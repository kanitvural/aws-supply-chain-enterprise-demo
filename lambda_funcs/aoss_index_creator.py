import json
import boto3
import urllib.request
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
                        "engine": "nmslib",
                        "space_type": "cosinesimil"
                    }
                },
                "AMAZON_BEDROCK_METADATA": {
                    "type": "text",
                    "index": False
                },
                "AMAZON_BEDROCK_TEXT_CHUNK": {
                    "type": "text"
                },
                "id": {
                    "type": "keyword"
                }
            }
        }
    }
    
    request = AWSRequest(method="PUT", url=url, data=json.dumps(payload).encode('utf-8'))
    SigV4Auth(credentials, "aoss", region).add_auth(request)
    
    req = urllib.request.Request(url, data=request.body, headers=dict(request.headers), method="PUT")
    
    try:
        response = urllib.request.urlopen(req)
        print("Response:", response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8')
        print(f"HTTPError: {err}")
        # Ignore resource_already_exists_exception during updates
        if 'resource_already_exists_exception' not in err:
            raise Exception(f"Failed to create index: {err}")
            
    return {'PhysicalResourceId': f"{host}/{index_name}"}
