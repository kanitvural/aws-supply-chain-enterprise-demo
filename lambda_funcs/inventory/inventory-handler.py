"""Inventory Lambda handler — check_inventory and update_inventory tools."""

import json
import logging
import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("INVENTORY_TABLE_NAME", "")
table = dynamodb.Table(TABLE_NAME)


class DecimalEncoder(json.JSONEncoder):
    """Encode Decimal values returned by DynamoDB."""

    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == int(o) else float(o)
        return super().default(o)


def list_products(params: dict) -> dict:
    """Scan the inventory table and return all products."""
    try:
        resp = table.scan()
        items = resp.get("Items", [])
        # Handle pagination
        while "LastEvaluatedKey" in resp:
            resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
        return {"products": items, "count": len(items)}
    except ClientError as exc:
        logger.error("DynamoDB error listing products: %s", exc)
        return {"error": "Database operation failed", "status": 500}


def check_inventory(params: dict) -> dict:
    """Look up a product by product_id or product_name."""
    product_id = params.get("product_id")
    product_name = params.get("product_name")

    if not product_id and not product_name:
        return {"error": "Missing required parameter: either product_id or product_name must be provided", "status": 400}

    try:
        if product_id:
            resp = table.get_item(Key={"product_id": product_id})
            item = resp.get("Item")
        else:
            # Search by name using a scan (OK for small datasets)
            from boto3.dynamodb.conditions import Attr
            resp = table.scan(FilterExpression=Attr("name").eq(product_name))
            items = resp.get("Items", [])
            item = items[0] if items else None

    except ClientError as exc:
        logger.error("DynamoDB error checking inventory: %s", exc)
        return {"error": "Database operation failed", "status": 500}

    if not item:
        return {"error": f"Item not found (Search: ID={product_id}, Name={product_name})", "status": 404}
    return item


def update_inventory(params: dict) -> dict:
    """Update inventory quantity using set/add/subtract operations."""
    product_id = params.get("product_id")
    if not product_id:
        return {"error": "Missing required parameter: product_id", "status": 400}

    quantity = params.get("quantity")
    if quantity is None:
        return {"error": "Missing required parameter: quantity", "status": 400}

    operation = params.get("operation", "set")
    if operation not in ("set", "add", "subtract"):
        return {"error": f"Invalid operation: {operation}. Must be set, add, or subtract", "status": 400}

    try:
        if operation == "set":
            resp = table.update_item(
                Key={"product_id": product_id},
                UpdateExpression="SET quantity = :q",
                ExpressionAttributeValues={":q": quantity},
                ReturnValues="ALL_NEW",
            )
        elif operation == "add":
            resp = table.update_item(
                Key={"product_id": product_id},
                UpdateExpression="SET quantity = quantity + :q",
                ExpressionAttributeValues={":q": quantity},
                ReturnValues="ALL_NEW",
            )
        else:  # subtract
            resp = table.update_item(
                Key={"product_id": product_id},
                UpdateExpression="SET quantity = quantity - :q",
                ExpressionAttributeValues={":q": quantity},
                ReturnValues="ALL_NEW",
            )
    except ClientError as exc:
        logger.error("DynamoDB error updating inventory: %s", exc)
        return {"error": "Database operation failed", "status": 500}

    return resp.get("Attributes", {})


# ---------------------------------------------------------------------------
# Tool routing
# ---------------------------------------------------------------------------

HANDLERS = {
    "list_products": list_products,
    "check_inventory": check_inventory,
    "update_inventory": update_inventory,
}


def lambda_handler(event, context):
    """Route Gateway tool invocations to the correct handler function.

    AgentCore Gateway sends:
    - Tool name via context.client_context.custom["bedrockAgentCoreToolName"]
      (format: "target-name___tool_name")
    - Parameters directly in the event dict (not nested under "input")
    """
    logger.info("Event: %s", json.dumps(event, cls=DecimalEncoder))

    # Extract tool name from Gateway context or fallback to event
    tool_name = None
    try:
        extended_name = context.client_context.custom["bedrockAgentCoreToolName"]
        tool_name = extended_name.split("___")[1] if "___" in extended_name else extended_name
    except (AttributeError, KeyError, TypeError):
        tool_name = event.get("tool_name")

    # Parameters are directly in the event (Gateway format) or under "input" (legacy)
    params = event if "product_id" in event or "quantity" in event else event.get("input", event)

    if not tool_name:
        return {"statusCode": 400, "body": "Missing tool_name"}

    handler = HANDLERS.get(tool_name)
    if not handler:
        return {"statusCode": 400, "body": f"Unknown tool: {tool_name}"}

    result = handler(params)
    return {"statusCode": 200, "body": json.dumps(result, cls=DecimalEncoder)}
