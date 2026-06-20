"""Quality Lambda handler — check_quality, get_compliance, and get_standards tools."""

import json
import logging
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
INSPECTIONS_TABLE_NAME = os.environ.get("INSPECTIONS_TABLE_NAME", "")
COMPLIANCE_TABLE_NAME = os.environ.get("COMPLIANCE_TABLE_NAME", "")
STANDARDS_TABLE_NAME = os.environ.get("STANDARDS_TABLE_NAME", "")

inspections_table = dynamodb.Table(INSPECTIONS_TABLE_NAME)
compliance_table = dynamodb.Table(COMPLIANCE_TABLE_NAME)
standards_table = dynamodb.Table(STANDARDS_TABLE_NAME)


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == int(o) else float(o)
        return super().default(o)


def check_quality(params: dict) -> dict:
    """Query inspection results by product_id (GSI) or batch_id (partition key)."""
    product_id = params.get("product_id")
    batch_id = params.get("batch_id")

    if not product_id and not batch_id:
        return {"error": "At least one of product_id or batch_id is required", "status": 400}

    try:
        if batch_id:
            resp = inspections_table.get_item(Key={"batch_id": batch_id})
            item = resp.get("Item")
            if not item:
                return {"error": "Item not found", "status": 404}
            return item
        else:
            # Query the ProductIndex GSI by product_id
            resp = inspections_table.query(
                IndexName="ProductIndex",
                KeyConditionExpression=Key("product_id").eq(product_id),
            )
            items = resp.get("Items", [])
            if not items:
                return {"error": "Item not found", "status": 404}
            return {"inspections": items, "count": len(items)}

    except ClientError as exc:
        logger.error("DynamoDB error checking quality: %s", exc)
        return {"error": "Database operation failed", "status": 500}


def get_compliance(params: dict) -> dict:
    """Look up compliance record by entity_id and entity_type."""
    entity_id = params.get("entity_id")
    if not entity_id:
        return {"error": "Missing required parameter: entity_id", "status": 400}

    entity_type = params.get("entity_type")
    if not entity_type:
        return {"error": "Missing required parameter: entity_type", "status": 400}

    if entity_type not in ("product", "supplier"):
        return {"error": f"Invalid entity_type: {entity_type}. Must be product or supplier", "status": 400}

    try:
        resp = compliance_table.get_item(Key={"entity_id": entity_id, "entity_type": entity_type})
    except ClientError as exc:
        logger.error("DynamoDB error getting compliance: %s", exc)
        return {"error": "Database operation failed", "status": 500}

    item = resp.get("Item")
    if not item:
        return {"error": "Item not found", "status": 404}
    return item


def get_standards(params: dict) -> dict:
    """Query standards by product category, or scan all if no category given."""
    product_category = params.get("product_category")

    try:
        if product_category:
            resp = standards_table.get_item(Key={"category": product_category})
            item = resp.get("Item")
            if not item:
                return {"error": "Item not found", "status": 404}
            return item
        else:
            resp = standards_table.scan()
            items = resp.get("Items", [])
            return {"standards": items, "count": len(items)}

    except ClientError as exc:
        logger.error("DynamoDB error getting standards: %s", exc)
        return {"error": "Database operation failed", "status": 500}


# ---------------------------------------------------------------------------
# Tool routing
# ---------------------------------------------------------------------------

HANDLERS = {
    "check_quality": check_quality,
    "get_compliance": get_compliance,
    "get_standards": get_standards,
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
    params = event if "product_id" in event or "batch_id" in event or "entity_id" in event or "product_category" in event else event.get("input", event)
    if not tool_name:
        return {"statusCode": 400, "body": "Missing tool_name"}
    handler = HANDLERS.get(tool_name)
    if not handler:
        return {"statusCode": 400, "body": f"Unknown tool: {tool_name}"}
    result = handler(params)
    return {"statusCode": 200, "body": json.dumps(result, cls=DecimalEncoder)}
