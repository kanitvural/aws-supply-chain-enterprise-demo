"""Knowledge Base Specialist Agent Runtime — handles KB queries via A2A.

This agent is invoked by the orchestrator via Agent-to-Agent (A2A) protocol.
It searches the supply chain knowledge base and returns relevant documents.
"""

import json
import logging
import os
import traceback

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("MODEL_ID", "amazon.nova-lite-v1:0")
REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID", "")

SYSTEM_PROMPT = """You are a Knowledge Base Specialist for a Supply Chain Management system.

You have access to a knowledge base containing supply chain policies, procedures, and manuals.
Use the search_knowledge_base tool to find relevant information when asked questions about:
- Inventory procedures, reorder policies, stock management guidelines
- Supplier management manuals, onboarding processes, vendor policies
- Quality control standards, inspection procedures, compliance requirements
- Any general supply chain policy or procedural question

Always search the knowledge base before answering. Provide concise, accurate answers
based on the retrieved documents. Cite the source document when possible."""

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = BedrockModel(
            model_id=MODEL_ID,
            region_name=REGION,
            temperature=0,
            max_tokens=2000,
        )
    return _model


_bedrock_agent_runtime = None


def _get_bedrock_agent_runtime():
    global _bedrock_agent_runtime
    if _bedrock_agent_runtime is None:
        _bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)
    return _bedrock_agent_runtime


def search_knowledge_base(query: str) -> str:
    """Search the supply chain knowledge base for policies, procedures, and manuals.

    Args:
        query: The search query describing what information to find.

    Returns:
        Relevant passages from the knowledge base documents.
    """
    if not KNOWLEDGE_BASE_ID:
        return "Knowledge base not configured."

    client = _get_bedrock_agent_runtime()
    try:
        resp = client.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": 5}
            },
        )
        results = []
        for item in resp.get("retrievalResults", []):
            text = item.get("content", {}).get("text", "").strip()
            source = item.get("location", {}).get("s3Location", {}).get("uri", "")
            score = item.get("score", 0)
            if text:
                source_label = source.split("/")[-1] if source else "unknown"
                results.append(f"[{source_label} (score: {score:.2f})]\n{text}")

        if results:
            return "\n\n---\n\n".join(results)
        return "No relevant information found in the knowledge base."
    except Exception as e:
        logger.error("KB retrieval failed: %s", e)
        return f"Knowledge base search failed: {str(e)[:200]}"


app = BedrockAgentCoreApp()


@app.entrypoint
async def handle(payload, context=None):
    """Process KB queries via A2A invocation."""
    user_input = payload.get("prompt", "")
    if not user_input:
        return "Please provide a question to search the knowledge base."

    logger.info("KB Specialist request: %s", user_input[:100])

    try:
        agent = Agent(
            model=_get_model(),
            tools=[search_knowledge_base],
            system_prompt=SYSTEM_PROMPT,
        )
        response = agent(user_input)
        return response.message["content"][0]["text"]
    except Exception as e:
        logger.error("Error: %s\n%s", e, traceback.format_exc())
        return f"Error: {str(e)[:300]}"


if __name__ == "__main__":
    app.run()
