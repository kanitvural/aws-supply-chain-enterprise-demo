"""S3 Assets Stack — bucket for schemas and knowledge base documents.

Deploys:
  - S3 bucket for supply-chain assets
  - Schema JSON files under schemas/ prefix
  - Knowledge base documents under kb-docs/ prefix
"""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
)
from constructs import Construct


class S3AssetsStack(Stack):
    """Asset layer: S3 bucket + auto-deployed schemas & KB docs."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # ------------------------------------------------------------------
        # S3 Bucket — schemas + KB documents
        # ------------------------------------------------------------------
        self.assets_bucket = s3.Bucket(
            self,
            "AssetsBucket",
            bucket_name=f"supply-chain-assets-{self.account}",
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        # ------------------------------------------------------------------
        # Deploy schema JSON files → schemas/ prefix
        # ------------------------------------------------------------------
        s3deploy.BucketDeployment(
            self,
            "DeploySchemas",
            sources=[s3deploy.Source.asset("agent_core/schemas")],
            destination_bucket=self.assets_bucket,
            destination_key_prefix="schemas",
        )

        # ------------------------------------------------------------------
        # Deploy knowledge base documents → kb-docs/ prefix
        # ------------------------------------------------------------------
        s3deploy.BucketDeployment(
            self,
            "DeployKBDocs",
            sources=[s3deploy.Source.asset("agent_core/knowledge_base_docs")],
            destination_bucket=self.assets_bucket,
            destination_key_prefix="kb-docs",
        )
