"""Lambda Stack — 4 domain handler Lambda functions for Supply Chain.

Domain handlers (MCP targets for AgentCore Gateway):
  - inventory-handler: list_products, check_inventory, update_inventory
  - logistics-handler: calculate_shipping, list_shipments, track_shipment
  - supplier-handler: get_supplier, get_supplier_kb
  - quality-handler: check_quality, get_compliance, get_standards
"""

from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_cognito as cognito,
    aws_s3 as s3,
)
from constructs import Construct


class LambdaStack(Stack):
    """Compute layer: 4 domain Lambda handlers + 1 chat handler."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        inventory_table: dynamodb.ITable,
        shipments_table: dynamodb.ITable,
        routes_table: dynamodb.ITable,
        suppliers_table: dynamodb.ITable,
        inspections_table: dynamodb.ITable,
        compliance_table: dynamodb.ITable,
        standards_table: dynamodb.ITable,
        user_pool: cognito.IUserPool,
        app_client: cognito.UserPoolClient,
        cognito_domain_url: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # ------------------------------------------------------------------
        # Inventory Handler
        # ------------------------------------------------------------------
        self.inventory_lambda = lambda_.Function(
            self,
            "InventoryHandler",
            function_name="sc-inventory-handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="inventory-handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_funcs"),
            timeout=Duration.seconds(60),
            environment={
                "INVENTORY_TABLE_NAME": inventory_table.table_name,
            },
        )
        inventory_table.grant_read_write_data(self.inventory_lambda)

        # ------------------------------------------------------------------
        # Logistics Handler
        # ------------------------------------------------------------------
        self.logistics_lambda = lambda_.Function(
            self,
            "LogisticsHandler",
            function_name="sc-logistics-handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="logistics-handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_funcs"),
            timeout=Duration.seconds(60),
            environment={
                "SHIPMENT_TABLE_NAME": shipments_table.table_name,
                "ROUTE_TABLE_NAME": routes_table.table_name,
            },
        )
        shipments_table.grant_read_write_data(self.logistics_lambda)
        routes_table.grant_read_data(self.logistics_lambda)

        # ------------------------------------------------------------------
        # Supplier Handler
        # ------------------------------------------------------------------
        self.supplier_lambda = lambda_.Function(
            self,
            "SupplierHandler",
            function_name="sc-supplier-handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="supplier-handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_funcs"),
            timeout=Duration.seconds(60),
            environment={
                "SUPPLIER_TABLE_NAME": suppliers_table.table_name,
                # KNOWLEDGE_BASE_ID will be set after AgentCore stack creates KB
            },
        )
        suppliers_table.grant_read_data(self.supplier_lambda)
        # Bedrock Agent Runtime permission for KB retrieval
        self.supplier_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:Retrieve"],
                resources=["*"],  # KB ARN not yet known; scoped at deploy
            )
        )

        # ------------------------------------------------------------------
        # Quality Handler
        # ------------------------------------------------------------------
        self.quality_lambda = lambda_.Function(
            self,
            "QualityHandler",
            function_name="sc-quality-handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="quality-handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_funcs"),
            timeout=Duration.seconds(60),
            environment={
                "INSPECTIONS_TABLE_NAME": inspections_table.table_name,
                "COMPLIANCE_TABLE_NAME": compliance_table.table_name,
                "STANDARDS_TABLE_NAME": standards_table.table_name,
            },
        )
        inspections_table.grant_read_data(self.quality_lambda)
        compliance_table.grant_read_data(self.quality_lambda)
        standards_table.grant_read_data(self.quality_lambda)


