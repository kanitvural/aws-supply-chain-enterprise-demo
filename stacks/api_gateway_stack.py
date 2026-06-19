"""API Gateway Stack — REST API for Chat UI.

Creates a REST API with:
  - POST /chat -> Chat Handler Lambda
  - GET /status -> Chat Handler Lambda
  - CORS enabled
"""

from aws_cdk import (
    Stack,
    aws_apigateway as apigw,
    aws_lambda as lambda_,
    CfnOutput,
)
from constructs import Construct


class ApiGatewayStack(Stack):
    """API layer: REST API for frontend communication."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        chat_lambda: lambda_.IFunction,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # ------------------------------------------------------------------
        # API Gateway
        # ------------------------------------------------------------------
        self.api = apigw.RestApi(
            self,
            "SupplyChainApi",
            rest_api_name="SupplyChainChatApi",
            endpoint_configuration=apigw.EndpointConfiguration(types=[apigw.EndpointType.REGIONAL]),
            description="API Gateway for Supply Chain Assistant",
            default_cors_preflight_options=apigw.CorsOptions(
                # ALL_ORIGINS is kept due to cyclic dependency with CloudFront
                # (CloudFront URL is unknown until API is deployed)
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=[
                    "Content-Type",
                    "Authorization",
                    "X-Amz-Date",
                    "X-Api-Key",
                    "X-Amz-Security-Token",
                ],
            ),
            deploy_options=apigw.StageOptions(
                stage_name="prod",
            ),
        )

        # ------------------------------------------------------------------
        # Routes mapping to Chat Lambda
        # ------------------------------------------------------------------
        chat_integration = apigw.LambdaIntegration(chat_lambda)

        # POST /chat
        self.api.root.add_resource("chat").add_method("POST", chat_integration)

        # GET /status
        self.api.root.add_resource("status").add_method("GET", chat_integration)

        # ------------------------------------------------------------------
        # Outputs
        # ------------------------------------------------------------------
        CfnOutput(self, "ApiUrl", value=self.api.url)
