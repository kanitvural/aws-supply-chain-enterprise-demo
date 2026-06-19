"""CloudFront Stack — Frontend hosting with S3, OAC, and CloudFront.

Deploys:
  - Private S3 Bucket for frontend files
  - Origin Access Control (OAC)
  - CloudFront Distribution
  - Deploys local `app/` folder to the S3 bucket
  - Dynamically injects config.json with the API Gateway URL
"""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_s3 as s3,
    aws_iam as iam,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3_deployment as s3deploy,
    CfnOutput,
)
from constructs import Construct


class CloudFrontStack(Stack):
    """Frontend layer: S3 + CloudFront CDN + App Deployment."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        api_url: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # ------------------------------------------------------------------
        # Private S3 Bucket
        # ------------------------------------------------------------------
        self.bucket = s3.Bucket(
            self,
            "SupplyChainFrontendBucket",
            bucket_name=f"supply-chain-frontend-{self.account}",
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        # ------------------------------------------------------------------
        # Origin Access Control (OAC) — replaces legacy OAI
        # ------------------------------------------------------------------
        oac = cloudfront.CfnOriginAccessControl(
            self,
            "SupplyChainOAC",
            origin_access_control_config=cloudfront.CfnOriginAccessControl.OriginAccessControlConfigProperty(
                name="SupplyChainOAC",
                origin_access_control_origin_type="s3",
                signing_behavior="always",
                signing_protocol="sigv4",
            ),
        )

        # ------------------------------------------------------------------
        # CloudFront Distribution — uses S3Origin (vanilla) + OAC override
        # ------------------------------------------------------------------
        self.distribution = cloudfront.Distribution(
            self,
            "SupplyChainDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    self.bucket,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
            ],
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
        )

        # ------------------------------------------------------------------
        # Deploy App files and dynamic config.json
        # ------------------------------------------------------------------
        s3deploy.BucketDeployment(
            self,
            "DeployFrontendApp",
            sources=[
                s3deploy.Source.asset("app"),
                s3deploy.Source.json_data("config.json", {"apiUrl": api_url}),
            ],
            destination_bucket=self.bucket,
            distribution=self.distribution,
            distribution_paths=["/*"],
        )

        # ------------------------------------------------------------------
        # Outputs
        # ------------------------------------------------------------------
        CfnOutput(self, "CloudFrontURL", value=f"https://{self.distribution.distribution_domain_name}")
        CfnOutput(self, "FrontendBucketName", value=self.bucket.bucket_name)
