"""Supplier Lambda handler — get_supplier and get_supplier_kb tools."""

import json
import logging
import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("SUPPLIER_TABLE_NAME", "")

table = dynamodb.Table(TABLE_NAME)
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime")
ssm_client = boto3.client("ssm")

def get_kb_id():
    kb_id = os.environ.get("KNOWLEDGE_BASE_ID", "")
    if kb_id:
        return kb_id
    try:
        response = ssm_client.get_parameter(Name="/supplychain/kb_id")
        return response["Parameter"]["Value"]
    except Exception as e:
        logger.error("Failed to fetch KB ID from SSM: %s", e)
        return ""

KNOWLEDGE_BASE_ID = get_kb_id()


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == int(o) else float(o)
        return super().default(o)


def get_supplier(params: dict) -> dict:
    """Look up a supplier by supplier_id or supplier_name."""
    supplier_id = params.get("supplier_id")
    supplier_name = params.get("supplier_name")

    if not supplier_id and not supplier_name:
        return {"error": "Missing required parameter: either supplier_id or supplier_name must be provided", "status": 400}

    try:
        if supplier_id:
            resp = table.get_item(Key={"supplier_id": supplier_id})
            item = resp.get("Item")
        else:
            from boto3.dynamodb.conditions import Attr
            resp = table.scan(FilterExpression=Attr("name").eq(supplier_name))
            items = resp.get("Items", [])
            item = items[0] if items else None
    except ClientError as exc:
        logger.error("DynamoDB error getting supplier: %s", exc)
        return {"error": "Database operation failed", "status": 500}

    if not item:
        return {"error": f"Item not found (Search: ID={supplier_id}, Name={supplier_name})", "status": 404}
    return item


def get_supplier_kb(params: dict) -> dict:
    """Query the Bedrock Knowledge Base for supplier documents."""
    query = params.get("query")
    if not query:
        return {"error": "Missing required parameter: query", "status": 400}

    if not KNOWLEDGE_BASE_ID:
        return {"error": "Knowledge base not configured", "status": 500}

    try:
        resp = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": query},
        )
    except ClientError as exc:
        logger.error("Knowledge base query failed: %s", exc)
        return {"error": "Knowledge base query failed", "status": 500}

    results = resp.get("retrievalResults", [])
    excerpts = [
        {
            "text": r.get("content", {}).get("text", ""),
            "source": r.get("location", {}).get("s3Location", {}).get("uri", ""),
        }
        for r in results
    ]
    return {"excerpts": excerpts, "count": len(excerpts)}


# ---------------------------------------------------------------------------
# Tool routing
# ---------------------------------------------------------------------------

HANDLERS = {
    "get_supplier": get_supplier,
    "get_supplier_kb": get_supplier_kb,
}


def lambda_handler(event, context):
    """Route Gateway tool invocations to the correct handler function."""
    logger.info("Event: %s", json.dumps(event, cls=DecimalEncoder))
    tool_name = None
    try:
        extended_name = context.client_context.custom["bedrockAgentCoreToolName"]
        tool_name = extended_name.split("___")[1] if "___" in extended_name else extended_name
    except (AttributeError, KeyError, TypeError):
        tool_name = event.get("tool_name")
    params = event if "supplier_id" in event or "supplier_name" in event or "query" in event else event.get("input", event)
    if not tool_name:
        return {"statusCode": 400, "body": "Missing tool_name"}
    handler = HANDLERS.get(tool_name)
    if not handler:
        return {"statusCode": 400, "body": f"Unknown tool: {tool_name}"}
    result = handler(params)
    return {"statusCode": 200, "body": json.dumps(result, cls=DecimalEncoder)}
