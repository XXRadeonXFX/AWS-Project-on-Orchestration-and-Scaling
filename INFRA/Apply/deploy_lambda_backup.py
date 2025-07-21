#!/usr/bin/env python3
"""
Deploy MongoDB Backup Lambda Function using Boto3
"""

import boto3
import json
import zipfile
import os
import tempfile
import time
from botocore.exceptions import ClientError


class LambdaDeployment:
    def __init__(self, region='ap-south-1'):
        self.region = region
        self.lambda_client = boto3.client('lambda', region_name=region)
        self.iam_client = boto3.client('iam', region_name=region)
        self.s3_client = boto3.client('s3', region_name=region)
        self.events_client = boto3.client('events', region_name=region)
        
    def create_s3_bucket(self, bucket_name='mern-app-database-backups'):
        """Create S3 bucket for backups"""
        try:
            # Check if bucket exists
            try:
                self.s3_client.head_bucket(Bucket=bucket_name)
                print(f"✅ S3 bucket already exists: {bucket_name}")
                return bucket_name
            except ClientError:
                pass
            
            # Create bucket
            if self.region == 'us-east-1':
                self.s3_client.create_bucket(Bucket=bucket_name)
            else:
                self.s3_client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': self.region}
                )
            
            # Add tags
            self.s3_client.put_bucket_tagging(
                Bucket=bucket_name,
                Tagging={
                    'TagSet': [
                        {'Key': 'Project', 'Value': 'MERN-Microservices'},
                        {'Key': 'Purpose', 'Value': 'Database-Backups'},
                        {'Key': 'Environment', 'Value': 'Production'}
                    ]
                }
            )
            
            # Enable versioning
            self.s3_client.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={'Status': 'Enabled'}
            )
            
            print(f"✅ S3 bucket created successfully: {bucket_name}")
            return bucket_name
            
        except ClientError as e:
            print(f"❌ Error creating S3 bucket: {e}")
            return None
    
    def create_lambda_role(self):
        """Create IAM role for Lambda function"""
        role_name = 'MERNBackupLambdaRole'
        
        # Trust policy for Lambda
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        # IAM policy for Lambda function
        lambda_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents"
                    ],
                    "Resource": "arn:aws:logs:*:*:*"
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject",
                        "s3:ListBucket"
                    ],
                    "Resource": [
                        "arn:aws:s3:::mern-app-database-backups",
                        "arn:aws:s3:::mern-app-database-backups/*"
                    ]
                }
            ]
        }
        
        try:
            # Check if role exists
            try:
                role = self.iam_client.get_role(RoleName=role_name)
                role_arn = role['Role']['Arn']
                print(f"✅ IAM role already exists: {role_arn}")
                return role_arn
            except ClientError:
                pass
            
            # Create role
            role_response = self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description='IAM role for MERN MongoDB backup Lambda function',
                Tags=[
                    {'Key': 'Project', 'Value': 'MERN-Microservices'},
                    {'Key': 'Purpose', 'Value': 'Lambda-Execution'}
                ]
            )
            
            role_arn = role_response['Role']['Arn']
            
            # Create and attach policy
            policy_name = 'MERNBackupLambdaPolicy'
            policy_response = self.iam_client.create_policy(
                PolicyName=policy_name,
                PolicyDocument=json.dumps(lambda_policy),
                Description='Policy for MERN MongoDB backup Lambda function'
            )
            
            policy_arn = policy_response['Policy']['Arn']
            
            # Attach policy to role
            self.iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn=policy_arn
            )
            
            # Wait for role to be available
            time.sleep(10)
            
            print(f"✅ IAM role created successfully: {role_arn}")
            return role_arn
            
        except ClientError as e:
            print(f"❌ Error creating IAM role: {e}")
            return None
    
    def create_lambda_package(self, lambda_code_file='lambda_mongo_backup.py'):
        """Create Lambda deployment package"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = os.path.join(temp_dir, 'lambda_function.zip')
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # Add the main Lambda function
                    zipf.write(lambda_code_file, 'lambda_function.py')
                    
                    # Add requirements.txt content as a comment for reference
                    requirements_content = """
# Lambda Layer Dependencies (install separately):
# pymongo==4.3.3
# dnspython==2.3.0
"""
                    zipf.writestr('requirements.txt', requirements_content)
                
                # Read the zip file
                with open(zip_path, 'rb') as f:
                    zip_content = f.read()
                
                print(f"✅ Lambda package created: {len(zip_content)} bytes")
                return zip_content
                
        except Exception as e:
            print(f"❌ Error creating Lambda package: {e}")
            return None
    
    def deploy_lambda_function(self, role_arn, zip_content):
        """Deploy Lambda function"""
        function_name = 'MERN-MongoDB-Backup'
        
        try:
            # Check if function exists
            try:
                response = self.lambda_client.get_function(FunctionName=function_name)
                print(f"✅ Lambda function already exists: {function_name}")
                
                # Update function code
                self.lambda_client.update_function_code(
                    FunctionName=function_name,
                    ZipFile=zip_content
                )
                
                function_arn = response['Configuration']['FunctionArn']
                print(f"✅ Lambda function code updated")
                
            except ClientError:
                # Create new function
                response = self.lambda_client.create_function(
                    FunctionName=function_name,
                    Runtime='python3.9',
                    Role=role_arn,
                    Handler='lambda_function.lambda_handler',
                    Code={'ZipFile': zip_content},
                    Description='MongoDB backup function for MERN application',
                    Timeout=900,  # 15 minutes
                    MemorySize=512,
                    Environment={
                        'Variables': {
                            'MONGO_CONNECTION_STRING': 'mongodb+srv://radeonxfx:1029384756!Sound@cluster0.gdl7f.mongodb.net/SimpleMern',
                            'S3_BUCKET_NAME': 'mern-app-database-backups',
                            'DATABASE_NAME': 'SimpleMern'
                        }
                    },
                    Tags={
                        'Project': 'MERN-Microservices',
                        'Purpose': 'Database-Backup'
                    }
                )
                
                function_arn = response['FunctionArn']
                print(f"✅ Lambda function created successfully: {function_arn}")
            
            return function_arn
            
        except ClientError as e:
            print(f"❌ Error deploying Lambda function: {e}")
            return None
    
    def create_cloudwatch_rule(self, function_arn):
        """Create CloudWatch Events rule for scheduled backups"""
        rule_name = 'MERN-Daily-Backup-Schedule'
        
        try:
            # Create CloudWatch Events rule (daily at 2 AM UTC)
            self.events_client.put_rule(
                Name=rule_name,
                ScheduleExpression='cron(0 2 * * ? *)',  # Daily at 2 AM UTC
                Description='Daily MongoDB backup for MERN application',
                State='ENABLED',
                Tags=[
                    {'Key': 'Project', 'Value': 'MERN-Microservices'},
                    {'Key': 'Purpose', 'Value': 'Backup-Schedule'}
                ]
            )
            
            # Add Lambda function as target
            self.events_client.put_targets(
                Rule=rule_name,
                Targets=[
                    {
                        'Id': '1',
                        'Arn': function_arn,
                        'Input': json.dumps({
                            'backup_type': 'scheduled',
                            'source': 'cloudwatch-events'
                        })
                    }
                ]
            )
            
            # Add permission for CloudWatch Events to invoke Lambda
            try:
                self.lambda_client.add_permission(
                    FunctionName=function_arn,
                    StatementId='AllowExecutionFromCloudWatch',
                    Action='lambda:InvokeFunction',
                    Principal='events.amazonaws.com',
                    SourceArn=f'arn:aws:events:{self.region}:{boto3.client("sts").get_caller_identity()["Account"]}:rule/{rule_name}'
                )
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceConflictException':
                    raise
            
            print(f"✅ CloudWatch Events rule created: {rule_name}")
            print(f"⏰ Backup scheduled daily at 2:00 AM UTC")
            
        except ClientError as e:
            print(f"❌ Error creating CloudWatch Events rule: {e}")
    
    def deploy_backup_solution(self):
        """Deploy complete backup solution"""
        print("🚀 Deploying MongoDB backup solution...")
        
        # Create S3 bucket
        bucket_name = self.create_s3_bucket()
        if not bucket_name:
            return False
        
        # Create IAM role
        role_arn = self.create_lambda_role()
        if not role_arn:
            return False
        
        # Create Lambda package
        zip_content = self.create_lambda_package()
        if not zip_content:
            return False
        
        # Deploy Lambda function
        function_arn = self.deploy_lambda_function(role_arn, zip_content)
        if not function_arn:
            return False
        
        # Create CloudWatch Events rule
        self.create_cloudwatch_rule(function_arn)
        
        print("\n🎉 MongoDB backup solution deployed successfully!")
        print(f"📋 Deployment Summary:")
        print(f"   S3 Bucket: {bucket_name}")
        print(f"   Lambda Function: {function_arn}")
        print(f"   Backup Schedule: Daily at 2:00 AM UTC")
        print(f"   Retention: 30 days")
        
        return True
    
    def test_backup_function(self):
        """Test the backup function manually"""
        function_name = 'MERN-MongoDB-Backup'
        
        try:
            print("🧪 Testing backup function...")
            
            response = self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps({
                    'backup_type': 'manual',
                    'source': 'manual-test'
                })
            )
            
            result = json.loads(response['Payload'].read())
            
            if response['StatusCode'] == 200:
                print("✅ Backup test completed successfully!")
                print(f"📊 Result: {json.dumps(result, indent=2)}")
            else:
                print(f"❌ Backup test failed: {result}")
                
        except ClientError as e:
            print(f"❌ Error testing backup function: {e}")


def main():
    """Main function to deploy backup solution"""
    deployment = LambdaDeployment()
    
    try:
        success = deployment.deploy_backup_solution()
        if success:
            print("\n✅ All components deployed successfully!")
            
            # Test the backup function
            test_choice = input("\n🧪 Would you like to test the backup function now? (y/N): ")
            if test_choice.lower() == 'y':
                deployment.test_backup_function()
        else:
            print("\n❌ Deployment failed!")
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()