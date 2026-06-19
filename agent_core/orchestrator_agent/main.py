"""Supply Chain Orchestrator Agent Runtime — Gateway MCP tools + Memory + A2A.

Authentication: Cognito client_credentials flow for Gateway access.
Tool Discovery: AgentCore Gateway via MCP protocol.
Knowledge Base: Delegates to KB specialist agent via HTTP invocation.
Memory: AgentCoreMemorySessionManager (standard Strands integration).
Guardrails: Bedrock Guardrails via BedrockModel.
"""

import json
import logging
import os
import traceback
import concurrent.futures
from contextlib import asynccontextmanager

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("MODEL_ID", "amazon.nova-pro-v1:0")
REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
GATEWAY_URL = os.environ.get("GATEWAY_URL", "")
GUARDRAIL_ID = os.environ.get("GUARDRAIL_ID", "")
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "DRAFT")
MEMORY_ID = os.environ.get("MEMORY_ID", "")
KB_SPECIALIST_RUNTIME_ARN = os.environ.get("KB_SPECIALIST_RUNTIME_ARN", "")
COGNITO_DOMAIN = os.environ.get("COGNITO_DOMAIN", "")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")

SYSTEM_PROMPT = """You are a Supply Chain Management Assistant with access to these tools:

Inventory: list_products (no params), check_inventory (by product_id), update_inventory (product_id, quantity, operation)
Supplier: get_supplier (by supplier_id), get_supplier_kb (search supplier docs by query)
Logistics: list_shipments (no params), calculate_shipping (destination, weight_kg), track_shipment (tracking_number)
Quality: check_quality (product_id or batch_id), get_compliance (entity_id, entity_type), get_standards (product_category)
Knowledge Base: search_knowledge_base (search policies, procedures, manuals by query)

Guidelines:
- When users ask to list or see all products, use list_products.
- When users ask about shipments, use list_shipments.
- When users ask about policies, procedures, or manuals, use search_knowledge_base.
- Always use the appropriate tool to answer questions with real data.
- Always provide a visible response — never leave the response empty.
- If context from previous conversations is provided below the user message, it contains reliable information about this user (their name, preferences, past interactions). Use it directly to personalize your response. For example, if the context says the user's name is Alex, greet them by name.
- Be concise and actionable."""


# ---------------------------------------------------------------------------
# Cached resources — persist across requests
# ---------------------------------------------------------------------------

_gateway_client = None
_gateway_tools = None
_cognito_secret = None
_model = None


def _get_model():
    global _model
    if _model is None:
        _model = BedrockModel(
            model_id=MODEL_ID, region_name=REGION, temperature=0, max_tokens=3000,
            additional_request_fields={"inferenceConfig": {"topK": 1}},
        )
    return _model


def _get_cognito_token() -> str:
    """Get OAuth2 token from Cognito using client_credentials flow."""
    global _cognito_secret
    if not COGNITO_DOMAIN or not COGNITO_CLIENT_ID:
        return None
    if not _cognito_secret:
        cognito = boto3.client("cognito-idp", region_name=REGION)
        resp = cognito.describe_user_pool_client(
            UserPoolId=COGNITO_USER_POOL_ID, ClientId=COGNITO_CLIENT_ID
        )
        _cognito_secret = resp["UserPoolClient"].get("ClientSecret", "")
    if not _cognito_secret:
        return None
    from urllib import request as urllib_request, parse as urllib_parse
    body = urllib_parse.urlencode({
        "grant_type": "client_credentials", "client_id": COGNITO_CLIENT_ID,
        "client_secret": _cognito_secret, "scope": "supplychain/read supplychain/write",
    }).encode()
    req = urllib_request.Request(f"{COGNITO_DOMAIN}/oauth2/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    resp = urllib_request.urlopen(req, timeout=10)
    token = json.loads(resp.read())["access_token"]
    logger.info("Got Gateway token via Cognito")
    return token


def _init_gateway():
    """Initialize Gateway MCP client (cached, persistent connection)."""
    global _gateway_client, _gateway_tools
    if _gateway_tools is not None:
        return
    if not GATEWAY_URL:
        logger.warning("GATEWAY_URL not set")
        return
    token = _get_cognito_token()
    if not token:
        logger.warning("No Cognito token — Gateway tools unavailable")
        return
    try:
        _gateway_client = MCPClient(
            lambda: streamablehttp_client(
                url=GATEWAY_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
        )
        _gateway_client.start()
        _gateway_tools = _gateway_client.list_tools_sync()
        logger.info("Discovered %d Gateway tools", len(_gateway_tools))
        # Fix tool names for Nova (no hyphens)
        for t in _gateway_tools:
            t._agent_tool_name = t.mcp_tool.name.replace("___", "_").replace("-", "_")
    except Exception as e:
        logger.error("Gateway init failed: %s", e)
        _gateway_tools = []


# ---------------------------------------------------------------------------
# A2A — KB Specialist Agent invocation
# ---------------------------------------------------------------------------

@tool
def search_knowledge_base(query: str) -> str:
    """Search the supply chain knowledge base for policies, procedures, and manuals.

    Delegates the query to the KB Specialist Agent via HTTP invocation.

    Args:
        query: The search query describing what information to find.

    Returns:
        Relevant passages from the knowledge base documents.
    """
    if not KB_SPECIALIST_RUNTIME_ARN:
        return "Knowledge base specialist agent not configured."

    def _invoke():
        from urllib import request as urllib_request, parse as urllib_parse
        token = _get_cognito_token()
        if not token:
            return "Cannot authenticate with KB specialist."
        escaped_arn = urllib_parse.quote(KB_SPECIALIST_RUNTIME_ARN, safe="")
        url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{escaped_arn}/invocations?qualifier=DEFAULT"
        payload = json.dumps({"prompt": query}).encode()
        req = urllib_request.Request(url, data=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
        resp = urllib_request.urlopen(req, timeout=90)
        body = resp.read().decode("utf-8", errors="replace")
        result_parts = []
        for line in body.split("\n"):
            line = line.strip()
            if not line or line.startswith("event:"):
                continue
            if line.startswith("data: "):
                line = line[6:]
            try:
                data = json.loads(line)
                if isinstance(data, str):
                    result_parts.append(data)
                elif isinstance(data, dict):
                    text = data.get("text", data.get("response", data.get("message", "")))
                    if text:
                        result_parts.append(text)
            except (json.JSONDecodeError, ValueError):
                if line:
                    result_parts.append(line)
        return " ".join(result_parts).strip() or "No response from KB specialist."

    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            return executor.submit(_invoke).result(timeout=100)
    except Exception as e:
        logger.error("KB specialist failed: %s", e)
        return f"Knowledge base query failed: {str(e)[:200]}"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app):
    logger.info("Application starting")
    yield
    logger.info("Cleaning up")
    if _gateway_client:
        try:
            _gateway_client.stop()
        except Exception as e:
            logger.error("Error stopping gateway client: %s", e)


# ---------------------------------------------------------------------------
# App entrypoint
# ---------------------------------------------------------------------------

app = BedrockAgentCoreApp(lifespan=lifespan)


@app.entrypoint
async def handle(payload, context=None):
    """Process user queries — creates agent per request with session manager."""
    user_input = payload.get("prompt", "")
    if not user_input:
        return "Please provide a question about the supply chain."

    actor_id = payload.get("actor_id", "default_user")
    session_id = getattr(context, "session_id", None) or payload.get("session_id", "default_session")
    logger.info("Request: actor=%s session=%s input=%s", actor_id, session_id, user_input[:80])

    # Init Gateway (cached)
    _init_gateway()

    # Build tools
    all_tools = list(_gateway_tools or [])
    if KB_SPECIALIST_RUNTIME_ARN:
        all_tools.append(search_knowledge_base)

    # Build session manager for memory (standard Strands integration)
    session_manager = None
    memory_client = None
    memory_namespaces = {}
    if MEMORY_ID:
        try:
            from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
            from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
            from bedrock_agentcore.memory import MemoryClient

            config = AgentCoreMemoryConfig(
                memory_id=MEMORY_ID,
                session_id=session_id,
                actor_id=actor_id,
            )
            session_manager = AgentCoreMemorySessionManager(
                agentcore_memory_config=config,
                region_name=REGION,
            )
            # Set up cross-session retrieval
            memory_client = MemoryClient(region_name=REGION)
            # Load strategy namespaces dynamically
            try:
                strategies = memory_client.get_memory_strategies(memory_id=MEMORY_ID)
                for s in strategies:
                    stype = s.get("type", "")
                    sid = s.get("strategyId", "")
                    ns_list = s.get("namespaces", s.get("namespaceTemplates", []))
                    if ns_list and sid:
                        memory_namespaces[stype] = ns_list[0].replace("{memoryStrategyId}", sid).replace("{actorId}", actor_id)
            except Exception:
                # Fallback: try gmcp_client
                try:
                    resp = memory_client.gmcp_client.get_memory(memoryId=MEMORY_ID)
                    for s in resp.get("memory", {}).get("strategies", []):
                        stype = s.get("type", "")
                        sid = s.get("strategyId", "")
                        ns_list = s.get("namespaces", [])
                        if ns_list and sid:
                            memory_namespaces[stype] = ns_list[0].replace("{memoryStrategyId}", sid).replace("{actorId}", actor_id)
                except Exception as e2:
                    logger.warning("Could not load memory strategies: %s", e2)
            logger.info("Memory enabled (session_manager + %d retrieval namespaces)", len(memory_namespaces))
            # Fallback: use env vars for namespace templates if dynamic loading failed
            if not memory_namespaces:
                sem_ns = os.environ.get("MEMORY_SEMANTIC_NS", "")
                pref_ns = os.environ.get("MEMORY_PREFERENCE_NS", "")
                if sem_ns:
                    memory_namespaces["SEMANTIC"] = sem_ns.replace("{actorId}", actor_id)
                if pref_ns:
                    memory_namespaces["USER_PREFERENCE"] = pref_ns.replace("{actorId}", actor_id)
                if memory_namespaces:
                    logger.info("Loaded %d namespaces from env vars", len(memory_namespaces))
        except Exception as e:
            logger.warning("Memory setup failed: %s", e)

    # Apply guardrail on input BEFORE memory injection (word filter, content filter, PII)
    if GUARDRAIL_ID:
        try:
            bedrock_rt = boto3.client("bedrock-runtime", region_name=REGION)
            gr_resp = bedrock_rt.apply_guardrail(
                guardrailIdentifier=GUARDRAIL_ID,
                guardrailVersion=GUARDRAIL_VERSION,
                source="INPUT",
                content=[{"text": {"text": user_input}}],
            )
            if gr_resp.get("action") == "GUARDRAIL_INTERVENED":
                outputs = gr_resp.get("outputs", [])
                if outputs and outputs[0].get("text"):
                    masked_text = outputs[0]["text"]
                    if masked_text == "Your request was blocked by our content policy." or not masked_text.strip():
                        return "Your request was blocked by our content policy."
                    user_input = masked_text
                else:
                    return "Your request was blocked by our content policy."
        except Exception as e:
            logger.warning("Input guardrail failed: %s", e)

    # Cross-session memory retrieval — inject context from previous sessions
    if memory_client and memory_namespaces:
        try:
            all_context = []
            for ns_type in ("SEMANTIC", "USER_PREFERENCE"):
                ns = memory_namespaces.get(ns_type, "")
                if not ns:
                    continue
                memories = memory_client.retrieve_memories(
                    memory_id=MEMORY_ID, namespace=ns, query=user_input, top_k=3,
                )
                label = ns_type.lower().replace("_", " ")
                for mem in memories:
                    if isinstance(mem, dict):
                        content = mem.get("content", {})
                        if isinstance(content, dict):
                            text = content.get("text", "").strip()
                            if text:
                                all_context.append(f"[{label}] {text}")
            if all_context:
                user_input = user_input + "\n\nRelevant context from previous conversations:\n" + "\n".join(all_context)
                logger.info("Injected %d cross-session memory items", len(all_context))
        except Exception as e:
            logger.warning("Cross-session memory retrieval failed: %s", e)

    # Create agent per request (with session manager for memory)
    agent = Agent(
        model=_get_model(),
        tools=all_tools,
        system_prompt=SYSTEM_PROMPT,
        session_manager=session_manager,
    )

    try:
        response = agent(user_input)
        result_text = response.message["content"][0]["text"]

        # Apply guardrail on output manually (anonymization without blocking)
        if GUARDRAIL_ID:
            try:
                bedrock_rt = boto3.client("bedrock-runtime", region_name=REGION)
                gr_resp = bedrock_rt.apply_guardrail(
                    guardrailIdentifier=GUARDRAIL_ID,
                    guardrailVersion=GUARDRAIL_VERSION,
                    source="OUTPUT",
                    content=[{"text": {"text": result_text}}],
                )
                if gr_resp.get("action") == "GUARDRAIL_INTERVENED":
                    outputs = gr_resp.get("outputs", [])
                    if outputs and outputs[0].get("text"):
                        result_text = outputs[0]["text"]
                    else:
                        # Truly blocked — return blocked message
                        result_text = "The response was blocked by our content policy."
            except Exception as e:
                logger.warning("Output guardrail failed: %s", e)

        return result_text
    except Exception as e:
        logger.error("Agent error: %s\n%s", e, traceback.format_exc())
        return f"Error: {str(e)[:300]}"


if __name__ == "__main__":
    app.run()
