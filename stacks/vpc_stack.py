"""VPC Stack — Network infrastructure for Supply Chain AgentCore.

Creates a VPC with public/private subnets, NAT Gateway, Security Group,
and VPC Interface Endpoints for AgentCore, Bedrock Runtime, and CloudWatch Logs.
"""

from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    CfnOutput,
)
from constructs import Construct


class VpcStack(Stack):
    """Network layer: VPC + subnets + NAT + endpoints + security group."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # ------------------------------------------------------------------
        # VPC — 2 AZ, public + private subnets, 1 NAT Gateway
        # ------------------------------------------------------------------
        self.vpc = ec2.Vpc(
            self,
            "SupplyChainVpc",
            vpc_name="supply-chain-vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            nat_gateways=1,  # Cost optimization: single NAT GW
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )

        # ------------------------------------------------------------------
        # Security Group — HTTPS inbound from VPC, all outbound
        # ------------------------------------------------------------------
        self.security_group = ec2.SecurityGroup(
            self,
            "AgentCoreSecurityGroup",
            vpc=self.vpc,
            security_group_name="supply-chain-agentcore-sg",
            description="Allow HTTPS from VPC CIDR, all outbound",
            allow_all_outbound=True,
        )
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(443),
            description="HTTPS from VPC CIDR",
        )

        # ------------------------------------------------------------------
        # Gateway Endpoint — S3 (free, no hourly charge)
        # ------------------------------------------------------------------
        self.vpc.add_gateway_endpoint(
            "S3GatewayEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        # ------------------------------------------------------------------
        # Interface Endpoints — private DNS enabled, shared security group
        # ------------------------------------------------------------------
        private_subnets = ec2.SubnetSelection(
            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
        )

        # AgentCore Gateway endpoint
        self.vpc.add_interface_endpoint(
            "AgentCoreGatewayEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService(
                name="bedrock-agentcore.gateway",
            ),
            subnets=private_subnets,
            security_groups=[self.security_group],
            private_dns_enabled=True,
        )

        # AgentCore Data Plane endpoint
        self.vpc.add_interface_endpoint(
            "AgentCoreDataPlaneEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService(
                name="bedrock-agentcore",
            ),
            subnets=private_subnets,
            security_groups=[self.security_group],
            private_dns_enabled=True,
        )

        # Bedrock Runtime endpoint
        self.vpc.add_interface_endpoint(
            "BedrockRuntimeEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService(
                name="bedrock-runtime",
            ),
            subnets=private_subnets,
            security_groups=[self.security_group],
            private_dns_enabled=True,
        )

        # CloudWatch Logs endpoint
        self.vpc.add_interface_endpoint(
            "CloudWatchLogsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            subnets=private_subnets,
            security_groups=[self.security_group],
            private_dns_enabled=True,
        )

        # ------------------------------------------------------------------
        # Outputs
        # ------------------------------------------------------------------
        CfnOutput(self, "VpcId", value=self.vpc.vpc_id)
        CfnOutput(
            self,
            "SecurityGroupId",
            value=self.security_group.security_group_id,
        )
