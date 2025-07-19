import boto3
import base64
import time
from botocore.exceptions import ClientError

# ----------------------------------------
# 🔧 CONFIGURE THESE VARIABLES
# ----------------------------------------
region = "ap-south-1"
ami_id = "ami-0f918f7e67a3323f0"  # Amazon Linux 2 AMI
instance_type = "t2.micro"
key_name = "prince-pair-x"
security_group_id = "sg-0d87019135757e907"
subnet_ids = ["subnet-0fe9c16f3384ed76e"]
iam_instance_profile_name = "Prince_EC2_ECR_PullAccess"
launch_template_name = "prince-launch-template"
asg_name = "prince-backend-asg"
docker_image_uri = "975050024946.dkr.ecr.ap-south-1.amazonaws.com/hello-service:latest"
min_size = 1
max_size = 3
desired_capacity = 2

# ----------------------------------------
# ✅ User Data Script to Pull and Run Image
# ----------------------------------------
user_data_script = f"""#!/bin/bash
yum update -y
yum install -y docker
systemctl start docker
systemctl enable docker
# Login to ECR
aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {docker_image_uri.split('/')[0]}
# Pull and run container
docker pull {docker_image_uri}
docker run -d -p 3000:3000 {docker_image_uri}
"""

# Base64 encode
encoded_user_data = base64.b64encode(user_data_script.encode("utf-8")).decode("utf-8")

# Initialize clients
ec2_client = boto3.client("ec2", region_name=region)
asg_client = boto3.client("autoscaling", region_name=region)

# ----------------------------------------
# 🗑️ Helper Functions for Cleanup
# ----------------------------------------
def delete_existing_asg(asg_name):
    """Delete existing ASG if it exists"""
    try:
        print(f"🔍 Checking if ASG '{asg_name}' exists...")
        response = asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )
        
        if response['AutoScalingGroups']:
            print(f"🗑️ Deleting existing ASG '{asg_name}'...")
            
            # First, set desired capacity to 0
            asg_client.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MinSize=0,
                DesiredCapacity=0
            )
            print("⏳ Waiting for instances to terminate...")
            
            # Wait for instances to terminate manually
            max_wait_time = 300  # 5 minutes
            wait_interval = 15
            waited = 0
            
            while waited < max_wait_time:
                response = asg_client.describe_auto_scaling_groups(
                    AutoScalingGroupNames=[asg_name]
                )
                
                if response['AutoScalingGroups']:
                    asg = response['AutoScalingGroups'][0]
                    if len(asg['Instances']) == 0:
                        print("✅ All instances terminated")
                        break
                    else:
                        print(f"⏳ {len(asg['Instances'])} instances still running...")
                        time.sleep(wait_interval)
                        waited += wait_interval
                else:
                    break
            
            # Delete the ASG
            asg_client.delete_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                ForceDelete=True
            )
            
            # Wait for ASG to be completely deleted
            print("⏳ Waiting for ASG deletion to complete...")
            time.sleep(30)
            print(f"✅ ASG '{asg_name}' deleted successfully")
        else:
            print(f"ℹ️ ASG '{asg_name}' does not exist")
            
    except ClientError as e:
        if e.response['Error']['Code'] == 'ValidationError':
            print(f"ℹ️ ASG '{asg_name}' does not exist")
        else:
            print(f"❌ Error checking/deleting ASG: {e}")
            raise

def delete_existing_launch_template(template_name):
    """Delete existing launch template if it exists"""
    try:
        print(f"🔍 Checking if Launch Template '{template_name}' exists...")
        response = ec2_client.describe_launch_templates(
            LaunchTemplateNames=[template_name]
        )
        
        if response['LaunchTemplates']:
            print(f"🗑️ Deleting existing Launch Template '{template_name}'...")
            ec2_client.delete_launch_template(
                LaunchTemplateName=template_name
            )
            print(f"✅ Launch Template '{template_name}' deleted successfully")
        else:
            print(f"ℹ️ Launch Template '{template_name}' does not exist")
            
    except ClientError as e:
        if e.response['Error']['Code'] == 'InvalidLaunchTemplateName.NotFound':
            print(f"ℹ️ Launch Template '{template_name}' does not exist")
        else:
            print(f"❌ Error checking/deleting Launch Template: {e}")
            raise

# ----------------------------------------
# 🧹 Cleanup Existing Resources
# ----------------------------------------
print("🧹 Starting cleanup of existing resources...")

# Delete ASG first (it depends on launch template)
delete_existing_asg(asg_name)

# Then delete launch template
delete_existing_launch_template(launch_template_name)

print("✅ Cleanup completed")

# ----------------------------------------
# ✅ Create Launch Template
# ----------------------------------------
print("➡️ Creating Launch Template...")
try:
    response = ec2_client.create_launch_template(
        LaunchTemplateName=launch_template_name,
        LaunchTemplateData={
            "ImageId": ami_id,
            "InstanceType": instance_type,
            "KeyName": key_name,
            "SecurityGroupIds": [security_group_id],
            "IamInstanceProfile": {"Name": iam_instance_profile_name},
            "UserData": encoded_user_data,
        },
    )
    launch_template_id = response["LaunchTemplate"]["LaunchTemplateId"]
    print(f"✅ Launch Template created: {launch_template_id}")
    
except ClientError as e:
    print(f"❌ Error creating Launch Template: {e}")
    exit(1)

# ----------------------------------------
# ✅ Create Auto Scaling Group
# ----------------------------------------
print("➡️ Creating Auto Scaling Group...")
try:
    asg_client.create_auto_scaling_group(
        AutoScalingGroupName=asg_name,
        LaunchTemplate={
            "LaunchTemplateId": launch_template_id,
            "Version": "$Latest",
        },
        MinSize=min_size,
        MaxSize=max_size,
        DesiredCapacity=desired_capacity,
        VPCZoneIdentifier=",".join(subnet_ids),
        Tags=[
            {
                "Key": "Name",
                "Value": "backend-ec2",
                "PropagateAtLaunch": True,
            }
        ],
    )
    print(f"✅ ASG '{asg_name}' created with desired capacity {desired_capacity}")
    
except ClientError as e:
    print(f"❌ Error creating ASG: {e}")
    exit(1)

print("🎉 All resources created successfully!")