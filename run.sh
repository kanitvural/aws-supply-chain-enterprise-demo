#!/bin/bash

# Automatically fetch AWS account ID and region from AWS CLI config
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region)

bootstrap() {
  echo "🔹 Bootstrapping environment (Account: $ACCOUNT_ID, Region: $REGION)"
  cdk bootstrap \
    --context @aws-cdk/core:bootstrapQualifier=sc \
    --qualifier sc \
    --toolkit-stack-name CDKToolkit-SC \
    aws://$ACCOUNT_ID/$REGION
}

synth() {
  echo "🛠️  Synthesizing CloudFormation templates..."
  cdk synth \
    --context @aws-cdk/core:bootstrapQualifier=sc
}

deploy() {
  echo "🚀 Deploying SupplyChainPipeline (Account: $ACCOUNT_ID, Region: $REGION)"
  cdk deploy SupplyChainPipeline \
    --context @aws-cdk/core:bootstrapQualifier=sc \
    --require-approval never
}

destroy() {
  echo "⚠️ Destroying SupplyChainPipeline (Account: $ACCOUNT_ID, Region: $REGION)"
  cdk destroy SupplyChainPipeline \
    --context @aws-cdk/core:bootstrapQualifier=sc \
    --force
}

# --- Dispatcher ---
action=$1

if [[ "$action" == "bootstrap" ]]; then
    bootstrap
elif [[ "$action" == "synth" ]]; then
    synth
elif [[ "$action" == "deploy" ]]; then
    deploy
elif [[ "$action" == "destroy" ]]; then
    destroy
else
    echo "❌ Invalid action! Use: bootstrap, synth, deploy, or destroy"
    exit 1
fi
