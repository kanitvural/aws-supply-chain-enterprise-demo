from aws_cdk import (
    Stack,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct

class CloudWatchDashboardStack(Stack):
    """Observability layer: CloudWatch Dashboard for Agent and Bedrock metrics."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        dashboard = cloudwatch.Dashboard(
            self,
            "SupplyChainDashboard",
            dashboard_name="SupplyChain-AI-Metrics"
        )

        # Bedrock Token Usage Widget
        token_widget = cloudwatch.GraphWidget(
            title="Bedrock Token Usage (Nova Pro vs Lite)",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Bedrock",
                    metric_name="InputTokenCount",
                    dimensions_map={"ModelId": "amazon.nova-pro-v1:0"},
                    label="Nova Pro Input",
                    statistic="Sum",
                ),
                cloudwatch.Metric(
                    namespace="AWS/Bedrock",
                    metric_name="OutputTokenCount",
                    dimensions_map={"ModelId": "amazon.nova-pro-v1:0"},
                    label="Nova Pro Output",
                    statistic="Sum",
                ),
                cloudwatch.Metric(
                    namespace="AWS/Bedrock",
                    metric_name="InputTokenCount",
                    dimensions_map={"ModelId": "amazon.nova-lite-v1:0"},
                    label="Nova Lite Input",
                    statistic="Sum",
                ),
                cloudwatch.Metric(
                    namespace="AWS/Bedrock",
                    metric_name="OutputTokenCount",
                    dimensions_map={"ModelId": "amazon.nova-lite-v1:0"},
                    label="Nova Lite Output",
                    statistic="Sum",
                )
            ],
            width=12
        )

        # Bedrock Invocation Latency
        latency_widget = cloudwatch.GraphWidget(
            title="Bedrock Invocation Latency (ms)",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Bedrock",
                    metric_name="InvocationLatency",
                    dimensions_map={"ModelId": "amazon.nova-pro-v1:0"},
                    label="Nova Pro Latency",
                    statistic="Average",
                ),
                cloudwatch.Metric(
                    namespace="AWS/Bedrock",
                    metric_name="InvocationLatency",
                    dimensions_map={"ModelId": "amazon.nova-lite-v1:0"},
                    label="Nova Lite Latency",
                    statistic="Average",
                )
            ],
            width=12
        )

        # Lambda Invocations (MCP Tools)
        lambda_widget = cloudwatch.GraphWidget(
            title="MCP Tool Executions (Lambda)",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Lambda",
                    metric_name="Invocations",
                    statistic="Sum",
                )
            ],
            width=24
        )

        dashboard.add_widgets(token_widget, latency_widget)
        dashboard.add_widgets(lambda_widget)
