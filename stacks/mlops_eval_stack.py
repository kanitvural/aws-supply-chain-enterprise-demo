from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    Duration
)
from constructs import Construct

class MlopsEvalStack(Stack):
    """MLOps layer: Automated Model Evaluation with S3, Lambda, EventBridge, and SNS."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # 1. MLOps S3 Bucket (for logs, datasets, results)
        self.mlops_bucket = s3.Bucket(
            self,
            "MlopsEvalBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # 2. Deploy Golden Datasets to S3
        s3deploy.BucketDeployment(
            self,
            "DeployGoldenDatasets",
            sources=[s3deploy.Source.asset("agent_core/golden_datasets")],
            destination_bucket=self.mlops_bucket,
            destination_key_prefix="golden_datasets",
        )

        # 3. SNS Topic for Notifications
        self.eval_topic = sns.Topic(
            self,
            "MlopsEvalTopic",
            display_name="Supply Chain LLMOps Notifications"
        )
        
        # Subscribe email from cdk.json context
        notification_email = self.node.try_get_context("notification_email")
        if notification_email:
            self.eval_topic.add_subscription(subs.EmailSubscription(notification_email))

        # 4. IAM Role for Bedrock Evaluation
        eval_role = iam.Role(
            self,
            "BedrockEvalRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
        )
        self.mlops_bucket.grant_read_write(eval_role)
        
        # Bedrock permissions for evaluation
        eval_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=["*"] # Restrict to specific models in prod
        ))

        # 5. Lambda Function to Trigger Evaluation
        self.eval_lambda = lambda_.Function(
            self,
            "MlopsEvalLambda",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="mlops_eval_handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_funcs/mlops_eval"),
            timeout=Duration.minutes(1),
            environment={
                "MLOPS_BUCKET": self.mlops_bucket.bucket_name,
                "SNS_TOPIC_ARN": self.eval_topic.topic_arn,
                "EVAL_ROLE_ARN": eval_role.role_arn,
            }
        )
        
        # Grant permissions to Lambda
        self.eval_topic.grant_publish(self.eval_lambda)
        self.mlops_bucket.grant_read_write(self.eval_lambda)
        self.eval_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:CreateEvaluationJob"],
            resources=["*"]
        ))
        self.eval_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=[eval_role.role_arn]
        ))

        # 6. EventBridge Rule (Weekly trigger)
        weekly_rule = events.Rule(
            self,
            "WeeklyEvalRule",
            schedule=events.Schedule.cron(
                minute="0",
                hour="2",
                week_day="SUN"
            )
        )
        weekly_rule.add_target(targets.LambdaFunction(self.eval_lambda))
