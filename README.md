# AWS Supply Chain Enterprise Demo

This project demonstrates a fully functional, enterprise-grade Supply Chain AI Assistant powered by **Amazon Bedrock AgentCore**. It uses a self-mutating AWS CDK CodePipeline to deploy the entire infrastructure securely and scalably into your AWS environment.

## Architecture

The project consists of 9 CDK stacks deployed sequentially via CodePipeline:
1. **VPC Stack**: Private and public subnets, NAT Gateway, and required VPC Endpoints.
2. **DynamoDB Stack**: 7 tables for Inventory, Shipments, Routes, Suppliers, Inspections, Compliance, and Standards.
3. **S3 Assets Stack**: S3 Bucket for Open API schemas and Knowledge Base text documents.
4. **Cognito Stack**: User Pool with M2M client_credentials flow for API Gateway to Agent auth.
5. **Guardrails Stack**: Amazon Bedrock Guardrail for PII filtering, regex masking, and profanity blocking.
6. **Lambda Stack**: 5 AWS Lambda functions (1 Chat API handler + 4 Domain handlers for Agent MCP tools).
7. **API Gateway Stack**: REST API exposing endpoints to the frontend.
8. **CloudFront Stack**: Secure frontend delivery with Origin Access Control (OAC).
9. **AgentCore Stack**: OpenSearch Serverless collection, Knowledge Base, Memory, Gateway, and 2 containerized AgentCore Runtimes (Orchestrator and KB Specialist).

## Deployment Instructions

Ensure you have your AWS CLI configured with administrator privileges.

### 1. Bootstrap your environment
You only need to do this once for your account/region combination:
```bash
make bootstrap
```

### 2. Commit your code
Because this project uses a self-mutating CodePipeline with GitHub (via CodeConnections), you must commit and push your changes to the `main` branch:
```bash
git add .
git commit -m "Initial commit for Supply Chain CI/CD"
git push origin main
```

### 3. Deploy the pipeline
Deploy the pipeline stack. Once deployed, the pipeline will automatically pull from GitHub and deploy the remaining 9 stacks.
```bash
make deploy
```

### 4. Sync Knowledge Base (Required)
The S3 bucket will automatically contain your `knowledge_base_docs`, and the Bedrock Knowledge Base is created automatically. However, the data ingestion (sync) is **not automatic**.
After the deployment succeeds, you must manually sync the files into the OpenSearch vector database:
1. Go to the AWS Console -> **Amazon Bedrock**.
2. Navigate to **Knowledge Bases** and select `supply-chain-kb`.
3. Scroll down to **Data Source** and click the **Sync** button.

### 5. Seed Data (Optional)
Currently, the DynamoDB tables are deployed empty. To add sample data to `sc-inventory`, `sc-shipments`, etc., you can write a short Python script to populate the tables.

## Destroying the Infrastructure

To remove the CodePipeline:
```bash
make destroy
```
Then, go to the AWS CloudFormation Console and manually delete the `SupplyChainStage` stacks.
