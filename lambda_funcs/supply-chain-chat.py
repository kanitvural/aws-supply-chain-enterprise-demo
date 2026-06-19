"""Chat Handler Lambda — obtains OAuth2 token from Cognito and invokes Orchestrator Runtime.

Also serves a GET /status endpoint returning feature flags dynamically
by querying the orchestrator runtime's environment variables.
"""

import json
import logging
import os
from urllib import request, parse, error as urllib_error

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# CORS headers for all responses
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
}

# Environment variables
COGNITO_DOMAIN = os.environ.get("COGNITO_DOMAIN", "")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")
COGNITO_CLIENT_SECRET = os.environ.get("COGNITO_CLIENT_SECRET", "")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
ORCHESTRATOR_RUNTIME_ARN = os.environ.get("ORCHESTRATOR_RUNTIME_ARN", "")

# Lazy-load client secret from Cognito if not set in env
_cached_client_secret = None


def _get_client_secret():
    global _cached_client_secret
    if COGNITO_CLIENT_SECRET:
        return COGNITO_CLIENT_SECRET
    if _cached_client_secret:
        return _cached_client_secret
    logger.info("Fetching client secret from Cognito API...")
    cognito = boto3.client("cognito-idp")
    resp = cognito.describe_user_pool_client(
        UserPoolId=COGNITO_USER_POOL_ID,
        ClientId=COGNITO_CLIENT_ID,
    )
    _cached_client_secret = resp["UserPoolClient"].get("ClientSecret", "")
    return _cached_client_secret


def get_oauth2_token() -> str:
    """Obtain an OAuth2 access token from Cognito using client_credentials flow."""
    token_url = f"{COGNITO_DOMAIN}/oauth2/token"
    body = parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": COGNITO_CLIENT_ID,
        "client_secret": _get_client_secret(),
        "scope": "supplychain/read supplychain/write",
    }).encode("utf-8")

    req = request.Request(
        token_url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    resp = request.urlopen(req, timeout=10)
    return json.loads(resp.read().decode("utf-8"))["access_token"]


def invoke_orchestrator(message: str, session_id: str = "") -> str:
    """Invoke the Orchestrator Agent Runtime with OAuth bearer token via HTTP."""
    token = get_oauth2_token()

    escaped_arn = parse.quote(ORCHESTRATOR_RUNTIME_ARN, safe="")
    region = os.environ.get("AWS_REGION", "us-east-1")
    url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{escaped_arn}/invocations?qualifier=DEFAULT"

    if session_id and len(session_id) < 33:
        session_id = session_id + "-" + "0" * (33 - len(session_id) - 1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if session_id:
        headers["X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"] = session_id

    payload = json.dumps({"prompt": message}).encode("utf-8")
    req = request.Request(url, data=payload, headers=headers, method="POST")

    try:
        resp = request.urlopen(req, timeout=120)
        body = resp.read().decode("utf-8", errors="replace")
        logger.info("Raw response (%d bytes): %s", len(body), body[:300])

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
                else:
                    result_parts.append(str(data))
            except (json.JSONDecodeError, ValueError):
                result_parts.append(line)

        result = " ".join(result_parts).strip()
        return result or body.strip() or "No response from agent."
    except urllib_error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Runtime HTTP %d: %s", exc.code, error_body[:500])
        raise Exception(f"Runtime returned HTTP {exc.code}: {error_body[:200]}")


# Cache for runtime details (refreshed every 60s)
_runtime_cache = {"env": {}, "runtime_id": "", "obs_config": {}, "timestamp": 0}


def _get_runtime_details() -> dict:
    """Dynamically fetch the orchestrator runtime's environment variables and runtime ID.

    Caches for 60 seconds to avoid excessive API calls on /status polling.
    """
    import time
    now = time.time()
    if now - _runtime_cache["timestamp"] < 60 and _runtime_cache["env"]:
        return _runtime_cache

    if not ORCHESTRATOR_RUNTIME_ARN:
        return _runtime_cache

    try:
        runtime_id = ORCHESTRATOR_RUNTIME_ARN.split("/")[-1]
        client = boto3.client("bedrock-agentcore-control")
        resp = client.get_agent_runtime(agentRuntimeId=runtime_id)
        env = resp.get("environmentVariables", {})
        obs_config = resp.get("observabilityConfiguration", resp.get("loggingConfiguration", {}))
        _runtime_cache["env"] = env
        _runtime_cache["runtime_id"] = runtime_id
        _runtime_cache["obs_config"] = obs_config or {}
        _runtime_cache["timestamp"] = now
        logger.info("Refreshed runtime env vars: %s", list(env.keys()))
        return _runtime_cache
    except Exception as e:
        logger.warning("Failed to fetch runtime details: %s", e)
        return _runtime_cache


def _check_vpc_active(runtime_id: str) -> bool:
    """Check if the orchestrator runtime is running in VPC mode."""
    if not runtime_id:
        return False
    try:
        client = boto3.client("bedrock-agentcore-control")
        resp = client.get_agent_runtime(agentRuntimeId=runtime_id)
        network = resp.get("networkConfiguration", {})
        return network.get("networkMode") == "VPC"
    except Exception:
        return False


def handle_status():
    """Return feature status flags by querying the orchestrator runtime dynamically."""
    auth_ok = bool(ORCHESTRATOR_RUNTIME_ARN and COGNITO_DOMAIN and COGNITO_CLIENT_ID and COGNITO_USER_POOL_ID)

    cache = _get_runtime_details()
    env = cache.get("env", {})
    runtime_id = cache.get("runtime_id", "")

    memory_id = env.get("MEMORY_ID", "")
    guardrail_id = env.get("GUARDRAIL_ID", "")
    kb_specialist_arn = env.get("KB_SPECIALIST_RUNTIME_ARN", "")
    gateway_url = env.get("GATEWAY_URL", "")

    # Verify resources exist (best-effort)
    memory_active = False
    if memory_id:
        try:
            client = boto3.client("bedrock-agentcore-control")
            resp = client.get_memory(memoryId=memory_id)
            memory_active = resp.get("memory", {}).get("status") == "ACTIVE"
        except Exception:
            pass

    guardrail_active = False
    if guardrail_id:
        try:
            bedrock = boto3.client("bedrock")
            resp = bedrock.get_guardrail(guardrailIdentifier=guardrail_id)
            guardrail_active = resp.get("status") == "READY"
        except Exception:
            pass

    kb_active = False
    if kb_specialist_arn:
        try:
            client = boto3.client("bedrock-agentcore-control")
            rid = kb_specialist_arn.split("/")[-1]
            resp = client.get_agent_runtime(agentRuntimeId=rid)
            kb_active = resp.get("status") == "READY"
        except Exception:
            pass

    vpc_active = _check_vpc_active(cache.get("runtime_id", ""))

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "features": {
                "auth": {"enabled": auth_ok},
                "gateway": {"enabled": bool(gateway_url)},
                "memory": {"enabled": memory_active, "memoryId": memory_id or None},
                "guardrails": {"enabled": guardrail_active, "guardrailId": guardrail_id or None},
                "knowledgeBase": {"enabled": kb_active},
                "vpc": {"enabled": vpc_active},
            }
        }),
    }


def lambda_handler(event, context):
    """Chat Handler entrypoint — routes /chat POST and /status GET."""
    resource = event.get("resource", "")
    http_method = event.get("httpMethod", "")

    # Route: GET /status
    if resource == "/status" and http_method == "GET":
        return handle_status()

    # Route: POST /chat
    body = event.get("body", "{}")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            body = {}

    message = body.get("message", "").strip()
    if not message:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Missing 'message' in request body"}),
        }

    session_id = body.get("session_id", "")

    try:
        response_text = invoke_orchestrator(message, session_id)
    except urllib_error.URLError as exc:
        logger.error("Cognito token retrieval failed: %s", exc)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Authentication service unavailable. Check that COGNITO_DOMAIN, COGNITO_CLIENT_ID, and COGNITO_USER_POOL_ID are configured on the chat handler Lambda, and that a valid M2M app client exists with client_credentials flow and supplychain scopes."}),
        }
    except Exception as exc:
        error_msg = str(exc)
        logger.error("Orchestrator Runtime invocation failed: %s", exc)
        if "ORCHESTRATOR_RUNTIME_ARN" in error_msg or not ORCHESTRATOR_RUNTIME_ARN:
            hint = "Agent service unavailable. ORCHESTRATOR_RUNTIME_ARN is not set on the chat handler Lambda."
        elif "401" in error_msg or "mismatch" in error_msg.lower():
            hint = "Agent authentication failed. The Cognito app client ID may not be in the runtime's allowedClients list."
        elif "424" in error_msg or "500" in error_msg:
            hint = "Agent runtime error. Check the orchestrator runtime logs in CloudWatch for details."
        else:
            hint = f"Agent service unavailable: {error_msg[:150]}"
        return {
            "statusCode": 502,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": hint}),
        }

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({"response": response_text}),
    }
