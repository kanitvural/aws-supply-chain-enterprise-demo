"""Supply Chain CDK Pipeline Stage.

Assembles all stacks in the correct dependency order.
"""

from aws_cdk import Stage
from constructs import Construct

from stacks.vpc_stack import VpcStack
from stacks.dynamodb_stack import DynamoDbStack
from stacks.s3_assets_stack import S3AssetsStack
from stacks.cognito_stack import CognitoStack
from stacks.guardrails_stack import GuardrailsStack
from stacks.lambda_stack import LambdaStack
from stacks.api_gateway_stack import ApiGatewayStack
from stacks.cloudfront_stack import CloudFrontStack
from stacks.agentcore_stack import AgentCoreStack

class SupplyChainStage(Stage):
    """Prod stage containing all application stacks."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # 1. VPC
        vpc_stack = VpcStack(self, "VpcStack")

        # 2. DynamoDB
        dynamodb_stack = DynamoDbStack(self, "DynamoDbStack")

        # 3. S3 Assets
        assets_stack = S3AssetsStack(self, "S3AssetsStack")

        # 4. Cognito
        cognito_stack = CognitoStack(self, "CognitoStack")

        # 5. Guardrails
        guardrails_stack = GuardrailsStack(self, "GuardrailsStack")

        # 6. Lambda
        lambda_stack = LambdaStack(
            self,
            "LambdaStack",
            inventory_table=dynamodb_stack.inventory_table,
            shipments_table=dynamodb_stack.shipments_table,
            routes_table=dynamodb_stack.routes_table,
            suppliers_table=dynamodb_stack.suppliers_table,
            inspections_table=dynamodb_stack.inspections_table,
            compliance_table=dynamodb_stack.compliance_table,
            standards_table=dynamodb_stack.standards_table,
            user_pool=cognito_stack.user_pool,
            app_client=cognito_stack.app_client,
            cognito_domain_url=cognito_stack.cognito_domain_url,
        )

        # 7. AgentCore
        agentcore_stack = AgentCoreStack(
            self,
            "AgentCoreStack",
            vpc=vpc_stack.vpc,
            security_group_id=vpc_stack.security_group.security_group_id,
            assets_bucket=assets_stack.assets_bucket,
            user_pool=cognito_stack.user_pool,
            app_client=cognito_stack.app_client,
            cognito_domain_url=cognito_stack.cognito_domain_url,
            guardrail_id=guardrails_stack.guardrail_id,
            guardrail_version="DRAFT",
            inventory_lambda=lambda_stack.inventory_lambda,
            logistics_lambda=lambda_stack.logistics_lambda,
            supplier_lambda=lambda_stack.supplier_lambda,
            quality_lambda=lambda_stack.quality_lambda,
        )

        # 8. API Gateway
        api_gw_stack = ApiGatewayStack(
            self,
            "ApiGatewayStack",
            chat_lambda=agentcore_stack.chat_lambda,
        )

        # 9. CloudFront
        cloudfront_stack = CloudFrontStack(
            self,
            "CloudFrontStack",
            api_url=api_gw_stack.api.url,
        )

        # 10. CloudWatch Dashboard
        from stacks.cloudwatch_dashboard_stack import CloudWatchDashboardStack
        cw_dashboard_stack = CloudWatchDashboardStack(self, "CloudWatchDashboardStack")

        # 11. MLOps LLM Evaluation
        from stacks.mlops_eval_stack import MlopsEvalStack
        mlops_stack = MlopsEvalStack(self, "MlopsEvalStack")
