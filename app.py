#!/usr/bin/env python3
import os

import aws_cdk as cdk
from cdk_pipeline.supply_chain_pipeline import SupplyChainPipelineStack

app = cdk.App()

SupplyChainPipelineStack(
    app,
    "SupplyChainPipeline",
    # Using explicit account and region to enable advanced features like VPC lookups
    env=cdk.Environment(account="757884822287", region="eu-central-1")
)

app.synth()
