"""Supply Chain Pipeline Stack.

Creates the self-mutating CodePipeline using AWS CDK Pipelines.
It pulls code from GitHub, installs dependencies, builds Docker images (for AgentCore),
and deploys the SupplyChainStage.
"""

from aws_cdk import Stack
from aws_cdk.pipelines import CodePipeline, CodePipelineSource, ShellStep
from constructs import Construct

from .supply_chain_stage import SupplyChainStage


class SupplyChainPipelineStack(Stack):
    """CI/CD layer: Self-mutating CDK pipeline."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Retrieve settings from cdk.json context
        github_repo = self.node.try_get_context("githubRepo") or "kanitvural/aws-supply-chain-enterprise-demo"
        github_branch = self.node.try_get_context("githubBranch") or "main"
        github_connection_arn = self.node.try_get_context("githubConnectionArn")

        pipeline = CodePipeline(
            self,
            "Pipeline",
            pipeline_name="SupplyChainPipeline",
            synth=ShellStep(
                "Synth",
                input=CodePipelineSource.connection(
                    github_repo,
                    github_branch,
                    connection_arn=github_connection_arn,
                ),
                commands=[
                    "npm install -g aws-cdk",
                    "pip install -r requirements.txt",
                    "cdk synth",
                ],
            ),
            # Docker is required for AgentCore Runtime deployment via AgentRuntimeArtifact.from_asset
            docker_enabled_for_synth=True,
        )

        pipeline.add_stage(SupplyChainStage(self, "Prod"))
