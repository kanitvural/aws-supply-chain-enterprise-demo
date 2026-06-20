import os
import json
import boto3
import time

bedrock = boto3.client('bedrock')
sns = boto3.client('sns')

def lambda_handler(event, context):
    s3_bucket = os.environ.get('MLOPS_BUCKET')
    sns_topic = os.environ.get('SNS_TOPIC_ARN')
    role_arn = os.environ.get('EVAL_ROLE_ARN')
    
    if not all([s3_bucket, sns_topic, role_arn]):
        raise ValueError("Missing required environment variables.")
        
    job_name = f"sc-weekly-eval-{int(time.time())}"
    
    try:
        # Note: Bedrock CreateEvaluationJob API signature can be complex.
        # This is a representative configuration for an automated evaluation job.
        response = bedrock.create_evaluation_job(
            jobName=job_name,
            jobDescription='Weekly automated evaluation of Supply Chain RAG Agent',
            roleArn=role_arn,
            evaluationConfig={
                'automated': {
                    'datasetMetricConfigs': [
                        {
                            'taskType': 'QuestionAndAnswer',
                            'dataset': {
                                'name': 'rag_golden',
                                'datasetLocation': {
                                    's3Uri': f's3://{s3_bucket}/golden_datasets/rag_golden.jsonl'
                                }
                            },
                            'metricNames': ['Correctness', 'Faithfulness']
                        }
                    ]
                }
            },
            inferenceConfig={
                'models': [
                    {'bedrockModel': {'modelIdentifier': 'amazon.nova-lite-v1:0'}}
                ]
            },
            outputDataConfig={
                's3Uri': f's3://{s3_bucket}/evaluation_results/'
            }
        )
        
        # Notify success via SNS
        sns.publish(
            TopicArn=sns_topic,
            Subject="Supply Chain LLMOps: Evaluation Started",
            Message=f"Automated evaluation job '{job_name}' has successfully started.\nResults will be saved to s3://{s3_bucket}/evaluation_results/"
        )
        return {"statusCode": 200, "body": json.dumps({"message": "Evaluation started successfully.", "job_name": job_name})}
        
    except Exception as e:
        print(f"Error starting evaluation: {e}")
        sns.publish(
            TopicArn=sns_topic,
            Subject="Supply Chain LLMOps: Evaluation FAILED to start",
            Message=f"Failed to start evaluation job {job_name}.\nError: {str(e)}"
        )
        raise e
