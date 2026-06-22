"""AgentCore Stack — Orchestrator, KB Specialist, Gateway, Memory, and Knowledge Base.

Deploys:
  - OpenSearch Serverless (AOSS) Collection + Index Custom Resource
  - Bedrock Knowledge Base + S3 Data Source
  - AgentCore Memory
  - KB Specialist Agent Runtime (Nova Lite)
  - Orchestrator Agent Runtime (Nova Pro)
  - AgentCore Gateway with 4 Lambda targets
"""

import json
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CustomResource,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_opensearchserverless as aoss,
    aws_bedrock as bedrock,
    aws_bedrockagentcore as agentcore,
    aws_ec2 as ec2,
    aws_s3 as s3,
    aws_cognito as cognito,
    custom_resources as cr,
    CfnOutput,
)
from constructs import Construct


class AgentCoreStack(Stack):
    """Core AI services layer."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        vpc: ec2.IVpc,
        security_group_id: str,
        assets_bucket: s3.IBucket,
        user_pool: cognito.IUserPool,
        app_client: cognito.IUserPoolClient,
        cognito_domain_url: str,
        guardrail_id: str,
        guardrail_version: str,
        inventory_lambda: lambda_.IFunction,
        logistics_lambda: lambda_.IFunction,
        supplier_lambda: lambda_.IFunction,
        quality_lambda: lambda_.IFunction,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # ------------------------------------------------------------------
        # Roles for Knowledge Base & OpenSearch Custom Resource
        # ------------------------------------------------------------------
        kb_role = iam.Role(
            self,
            "KnowledgeBaseRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
        )
        assets_bucket.grant_read(kb_role)
        kb_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0"],
        ))
        
        cr_role = iam.Role(
            self,
            "AossIndexCreatorRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")],
        )

        # ------------------------------------------------------------------
        # OpenSearch Serverless (AOSS) Collection
        # ------------------------------------------------------------------
        collection = aoss.CfnCollection(
            self,
            "SupplyChainKbCollection",
            name="supply-chain-kb-collection",
            type="VECTORSEARCH",
        )

        # Encryption policy
        enc_policy = aoss.CfnSecurityPolicy(
            self,
            "AossEncryptionPolicy",
            name="supply-chain-kb-enc",
            type="encryption",
            policy=json.dumps({
                "Rules": [
                    {"ResourceType": "collection", "Resource": [f"collection/{collection.name}"]}
                ],
                "AWSOwnedKey": True
            })
        )
        collection.add_dependency(enc_policy)

        # Network policy
        net_policy = aoss.CfnSecurityPolicy(
            self,
            "AossNetworkPolicy",
            name="supply-chain-kb-net",
            type="network",
            policy=json.dumps([
                {
                    "Rules": [
                        {"ResourceType": "collection", "Resource": [f"collection/{collection.name}"]},
                        {"ResourceType": "dashboard", "Resource": [f"collection/{collection.name}"]}
                    ],
                    "AllowFromPublic": True
                }
            ])
        )
        collection.add_dependency(net_policy)

        # Data Access policy
        access_policy = aoss.CfnAccessPolicy(
            self,
            "AossDataAccessPolicy",
            name="supply-chain-kb-acc",
            type="data",
            policy=json.dumps([
                {
                    "Rules": [
                        {
                            "ResourceType": "collection",
                            "Resource": [f"collection/{collection.name}"],
                            "Permission": ["aoss:CreateCollectionItems", "aoss:DeleteCollectionItems", "aoss:UpdateCollectionItems", "aoss:DescribeCollectionItems"]
                        },
                        {
                            "ResourceType": "index",
                            "Resource": [f"index/{collection.name}/*"],
                            "Permission": ["aoss:CreateIndex", "aoss:DeleteIndex", "aoss:UpdateIndex", "aoss:DescribeIndex", "aoss:ReadDocument", "aoss:WriteDocument"]
                        }
                    ],
                    "Principal": [
                        kb_role.role_arn,
                        cr_role.role_arn,
                        f"arn:aws:iam::{self.account}:user/admin"
                    ]
                }
            ])
        )

        # ------------------------------------------------------------------
        # Create OpenSearch Index via Custom Resource
        # ------------------------------------------------------------------
        cr_role.add_to_policy(iam.PolicyStatement(
            actions=["aoss:APIAccessAll"],
            resources=["*"]
        ))
        
        index_creator_fn = lambda_.Function(
            self,
            "AossIndexCreatorFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="aoss_index_creator.handler",
            code=lambda_.Code.from_asset("lambda_funcs/aoss_index_creator"),
            role=cr_role,
            timeout=Duration.minutes(14),
        )
        
        index_creator_provider = cr.Provider(
            self,
            "AossIndexCreatorProvider",
            on_event_handler=index_creator_fn,
        )
        
        index_creation = CustomResource(
            self,
            "AossIndexCreation",
            service_token=index_creator_provider.service_token,
            properties={
                "CollectionEndpoint": collection.attr_collection_endpoint,
                "Region": self.region,
                "IndexName": "supply-chain-kb-index-v2",
            }
        )
        index_creation.node.add_dependency(access_policy)
        index_creation.node.add_dependency(collection)

        # ------------------------------------------------------------------
        # Bedrock Knowledge Base & Data Source
        # ------------------------------------------------------------------
        kb_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "aoss:APIAccessAll",
                "bedrock:InvokeModel",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            resources=["*"]
        ))

        knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "SupplyChainKnowledgeBase",
            name="supply-chain-kb",
            role_arn=kb_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0"
                )
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="OPENSEARCH_SERVERLESS",
                opensearch_serverless_configuration=bedrock.CfnKnowledgeBase.OpenSearchServerlessConfigurationProperty(
                    collection_arn=collection.attr_arn,
                    field_mapping=bedrock.CfnKnowledgeBase.OpenSearchServerlessFieldMappingProperty(
                        vector_field="bedrock-knowledge-base-default-vector",
                        text_field="AMAZON_BEDROCK_TEXT_CHUNK",
                        metadata_field="AMAZON_BEDROCK_METADATA"
                    ),
                    vector_index_name="supply-chain-kb-index-v2"
                )
            )
        )
        knowledge_base.node.add_dependency(index_creation)

        data_source = bedrock.CfnDataSource(
            self,
            "SupplyChainDataSource",
            name="supply-chain-kb-docs",
            knowledge_base_id=knowledge_base.attr_knowledge_base_id,
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=assets_bucket.bucket_arn,
                    inclusion_prefixes=["kb-docs/"]
                )
            )
        )

        # Store KB ID in SSM to break cyclic dependency with LambdaStack
        from aws_cdk import aws_ssm as ssm
        ssm.StringParameter(
            self,
            "KnowledgeBaseIdParam",
            parameter_name="/supplychain/kb_id",
            string_value=knowledge_base.attr_knowledge_base_id,
        )

        # ------------------------------------------------------------------
        # AgentCore: Memory with 3 namespace strategies
        # ------------------------------------------------------------------
        memory = agentcore.Memory(
            self,
            "SupplyChainMemory",
            memory_name="supply_chain_memory",
        )

        # Strategy 1: Semantic — cross-session factual knowledge
        memory.add_memory_strategy(
            agentcore.MemoryStrategy.using_semantic(
                strategy_name="semantic_memories",
                namespaces=["supplychain/user/{actorId}/semantic"],
            )
        )

        # Strategy 2: User Preference — name, preferences, style
        memory.add_memory_strategy(
            agentcore.MemoryStrategy.using_user_preference(
                strategy_name="user_preferences",
                namespaces=["supplychain/user/{actorId}/preferences"],
            )
        )

        # Strategy 3: Summarization — per-session conversation summary
        memory.add_memory_strategy(
            agentcore.MemoryStrategy.using_summarization(
                strategy_name="session_summaries",
                namespaces=["supplychain/user/{actorId}/session/{sessionId}/summary"],
            )
        )

        # ------------------------------------------------------------------
        # AgentCore: Network & Auth Common Config
        # ------------------------------------------------------------------
        sg = ec2.SecurityGroup.from_security_group_id(self, "AgentCoreSG", security_group_id)
        
        network_config = agentcore.RuntimeNetworkConfiguration.using_vpc(
            self,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[sg],
        )

        auth_config = agentcore.RuntimeAuthorizerConfiguration.using_cognito(
            user_pool=user_pool,
            user_pool_clients=[app_client],
        )

        # ------------------------------------------------------------------
        # AgentCore: KB Specialist Runtime (Nova Lite)
        # ------------------------------------------------------------------
        kb_specialist_artifact = agentcore.AgentRuntimeArtifact.from_asset("agent_core/kb_specialist_agent")
        
        kb_runtime = agentcore.Runtime(
            self,
            "KbSpecialistRuntime",
            runtime_name="kb_specialist",
            agent_runtime_artifact=kb_specialist_artifact,
            network_configuration=network_config,
            authorizer_configuration=auth_config,
            environment_variables={
                "MODEL_ID": "eu.amazon.nova-lite-v1:0",
                "KNOWLEDGE_BASE_ID": knowledge_base.attr_knowledge_base_id,
            }
        )
        kb_runtime.role.add_to_principal_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Retrieve"],
            resources=["*"],
        ))

        # ------------------------------------------------------------------
        # AgentCore: Gateway & MCP Targets
        # ------------------------------------------------------------------
        gateway = agentcore.Gateway(
            self,
            "SupplyChainGateway",
            gateway_name="supply-chain-gateway",
            authorizer_configuration=agentcore.GatewayAuthorizer.using_cognito(
                user_pool=user_pool,
                allowed_scopes=["supplychain/read", "supplychain/write"]
            ),
            exception_level=agentcore.GatewayExceptionLevel.DEBUG,
        )

        # Targets mapping to Lambda functions with S3 schemas
        def add_target(name: str, lambda_fn: lambda_.IFunction, schema_key: str):
            gateway.add_lambda_target(
                name,
                lambda_function=lambda_fn,
                tool_schema=agentcore.ToolSchema.from_s3_file(assets_bucket, schema_key)
            )

        add_target("inventory-target", inventory_lambda, "schemas/inventory_schema.json")
        add_target("logistics-target", logistics_lambda, "schemas/logistics_schema.json")
        add_target("supplier-target", supplier_lambda, "schemas/supplier_schema.json")
        add_target("quality-target", quality_lambda, "schemas/quality_schema.json")

        # ------------------------------------------------------------------
        # AgentCore: Orchestrator Runtime (Nova Pro)
        # ------------------------------------------------------------------
        orchestrator_artifact = agentcore.AgentRuntimeArtifact.from_asset("agent_core/orchestrator_agent")
        
        orchestrator_runtime = agentcore.Runtime(
            self,
            "OrchestratorRuntime",
            runtime_name="orchestrator",
            agent_runtime_artifact=orchestrator_artifact,
            network_configuration=network_config,
            authorizer_configuration=auth_config,
            environment_variables={
                "MODEL_ID": "eu.amazon.nova-pro-v1:0",
                "GATEWAY_URL": gateway.gateway_url,
                "MEMORY_ID": memory.memory_id,
                "GUARDRAIL_ID": guardrail_id,
                "GUARDRAIL_VERSION": guardrail_version,
                "KB_SPECIALIST_RUNTIME_ARN": kb_runtime.agent_runtime_arn,
                "COGNITO_DOMAIN": cognito_domain_url,
                "COGNITO_CLIENT_ID": app_client.user_pool_client_id,
                "COGNITO_USER_POOL_ID": user_pool.user_pool_id,
            }
        )
        orchestrator_runtime.role.add_to_principal_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:ApplyGuardrail",
                "bedrock-agentcore:InvokeAgentRuntime",
                "bedrock-agentcore:InvokeGateway",
                "bedrock-agentcore:GetMemory",
                "bedrock-agentcore:UpdateMemory",
                "bedrock-agentcore:DeleteMemory",
                "bedrock-agentcore:CreateMemory",
                "bedrock-agentcore:ListEvents",
                "bedrock-agentcore:GetEvent",
                "bedrock-agentcore:CreateEvent",
                "bedrock-agentcore:UpdateEvent",
                "bedrock-agentcore:DeleteEvent",
                "bedrock-agentcore:ListSessions",
                "bedrock-agentcore:GetSession",
                "bedrock-agentcore:CreateSession",
                "bedrock-agentcore:UpdateSession",
                "bedrock-agentcore:DeleteSession",
                "cognito-idp:DescribeUserPoolClient"
            ],
            resources=["*"],
        ))

        # ------------------------------------------------------------------
        # Chat Handler — bridges API Gateway <-> Orchestrator Agent
        # ------------------------------------------------------------------
        self.chat_lambda = lambda_.Function(
            self,
            "ChatLambda",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="supply-chain-chat.lambda_handler",
            code=lambda_.Code.from_asset("lambda_funcs/supply_chain_chat"),
            timeout=Duration.seconds(120),
            environment={
                "COGNITO_DOMAIN": cognito_domain_url,
                "COGNITO_CLIENT_ID": app_client.user_pool_client_id,
                "COGNITO_USER_POOL_ID": user_pool.user_pool_id,
                "ORCHESTRATOR_RUNTIME_ARN": orchestrator_runtime.agent_runtime_arn,
                "GATEWAY_URL": gateway.gateway_url,
                "MEMORY_ID": memory.memory_id,
                "GUARDRAIL_ID": guardrail_id,
                "KB_SPECIALIST_RUNTIME_ARN": kb_runtime.agent_runtime_arn,
                "VPC_ENABLED": "true",
            },
        )
        # Chat handler needs Cognito describe (to fetch client secret at runtime)
        self.chat_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cognito-idp:DescribeUserPoolClient"],
                resources=[user_pool.user_pool_arn],
            )
        )
        # AgentCore invocation + control plane for /status endpoint
        self.chat_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore-control:GetAgentRuntime",
                    "bedrock-agentcore-control:GetMemory",
                    "bedrock:GetGuardrail",
                ],
                resources=["*"],
            )
        )

        # ------------------------------------------------------------------
        # Outputs
        # ------------------------------------------------------------------
        CfnOutput(self, "OrchestratorRuntimeArn", value=orchestrator_runtime.agent_runtime_arn)
        CfnOutput(self, "GatewayEndpoint", value=gateway.gateway_url)
        CfnOutput(self, "KnowledgeBaseId", value=knowledge_base.attr_knowledge_base_id)
