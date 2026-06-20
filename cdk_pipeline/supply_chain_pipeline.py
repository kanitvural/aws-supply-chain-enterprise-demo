"""Supply Chain Pipeline Stack.

Creates the self-mutating CodePipeline using AWS CDK Pipelines.
It pulls code from GitHub, installs dependencies, builds Docker images (for AgentCore),
and deploys the SupplyChainStage.
"""

from aws_cdk import Stack, aws_iam as iam, aws_codebuild as codebuild
from aws_cdk.pipelines import CodePipeline, CodePipelineSource, ShellStep, CodeBuildStep
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
                    "cdk synth --context @aws-cdk/core:bootstrapQualifier=sc",
                ],
            ),
            # Docker is required for AgentCore Runtime deployment via AgentRuntimeArtifact.from_asset
            docker_enabled_for_synth=True,
        )

        prod_stage = pipeline.add_stage(SupplyChainStage(self, "Prod"))

        post_deploy_step = CodeBuildStep(
            "PostDeploymentDataSync",
            build_environment=codebuild.BuildEnvironment(
                compute_type=codebuild.ComputeType.SMALL,
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
            ),
            commands=[
                "echo '🔧 Installing required Python dependencies...'",
                "pip install boto3",
                "echo '📦 Seeding DynamoDB tables with mock enterprise data...'",
                "python scripts/load_mock_data_to_dynamodb_tables.py",
                "echo '🧠 Triggering Amazon Bedrock Knowledge Base synchronization...'",
                "python scripts/sync_knowledge_base.py",
                "echo '✅ Zero-Touch Deployment: Data hydration and sync completed successfully!'"
            ],
            role_policy_statements=[
                iam.PolicyStatement(
                    actions=[
                        "dynamodb:PutItem",
                        "dynamodb:BatchWriteItem",
                        "dynamodb:DescribeTable"
                    ],
                    resources=["*"]
                ),
                iam.PolicyStatement(
                    actions=[
                        "bedrock:ListKnowledgeBases",
                        "bedrock:ListDataSources",
                        "bedrock:StartIngestionJob"
                    ],
                    resources=["*"]
                )
            ]
        )
        prod_stage.add_post(post_deploy_step)

        # Build the pipeline to generate the underlying CodeBuild projects
        pipeline.build_pipeline()

        # Grant self-mutation role access to read SSM bootstrap version
        pipeline.self_mutation_project.role.add_to_principal_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter/cdk-bootstrap/*/version"],
            )
        )
