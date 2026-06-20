# AWS Supply Chain Enterprise AI Assistant

![Architecture Diagram](agent_core/images/diagram.png)

This project demonstrates a fully functional, enterprise-grade Supply Chain AI Assistant powered by **Amazon Bedrock AgentCore**. It uses a self-mutating AWS CDK CodePipeline to deploy the entire infrastructure securely and scalably into your AWS environment.

## 📦 What Business Problem Does This Solve?

Global supply chains are incredibly complex. Logistics managers, inventory specialists, and quality control officers deal with scattered data across multiple databases, manuals, and tracking systems. When an issue occurs (e.g., a shipment delay or a quality standard failure), it takes hours to trace the impact.

**This AI Assistant acts as an intelligent "Supply Chain Co-Pilot".** 
Through a simple chat interface, users can ask natural language questions like:
* *"Where is the shipment for order #12345, and what is its current status?"*
* *"Which suppliers provide raw material X, and what is their quality compliance score?"*
* *"If route A is blocked by a storm, what are my alternative logistics routes?"*
* *"What is our corporate policy regarding defective inventory returns?"*

The AI doesn't just guess; it **takes action** using specialized tools. It fetches real-time data from databases (Inventory, Logistics, Suppliers) and reads thousands of pages of corporate manuals using RAG (Knowledge Base).

---

## 🏗️ Enterprise Architecture & Security

To make this system ready for a Fortune 500 company, we built a highly secure, scalable, and isolated architecture:

* **Private Network (VPC & PrivateLink)**: The AI agents run inside a strictly controlled Virtual Private Cloud (VPC). They use AWS PrivateLink (VPC Interface Endpoints) to communicate with Amazon Bedrock, CloudWatch, and S3. This means **data never travels over the public internet**, shielding it from external threats.
* **100% Data Privacy & Model Choice**: Because the system is built on Amazon Bedrock, enterprise data is never used to train base foundation models. While we default to Amazon Nova, the architecture natively supports Anthropic's **Claude** family. Thanks to AWS's secure infrastructure, using Claude models does not require sending data out to third-party APIs over the internet; everything executes securely within your private AWS boundary.
* **M2M Authentication (Cognito)**: The chat application uses Amazon Cognito with a Machine-to-Machine (M2M) `client_credentials` flow. Every request between components is verified via JWT tokens with strict `supplychain/read` and `supplychain/write` scopes.
* **MCP (Model Context Protocol) Gateway**: Instead of giving the AI direct, unchecked access to the databases, we route all AI tool requests through the **AgentCore Gateway**. The Gateway validates the AI's requests against strict JSON schemas before triggering isolated Lambda functions.
* **Data Protection (Guardrails)**: We implemented Amazon Bedrock Guardrails to prevent data leaks. It automatically blocks inappropriate content, masks PII (like passwords), and anonymizes sensitive corporate data (like internal discount codes). It even strictly blocks mentions of confidential internal projects.
* **Agentic Memory**: The system uses AgentCore Memory namespaces to separate user preferences, factual semantic memory, and session summaries, meaning the AI remembers context across multiple sessions.
* **Self-Mutating CI/CD Pipeline**: Everything is defined as Infrastructure as Code (AWS CDK). The system automatically tests and deploys itself via CodePipeline on every GitHub commit.

---

## 🛠️ Architecture Stack

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

---

## 🧠 Multi-Agent System & Tools

At the core of this assistant is a **Multi-Agent Architecture**, splitting complex workflows between specialized AI models to optimize for both cost and reasoning power.

### 1. The Orchestrator Agent (Amazon Nova Pro)
The Orchestrator is the "brain" of the system. It talks directly to the user, understands the intent, plans the steps required to answer the question, and routes requests to the correct tools.
* **Why Nova Pro?** Because orchestrating multiple tools, reasoning through complex supply chain problems (e.g., "If shipment X is late, what are my alternatives?"), and maintaining conversational memory requires a highly capable, top-tier foundation model with advanced reasoning and planning skills.

### 2. MCP Tools & Lambda Handlers
When the Orchestrator needs real-world data, it cannot query databases directly. It uses tools defined by the Model Context Protocol (MCP) Gateway. Each tool triggers a specific AWS Lambda function, which then securely queries its designated DynamoDB tables:
* **Inventory Tool** ➡️ `Inventory Lambda` ➡️ Queries `sc-inventory`
* **Logistics Tool** ➡️ `Logistics Lambda` ➡️ Queries `sc-shipments` and `sc-routes`
* **Supplier Tool** ➡️ `Supplier Lambda` ➡️ Queries `sc-suppliers`
* **Quality Tool** ➡️ `Quality Lambda` ➡️ Queries `sc-inspections`, `sc-compliance`, and `sc-standards`

### 3. The Knowledge Base Specialist Agent (Amazon Nova Lite)
When a user asks about corporate policies, contracts, or procedural guidelines (which are not in databases but in PDF/Text documents), the Orchestrator delegates the task to the **KB Specialist Agent**. This agent uses Retrieval-Augmented Generation (RAG) to search the **Amazon OpenSearch Serverless** vector database, which contains synced manuals from S3.
* **Why Nova Lite?** The Specialist Agent has a single, focused job: read a retrieved chunk of text and summarize it accurately. It doesn't need to do complex tool routing. Nova Lite is exceptionally fast and cost-effective, making it the perfect model for high-speed, straightforward reading and summarization tasks.

---

## 🗄️ DynamoDB Data Architecture

The project deploys 7 DynamoDB tables that act as the single source of truth for the AI Assistant. In a real-world enterprise, these tables would be continuously updated via streaming data from ERP systems (e.g., SAP), Warehouse Management Systems (WMS), and IoT sensors on shipping containers.

1. **`sc-inventory`**: Tracks product stock, warehouse locations, and reorder thresholds.
2. **`sc-shipments`**: Holds active tracking numbers, estimated time of arrival (ETA), and carrier statuses.
3. **`sc-routes`**: Maps logistics routes, distances, and current conditions (e.g., weather delays).
4. **`sc-suppliers`**: Contains supplier profiles, tier ratings, and contact information.
5. **`sc-inspections`**: Stores quality control reports for specific product batches (Passed/Failed).
6. **`sc-compliance`**: Tracks environmental and manufacturing certifications (e.g., ISO-9001, CE, RoHS).
7. **`sc-standards`**: Defines strict corporate thresholds and rules (e.g., maximum acceptable noise levels for motors).

---

## 📚 Knowledge Base & Vector Store (RAG)

While DynamoDB handles structured, real-time metrics, a supply chain is also governed by thousands of pages of unstructured documents. To process these, we built a highly scalable Retrieval-Augmented Generation (RAG) pipeline:

### 1. The Data Lake (Amazon S3)
* **Corporate Manuals**: PDFs, text files, and guidelines detailing quality audits, return policies, and supplier rules.
* **OpenAPI Schemas**: Strict JSON schemas that the AgentCore Gateway uses to validate the AI's tool requests.

### 2. The Vector Database (Amazon OpenSearch Serverless)
Whenever a document is uploaded to S3, it is automatically chunked and converted into vector embeddings using the **Amazon Titan Text Embeddings** model. These vectors are stored in an **Amazon OpenSearch Serverless** collection.

**Why OpenSearch Serverless?**
* **Zero Infrastructure Management**: Unlike traditional OpenSearch clusters, Serverless requires no node provisioning, patching, or capacity planning. It auto-scales compute instantly based on search query volume.
* **Cost-Effective for AI Workloads**: In an AI Assistant, vector search traffic is highly unpredictable (bursty). With Serverless, you only pay for the active compute resources consumed during queries and ingestion, eliminating the high costs of idle clusters.
* **Native Bedrock Integration**: It serves as a seamless, fully-managed vector store backend for Amazon Bedrock Knowledge Bases, allowing the KB Specialist Agent to search securely without us having to write complex vector-math code.

---

## 🚀 Deployment Instructions

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
Currently, the DynamoDB tables are deployed empty. To add sample data to `sc-inventory`, `sc-shipments`, etc. and test the AI immediately, run the included mock data script:

```bash
python3 scripts/load_mock_data_to_dynamodb_tables.py
```
This script will populate all 7 tables with dummy data (products, delayed shipments, suppliers, etc.) so the AI has real scenarios to interact with.

---

## 🗑️ Destroying the Infrastructure

To remove the CodePipeline:
```bash
make destroy
```
Then, go to the AWS CloudFormation Console and manually delete the `SupplyChainStage` stacks.
