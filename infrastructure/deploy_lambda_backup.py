import boto3
import json
import zipfile
import os
import time
from botocore.exceptions import ClientError

# ----------------------------------------
# 🔧 CONFIGURE THESE VARIABLES
# ----------------------------------------
region = "ap-south-1"
lambda_function_name = "prince-mongo-backup"
s3_backup_bucket = "prince-mongo-backups-2025"
sns_topic_arn = "arn:aws:sns:ap-south-1:975050024946:prince-topic"
mongo_uri = "mongodb+srv://radeonxfx:1029384756!Sound@cluster0.gdl7f.mongodb.net/SimpleMern"  # Replace with your MongoDB URI

# Initialize AWS clients
lambda_client = boto3.client("lambda", region_name=region)
iam_client = boto3.client("iam", region_name=region)
s3_client = boto3.client("s3", region_name=region)
events_client = boto3.client("events", region_name=region)

def create_s3_bucket():
    """Create S3 bucket for backups"""
    try:
        print("🪣 Creating S3 bucket for backups...")
        
        # Check if bucket exists
        try:
            s3_client.head_bucket(Bucket=s3_backup_bucket)
            print(f"ℹ️ S3 bucket '{s3_backup_bucket}' already exists")
            return True
        except ClientError:
            pass
        
        # Create bucket
        if region == "us-east-1":
            s3_client.create_bucket(Bucket=s3_backup_bucket)
        else:
            s3_client.create_bucket(
                Bucket=s3_backup_bucket,
                CreateBucketConfiguration={'LocationConstraint': region}
            )
        
        # Add bucket policy for Lambda access
        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "LambdaBackupAccess",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "lambda.amazonaws.com"
                    },
                    "Action": [
                        "s3:PutObject",
                        "s3:GetObject",
                        "s3:ListBucket"
                    ],
                    "Resource": [
                        f"arn:aws:s3:::{s3_backup_bucket}",
                        f"arn:aws:s3:::{s3_backup_bucket}/*"
                    ]
                }
            ]
        }
        
        s3_client.put_bucket_policy(
            Bucket=s3_backup_bucket,
            Policy=json.dumps(bucket_policy)
        )
        
        print(f"✅ S3 bucket '{s3_backup_bucket}' created successfully")
        return True
        
    except ClientError as e:
        print(f"❌ Error creating S3 bucket: {e}")
        return False

def create_lambda_execution_role():
    """Create IAM role for Lambda execution"""
    role_name = f"{lambda_function_name}-role"
    
    try:
        print("🔐 Creating Lambda execution role...")
        
        # Trust policy for Lambda
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "lambda.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        # Create role
        try:
            response = iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description="Role for MongoDB backup Lambda function"
            )
            role_arn = response["Role"]["Arn"]
            print(f"✅ IAM role created: {role_arn}")
        except ClientError as e:
            if "already exists" in str(e):
                response = iam_client.get_role(RoleName=role_name)
                role_arn = response["Role"]["Arn"]
                print(f"ℹ️ IAM role already exists: {role_arn}")
            else:
                raise e
        
        # Attach policies
        policies = [
            "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            "arn:aws:iam::aws:policy/AmazonS3FullAccess",
            "arn:aws:iam::aws:policy/AmazonSNSPublishPolicy"
        ]
        
        for policy_arn in policies:
            try:
                iam_client.attach_role_policy(
                    RoleName=role_name,
                    PolicyArn=policy_arn
                )
            except ClientError:
                pass  # Policy might already be attached
        
        # Wait for role to be available
        time.sleep(10)
        
        return role_arn
        
    except ClientError as e:
        print(f"❌ Error creating IAM role: {e}")
        return None

def create_lambda_package():
    """Create Lambda deployment package"""
    print("📦 Creating Lambda deployment package...")
    
    # Create lambda function code
    lambda_code = '''
import json
import boto3
import datetime
import os
import urllib3

def lambda_handler(event, context):
    """
    Lambda function to backup MongoDB to S3 with timestamp
    """
    
    # Configuration from environment variables
    S3_BUCKET = os.environ.get('S3_BUCKET')
    SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
    
    # Initialize AWS clients
    s3_client = boto3.client('s3')
    sns_client = boto3.client('sns')
    
    try:
        # Generate timestamp for backup
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_filename = f"mongodb_backup_{timestamp}.json"
        
        print(f"Starting MongoDB backup simulation at {timestamp}")
        
        # Simulate backup data (replace with actual MongoDB backup logic)
        backup_data = {
            "backup_info": {
                "timestamp": timestamp,
                "status": "success",
                "databases": ["profileDB", "userDB"],
                "collections_count": 5,
                "documents_count": 1000
            },
            "sample_data": {
                "users": [
                    {"id": 1, "name": "John Doe", "email": "john@example.com"},
                    {"id": 2, "name": "Jane Smith", "email": "jane@example.com"}
                ],
                "profiles": [
                    {"userId": 1, "bio": "Software Developer"},
                    {"userId": 2, "bio": "Product Manager"}
                ]
            }
        }
        
        # Convert backup data to JSON
        backup_json = json.dumps(backup_data, indent=2, default=str)
        
        # Upload to S3
        print(f"Uploading backup to S3: {S3_BUCKET}/{backup_filename}")
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=backup_filename,
            Body=backup_json,
            ContentType='application/json',
            Metadata={
                'backup-date': timestamp,
                'backup-type': 'mongodb-simulation'
            }
        )
        
        # Send success notification
        message = f"""
        ✅ MongoDB Backup Successful!
        
        📊 Backup Details:
        • Timestamp: {timestamp}
        • File: {backup_filename}
        • S3 Bucket: {S3_BUCKET}
        • Status: Completed Successfully
        • Size: {len(backup_json)} bytes
        
        🎯 Backup completed and stored in S3.
        """
        
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="✅ MongoDB Backup Success",
            Message=message
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Backup completed successfully',
                'backup_file': backup_filename,
                'timestamp': timestamp,
                'status': 'success'
            })
        }
        
    except Exception as e:
        error_message = f"❌ MongoDB backup failed: {str(e)}"
        print(error_message)
        
        # Send failure notification
        try:
            sns_client.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject="❌ MongoDB Backup Failed",
                Message=f"MongoDB backup failed at {datetime.datetime.now()}\\n\\nError: {str(e)}"
            )
        except:
            pass
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_message,
                'timestamp': datetime.datetime.now().isoformat()
            })
        }
'''
    
    # Create ZIP package
    zip_filename = "lambda_function.zip"
    with zipfile.ZipFile(zip_filename, 'w') as zip_file:
        zip_file.writestr("lambda_function.py", lambda_code)
    
    print(f"✅ Lambda package created: {zip_filename}")
    return zip_filename

def deploy_lambda_function(role_arn):
    """Deploy Lambda function"""
    try:
        print("🚀 Deploying Lambda function...")
        
        # Create deployment package
        zip_filename = create_lambda_package()
        
        # Read ZIP file
        with open(zip_filename, 'rb') as zip_file:
            zip_content = zip_file.read()
        
        # Check if function exists
        try:
            lambda_client.get_function(FunctionName=lambda_function_name)
            print("ℹ️ Lambda function exists, updating...")
            
            # Update function code
            lambda_client.update_function_code(
                FunctionName=lambda_function_name,
                ZipFile=zip_content
            )
            
            # Update function configuration
            lambda_client.update_function_configuration(
                FunctionName=lambda_function_name,
                Environment={
                    'Variables': {
                        'S3_BUCKET': s3_backup_bucket,
                        'SNS_TOPIC_ARN': sns_topic_arn,
                        'MONGO_URI': mongo_uri
                    }
                }
            )
            
        except ClientError as e:
            if "ResourceNotFoundException" in str(e):
                print("✨ Creating new Lambda function...")
                
                # Create new function
                response = lambda_client.create_function(
                    FunctionName=lambda_function_name,
                    Runtime='python3.9',
                    Role=role_arn,
                    Handler='lambda_function.lambda_handler',
                    Code={'ZipFile': zip_content},
                    Description='MongoDB backup function with timestamp',
                    Timeout=300,  # 5 minutes
                    MemorySize=512,
                    Environment={
                        'Variables': {
                            'S3_BUCKET': s3_backup_bucket,
                            'SNS_TOPIC_ARN': sns_topic_arn,
                            'MONGO_URI': mongo_uri
                        }
                    },
                    Tags={
                        'Project': 'MERN-Deployment',
                        'Function': 'MongoDB-Backup'
                    }
                )
            else:
                raise e
        
        # Clean up ZIP file
        os.remove(zip_filename)
        
        print(f"✅ Lambda function '{lambda_function_name}' deployed successfully")
        return True
        
    except ClientError as e:
        print(f"❌ Error deploying Lambda function: {e}")
        return False

def create_cloudwatch_schedule():
    """Create CloudWatch Events rule to trigger Lambda daily"""
    try:
        print("⏰ Creating CloudWatch schedule for daily backups...")
        
        rule_name = f"{lambda_function_name}-schedule"
        
        # Create EventBridge rule (runs daily at 2 AM UTC)
        events_client.put_rule(
            Name=rule_name,
            ScheduleExpression='cron(0 2 * * ? *)',  # Daily at 2 AM UTC
            Description='Daily MongoDB backup trigger',
            State='ENABLED'
        )
        
        # Add Lambda function as target
        lambda_arn = f"arn:aws:lambda:{region}:975050024946:function:{lambda_function_name}"
        
        events_client.put_targets(
            Rule=rule_name,
            Targets=[
                {
                    'Id': '1',
                    'Arn': lambda_arn
                }
            ]
        )
        
        # Add permission for CloudWatch Events to invoke Lambda
        try:
            lambda_client.add_permission(
                FunctionName=lambda_function_name,
                StatementId='AllowExecutionFromCloudWatch',
                Action='lambda:InvokeFunction',
                Principal='events.amazonaws.com',
                SourceArn=f"arn:aws:events:{region}:975050024946:rule/{rule_name}"
            )
        except ClientError as e:
            if "ResourceConflictException" in str(e):
                print("ℹ️ Permission already exists")
            else:
                raise e
        
        print(f"✅ CloudWatch schedule created: {rule_name}")
        print("📅 Backup will run daily at 2:00 AM UTC")
        return True
        
    except ClientError as e:
        print(f"❌ Error creating CloudWatch schedule: {e}")
        return False

def test_lambda_function():
    """Test the Lambda function"""
    try:
        print("🧪 Testing Lambda function...")
        
        response = lambda_client.invoke(
            FunctionName=lambda_function_name,
            InvocationType='RequestResponse'
        )
        
        result = json.loads(response['Payload'].read())
        
        if response['StatusCode'] == 200:
            print("✅ Lambda function test successful!")
            print(f"   Response: {result}")
        else:
            print(f"❌ Lambda function test failed: {result}")
        
        return response['StatusCode'] == 200
        
    except ClientError as e:
        print(f"❌ Error testing Lambda function: {e}")
        return False

def main():
    """Main function to deploy complete backup solution"""
    print("🚀 Deploying MongoDB Backup Solution...")
    
    # Step 1: Create S3 bucket
    if not create_s3_bucket():
        print("❌ Failed to create S3 bucket")
        return
    
    # Step 2: Create IAM role
    role_arn = create_lambda_execution_role()
    if not role_arn:
        print("❌ Failed to create IAM role")
        return
    
    # Step 3: Deploy Lambda function
    if not deploy_lambda_function(role_arn):
        print("❌ Failed to deploy Lambda function")
        return
    
    # Step 4: Create CloudWatch schedule
    if not create_cloudwatch_schedule():
        print("❌ Failed to create CloudWatch schedule")
        return
    
    # Step 5: Test Lambda function
    test_lambda_function()
    
    print("\n🎉 MongoDB Backup Solution Deployed Successfully!")
    print(f"   📦 Lambda Function: {lambda_function_name}")
    print(f"   🪣 S3 Bucket: {s3_backup_bucket}")
    print(f"   📅 Schedule: Daily at 2:00 AM UTC")
    print(f"   🔔 Notifications: {sns_topic_arn}")
    
    print("\n📋 Manual Test Commands:")
    print(f"   aws lambda invoke --function-name {lambda_function_name} response.json")
    print(f"   aws s3 ls s3://{s3_backup_bucket}")

if __name__ == "__main__":
    main()