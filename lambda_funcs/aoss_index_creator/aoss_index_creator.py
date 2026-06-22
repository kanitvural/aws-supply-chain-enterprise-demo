import json
import boto3
import urllib.request
import time
import hashlib
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

def handler(event, context):
    print("Received event:", json.dumps(event))
    request_type = event['RequestType']
    
    # We only create/update. On delete, we just return success without deleting the index
    # since destroying the collection will wipe the index anyway.
    if request_type == 'Delete':
        return {'PhysicalResourceId': event.get('PhysicalResourceId', 'aoss-index')}
    
    props = event['ResourceProperties']
    host = props['CollectionEndpoint'].replace('https://', '')
    region = props['Region']
    index_name = props['IndexName']
    
    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()
    
    url = f"https://{host}/{index_name}"
    
    # Titan Embed Text v2 uses 1024 dimensions by default
    payload = {
        "settings": {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 512
            }
        },
        "mappings": {
            "properties": {
                "bedrock-knowledge-base-default-vector": {
                    "type": "knn_vector",
                    "dimension": 1024,
                    "method": {
                        "name": "hnsw",
                        "engine": "faiss",
                        "space_type": "cosinesimil"
                    }
                }
            }
        }
    }
    
    payload_bytes = json.dumps(payload).encode('utf-8')
    request = AWSRequest(method="PUT", url=url, data=payload_bytes)
    
    # OpenSearch Serverless strictly requires the x-amz-content-sha256 header
    request.headers['Content-Type'] = 'application/json'
    request.headers['x-amz-content-sha256'] = hashlib.sha256(payload_bytes).hexdigest()
    
    SigV4Auth(credentials, "aoss", region).add_auth(request)
    
    req = urllib.request.Request(url, data=request.body, headers=dict(request.headers), method="PUT")
    
    max_retries = 40
    for attempt in range(max_retries):
        try:
            response = urllib.request.urlopen(req)
            print("Response:", response.read().decode('utf-8'))
            break
        except urllib.error.HTTPError as e:
            err = e.read().decode('utf-8')
            print(f"HTTPError on attempt {attempt+1}: {err}")
            # Ignore resource_already_exists_exception during updates
            if 'resource_already_exists_exception' in err:
                break
            
            # AOSS Data Access policies take time to propagate. Retry on 403.
            if e.code == 403 and attempt < max_retries - 1:
                print("Got 403 Forbidden. Access policy might not have propagated yet. Retrying in 15 seconds...")
                time.sleep(15)
                continue
                
            raise Exception(f"Failed to create index: {err}")
            
    print("Index creation command accepted. Waiting 120 seconds for AOSS propagation...")
    time.sleep(120)
    
    return {'PhysicalResourceId': f"{host}/{index_name}"}
