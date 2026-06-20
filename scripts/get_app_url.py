import boto3
import sys

def get_cloudfront_url():
    print("🔍 Fetching KVural AI App URL from AWS...")
    client = boto3.client('cloudformation', region_name='eu-central-1')
    try:
        response = client.describe_stacks(StackName='DeployStage-CloudFrontStack')
        stacks = response.get('Stacks', [])
        if not stacks:
            print("❌ Stack DeployStage-CloudFrontStack not found. Make sure 'make deploy' has finished successfully.")
            return

        for output in stacks[0].get('Outputs', []):
            if output['OutputKey'] == 'CloudFrontURL':
                url = output['OutputValue']
                print("✅ Success! Your KVural AI application is live at:")
                print(f"🔗 {url}")
                return
                
        print("❌ Could not find CloudFrontURL in the stack outputs.")
    except Exception as e:
        print(f"❌ Error fetching stack: {e}")

if __name__ == "__main__":
    get_cloudfront_url()
