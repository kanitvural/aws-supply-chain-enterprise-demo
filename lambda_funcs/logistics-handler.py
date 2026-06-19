"""Logistics Lambda handler — calculate_shipping and track_shipment tools."""

import json
import logging
import os
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
SHIPMENT_TABLE_NAME = os.environ.get("SHIPMENT_TABLE_NAME", "")
ROUTE_TABLE_NAME = os.environ.get("ROUTE_TABLE_NAME", "")

shipments_table = dynamodb.Table(SHIPMENT_TABLE_NAME)
routes_table = dynamodb.Table(ROUTE_TABLE_NAME)


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == int(o) else float(o)
        return super().default(o)


def calculate_shipping(params: dict) -> dict:
    """Calculate shipping cost by finding a matching route and applying weight."""
    destination = params.get("destination")
    if not destination:
        return {"error": "Missing required parameter: destination", "status": 400}

    weight_kg = params.get("weight_kg")
    if weight_kg is None:
        return {"error": "Missing required parameter: weight_kg", "status": 400}

    try:
        resp = routes_table.scan()
    except ClientError as exc:
        logger.error("DynamoDB error scanning routes: %s", exc)
        return {"error": "Database operation failed", "status": 500}

    # Find a route whose destination contains the requested destination (case-insensitive)
    dest_lower = destination.lower()
    matching_route = None
    for route in resp.get("Items", []):
        if dest_lower in route.get("destination", "").lower():
            matching_route = route
            break

    if not matching_route:
        return {"error": f"No route found for destination: {destination}", "status": 404}

    base_cost = float(matching_route.get("base_cost", 0))
    # Cost scales linearly with weight: cost = base_cost * (weight_kg / 100)
    estimated_cost = round(base_cost * (float(weight_kg) / 100), 2)

    return {
        "route_id": matching_route.get("route_id"),
        "origin": matching_route.get("origin"),
        "destination": matching_route.get("destination"),
        "carrier": matching_route.get("carrier"),
        "distance_km": matching_route.get("distance_km"),
        "estimated_cost": estimated_cost,
        "weight_kg": weight_kg,
    }


def list_shipments(params: dict) -> dict:
    """List all shipments with pagination support."""
    try:
        scan_kwargs = {"Limit": 50}
        last_key = params.get("last_key")
        if last_key:
            scan_kwargs["ExclusiveStartKey"] = {"tracking_number": last_key}
        resp = shipments_table.scan(**scan_kwargs)
        result = {"shipments": resp.get("Items", []), "count": resp.get("Count", 0)}
        if "LastEvaluatedKey" in resp:
            result["last_key"] = resp["LastEvaluatedKey"].get("tracking_number")
        return result
    except ClientError as exc:
        logger.error("DynamoDB error listing shipments: %s", exc)
        return {"error": "Database operation failed", "status": 500}


def track_shipment(params: dict) -> dict:
    """Look up a shipment by tracking_number."""
    tracking_number = params.get("tracking_number")
    if not tracking_number:
        return {"error": "Missing required parameter: tracking_number", "status": 400}

    try:
        resp = shipments_table.get_item(Key={"tracking_number": tracking_number})
    except ClientError as exc:
        logger.error("DynamoDB error tracking shipment: %s", exc)
        return {"error": "Database operation failed", "status": 500}

    item = resp.get("Item")
    if not item:
        return {"error": "Item not found", "status": 404}
    return item


# ---------------------------------------------------------------------------
# Tool routing
# ---------------------------------------------------------------------------

HANDLERS = {
    "calculate_shipping": calculate_shipping,
    "list_shipments": list_shipments,
    "track_shipment": track_shipment,
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
    params = event if "destination" in event or "tracking_number" in event or "weight_kg" in event else event.get("input", event)
    if not tool_name:
        return {"statusCode": 400, "body": "Missing tool_name"}
    handler = HANDLERS.get(tool_name)
    if not handler:
        return {"statusCode": 400, "body": f"Unknown tool: {tool_name}"}
    result = handler(params)
    return {"statusCode": 200, "body": json.dumps(result, cls=DecimalEncoder)}
