"""Cognito Stack — M2M authentication for Chat UI ↔ Orchestrator Agent.

Creates:
  - User Pool (SupplyChainUserPool)
  - Resource Server (supplychain) with read/write scopes
  - Cognito Domain (hosted UI prefix)
  - App Client (client_credentials flow, generate_secret=True)
"""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    aws_cognito as cognito,
)
from constructs import Construct


class CognitoStack(Stack):
    """Auth layer: Cognito User Pool with M2M client_credentials flow."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # ------------------------------------------------------------------
        # User Pool
        # ------------------------------------------------------------------
        self.user_pool = cognito.UserPool(
            self,
            "SupplyChainUserPool",
            user_pool_name="SupplyChainUserPool",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ------------------------------------------------------------------
        # Resource Server — supplychain/read, supplychain/write
        # ------------------------------------------------------------------
        read_scope = cognito.ResourceServerScope(
            scope_name="read",
            scope_description="Read access to supply chain resources",
        )
        write_scope = cognito.ResourceServerScope(
            scope_name="write",
            scope_description="Write access to supply chain resources",
        )

        resource_server = self.user_pool.add_resource_server(
            "SupplyChainResourceServer",
            identifier="supplychain",
            scopes=[read_scope, write_scope],
        )

        # ------------------------------------------------------------------
        # Cognito Domain — hosted UI prefix for OAuth2 token endpoint
        # ------------------------------------------------------------------
        self.domain = self.user_pool.add_domain(
            "SupplyChainDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"supply-chain-{self.account}",
            ),
        )

        # ------------------------------------------------------------------
        # M2M App Client — client_credentials flow
        # ------------------------------------------------------------------
        self.app_client = self.user_pool.add_client(
            "SupplyChainM2MClient",
            user_pool_client_name="SupplyChainM2MClient",
            generate_secret=True,
            auth_flows=cognito.AuthFlow(
                custom=False,
                user_password=False,
                user_srp=False,
            ),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    client_credentials=True,
                ),
                scopes=[
                    cognito.OAuthScope.resource_server(resource_server, read_scope),
                    cognito.OAuthScope.resource_server(resource_server, write_scope),
                ],
            ),
        )

        # ------------------------------------------------------------------
        # Derived values for downstream stacks
        # ------------------------------------------------------------------
        self.cognito_domain_url = (
            f"https://{self.domain.domain_name}.auth.{self.region}.amazoncognito.com"
        )

        # ------------------------------------------------------------------
        # Outputs
        # ------------------------------------------------------------------
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(self, "UserPoolArn", value=self.user_pool.user_pool_arn)
        CfnOutput(self, "AppClientId", value=self.app_client.user_pool_client_id)
        CfnOutput(self, "CognitoDomainUrl", value=self.cognito_domain_url)
