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
  echo "⚠️ Destroying SupplyChainPipeline and all deployed Prod-* Stacks (Account: $ACCOUNT_ID, Region: $REGION)"
  
  # List of Prod stacks in REVERSE order of their dependencies
  STACKS_TO_DELETE=(
    "Prod-CloudFrontStack"
    "Prod-ApiGatewayStack"
    "Prod-AgentCoreStack"
    "Prod-LambdaStack"
    "Prod-MlopsEvalStack"
    "Prod-GuardrailsStack"
    "Prod-DynamoDbStack"
    "Prod-S3AssetsStack"
    "Prod-CognitoStack"
    "Prod-VpcStack"
    "Prod-CloudWatchDashboardStack"
  )

  for stack in "${STACKS_TO_DELETE[@]}"; do
    echo "🗑️ Deleting stack: $stack..."
    aws cloudformation delete-stack --stack-name $stack --region $REGION
  done

  echo "⏳ Waiting for Prod-* stacks to be deleted..."
  for stack in "${STACKS_TO_DELETE[@]}"; do
    aws cloudformation wait stack-delete-complete --stack-name $stack --region $REGION 2>/dev/null || true
    echo "✅ Deleted $stack"
  done

  echo "🧹 Emptying Pipeline Artifacts Bucket..."
  # Find the pipeline artifacts bucket and empty it before destroying
  PIPELINE_BUCKET=$(aws s3api list-buckets --query "Buckets[?contains(Name, 'supplychainpipeline') && contains(Name, 'artifact')].Name" --output text 2>/dev/null || echo "")
  if [[ -n "$PIPELINE_BUCKET" && "$PIPELINE_BUCKET" != "None" ]]; then
    for bucket in $PIPELINE_BUCKET; do
      echo "   -> Emptying $bucket"
      python3 -c "import boto3; s3=boto3.resource('s3'); b=s3.Bucket('$bucket'); b.object_versions.delete()" 2>/dev/null || true
    done
  fi

  echo "⚠️ Destroying the Pipeline stack itself..."
  cdk destroy --all \
    --context @aws-cdk/core:bootstrapQualifier=sc \
    --force

  echo "⚠️ Destroying CDKToolkit-SC (Bootstrap environment)..."
  
  # Find the S3 bucket and ECR repo specific to this SC qualifier
  CDK_BUCKET=$(aws cloudformation describe-stacks --stack-name CDKToolkit-SC --region $REGION --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" --output text 2>/dev/null || echo "")
  CDK_ECR=$(aws cloudformation describe-stack-resource --stack-name CDKToolkit-SC --logical-resource-id ContainerAssetsRepository --region $REGION --query "StackResourceDetail.PhysicalResourceId" --output text 2>/dev/null || echo "")

  if [[ -n "$CDK_BUCKET" && "$CDK_BUCKET" != "None" ]]; then
    echo "🧹 Emptying CDK Toolkit S3 Bucket: $CDK_BUCKET"
    # Delete all objects and versions
    aws s3 rm s3://$CDK_BUCKET --recursive 2>/dev/null || true
    # Python one-liner to delete all object versions securely
    python3 -c "import boto3; s3=boto3.resource('s3'); b=s3.Bucket('$CDK_BUCKET'); b.object_versions.delete()" 2>/dev/null || true
  fi

  if [[ -n "$CDK_ECR" && "$CDK_ECR" != "None" ]]; then
    echo "🧹 Emptying CDK Toolkit ECR Repository: $CDK_ECR"
    # Python one-liner to delete all ECR images
    python3 -c "import boto3; c=boto3.client('ecr', region_name='$REGION'); imgs=c.list_images(repositoryName='$CDK_ECR').get('imageIds',[]); c.batch_delete_image(repositoryName='$CDK_ECR', imageIds=imgs) if imgs else None" 2>/dev/null || true
  fi

  echo "🗑️ Deleting stack: CDKToolkit-SC..."
  aws cloudformation delete-stack --stack-name CDKToolkit-SC --region $REGION
  aws cloudformation wait stack-delete-complete --stack-name CDKToolkit-SC --region $REGION 2>/dev/null || true
  echo "✅ Deleted CDKToolkit-SC"
  echo "🎉 Environment is now 100% clean!"
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
