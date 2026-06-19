"""DynamoDB Stack — 7 tables for Supply Chain domain data.

Tables:
  - Inventory (product_id)
  - Shipments (tracking_number)
  - Routes (route_id)
  - Suppliers (supplier_id)
  - Inspections (batch_id) + GSI on product_id
  - Compliance (entity_id + entity_type)
  - Standards (category)
"""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
)
from constructs import Construct


class DynamoDbStack(Stack):
    """Data layer: 7 DynamoDB tables for all supply-chain domains."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Common table settings
        common = dict(
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ------------------------------------------------------------------
        # Inventory
        # ------------------------------------------------------------------
        self.inventory_table = dynamodb.Table(
            self,
            "InventoryTable",
            table_name="sc-inventory",
            partition_key=dynamodb.Attribute(
                name="product_id", type=dynamodb.AttributeType.STRING
            ),
            **common,
        )

        # ------------------------------------------------------------------
        # Shipments
        # ------------------------------------------------------------------
        self.shipments_table = dynamodb.Table(
            self,
            "ShipmentsTable",
            table_name="sc-shipments",
            partition_key=dynamodb.Attribute(
                name="tracking_number", type=dynamodb.AttributeType.STRING
            ),
            **common,
        )

        # ------------------------------------------------------------------
        # Routes
        # ------------------------------------------------------------------
        self.routes_table = dynamodb.Table(
            self,
            "RoutesTable",
            table_name="sc-routes",
            partition_key=dynamodb.Attribute(
                name="route_id", type=dynamodb.AttributeType.STRING
            ),
            **common,
        )

        # ------------------------------------------------------------------
        # Suppliers
        # ------------------------------------------------------------------
        self.suppliers_table = dynamodb.Table(
            self,
            "SuppliersTable",
            table_name="sc-suppliers",
            partition_key=dynamodb.Attribute(
                name="supplier_id", type=dynamodb.AttributeType.STRING
            ),
            **common,
        )

        # ------------------------------------------------------------------
        # Inspections (Quality) — with GSI on product_id
        # ------------------------------------------------------------------
        self.inspections_table = dynamodb.Table(
            self,
            "InspectionsTable",
            table_name="sc-inspections",
            partition_key=dynamodb.Attribute(
                name="batch_id", type=dynamodb.AttributeType.STRING
            ),
            **common,
        )
        self.inspections_table.add_global_secondary_index(
            index_name="ProductIndex",
            partition_key=dynamodb.Attribute(
                name="product_id", type=dynamodb.AttributeType.STRING
            ),
        )

        # ------------------------------------------------------------------
        # Compliance — composite key (entity_id + entity_type)
        # ------------------------------------------------------------------
        self.compliance_table = dynamodb.Table(
            self,
            "ComplianceTable",
            table_name="sc-compliance",
            partition_key=dynamodb.Attribute(
                name="entity_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="entity_type", type=dynamodb.AttributeType.STRING
            ),
            **common,
        )

        # ------------------------------------------------------------------
        # Standards
        # ------------------------------------------------------------------
        self.standards_table = dynamodb.Table(
            self,
            "StandardsTable",
            table_name="sc-standards",
            partition_key=dynamodb.Attribute(
                name="category", type=dynamodb.AttributeType.STRING
            ),
            **common,
        )
