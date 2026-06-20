import boto3
import sys

def main():
    print("Starting Bedrock Knowledge Base Ingestion Sync...")
    # The pipeline step might not have a default region set depending on environment, so it's safer to specify.
    client = boto3.client('bedrock-agent', region_name='eu-central-1')
    
    # 1. Find KB ID
    kbs = client.list_knowledge_bases(maxResults=100).get('knowledgeBaseSummaries', [])
    kb_id = None
    for kb in kbs:
        if kb['name'] == 'supply-chain-kb':
            kb_id = kb['knowledgeBaseId']
            break
            
    if not kb_id:
        print("Error: Knowledge Base 'supply-chain-kb' not found.")
        sys.exit(1)
        
    print(f"Found Knowledge Base ID: {kb_id}")
    
    # 2. Find Data Source ID
    data_sources = client.list_data_sources(knowledgeBaseId=kb_id, maxResults=100).get('dataSourceSummaries', [])
    if not data_sources:
        print("Error: No data sources found for this Knowledge Base.")
        sys.exit(1)
        
    ds_id = data_sources[0]['dataSourceId']
    print(f"Found Data Source ID: {ds_id}")
    
    # 3. Start Ingestion Job
    try:
        response = client.start_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            description='Automated Post-Deployment Sync'
        )
        print(f"Successfully started ingestion job: {response['ingestionJob']['ingestionJobId']}")
    except Exception as e:
        print(f"Error starting ingestion job: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
