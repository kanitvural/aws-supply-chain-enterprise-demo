import aws_cdk as core
import aws_cdk.assertions as assertions

from aws_supply_chain_enterprise_demo.aws_supply_chain_enterprise_demo_stack import AwsSupplyChainEnterpriseDemoStack

# example tests. To run these tests, uncomment this file along with the example
# resource in aws_supply_chain_enterprise_demo/aws_supply_chain_enterprise_demo_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = AwsSupplyChainEnterpriseDemoStack(app, "aws-supply-chain-enterprise-demo")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
