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
# ✅ User Data Script to Pull and Run Image (Ubuntu)
# ----------------------------------------
user_data_script = f"""#!/bin/bash
# Log everything for debugging
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
echo "Starting user data script execution..."

# Update system
echo "Updating system packages..."
sudo apt update -y

# Install Docker using the official Docker installation method
echo "Installing Docker..."
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -

# Add Docker repository
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"

# Update package database with Docker packages
sudo apt update -y

# Install Docker CE
sudo apt install -y docker-ce

# Enable and start Docker
echo "Starting Docker service..."
sudo systemctl enable docker
sudo systemctl start docker

# Add ubuntu user to docker group (default user for Ubuntu AMI)
sudo usermod -aG docker ubuntu

# Verify Docker is running
echo "Verifying Docker installation..."
sudo systemctl status docker
docker --version

# Wait for Docker to be fully ready
sleep 10

# Install AWS CLI v2 if not present
echo "Installing AWS CLI v2..."
if ! command -v aws &> /dev/null; then
    # Install unzip if not present
    sudo apt install -y unzip
    
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    unzip awscliv2.zip
    sudo ./aws/install
    rm -rf awscliv2.zip aws/
fi

# Refresh group membership for ubuntu user
echo "Refreshing group membership..."
newgrp docker << EONG
# Login to ECR
echo "Logging into ECR..."
aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {docker_image_uri.split('/')[0]}

if [ $? -eq 0 ]; then
    echo "ECR login successful"
    
    # Pull Docker image
    echo "Pulling Docker image: {docker_image_uri}"
    docker pull {docker_image_uri}
    
    if [ $? -eq 0 ]; then
        echo "Docker image pulled successfully"
        
        # Stop any existing container on port 80
        echo "Stopping existing containers on port 80..."
        docker stop \$(docker ps -q --filter "publish=80") 2>/dev/null || true
        docker rm \$(docker ps -aq --filter "publish=80") 2>/dev/null || true
        
        # Run the container (mapping port 80 to container port 3000)
        echo "Starting Docker container..."
        docker run -d -p 80:3000 --restart=unless-stopped --name backend-service {docker_image_uri}
        
        if [ $? -eq 0 ]; then
            echo "Container started successfully"
            docker ps
        else
            echo "Failed to start container"
        fi
    else
        echo "Failed to pull Docker image"
    fi
else
    echo "ECR login failed"
fi
EONG

echo "User data script completed"
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

print("🎉 All resources created successfully!")import boto3
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
# ✅ User Data Script to Pull and Run Image (Ubuntu)
# ----------------------------------------
user_data_script = f"""#!/bin/bash
# Log everything for debugging
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
echo "Starting user data script execution..."

# Update system
echo "Updating system packages..."
sudo apt update -y

# Install Docker using the official Docker installation method
echo "Installing Docker..."
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -

# Add Docker repository
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"

# Update package database with Docker packages
sudo apt update -y

# Install Docker CE
sudo apt install -y docker-ce

# Enable and start Docker
echo "Starting Docker service..."
sudo systemctl enable docker
sudo systemctl start docker

# Add ubuntu user to docker group (default user for Ubuntu AMI)
sudo usermod -aG docker ubuntu

# Verify Docker is running
echo "Verifying Docker installation..."
sudo systemctl status docker
docker --version

# Wait for Docker to be fully ready
sleep 10

# Install AWS CLI v2 if not present
echo "Installing AWS CLI v2..."
if ! command -v aws &> /dev/null; then
    # Install unzip if not present
    sudo apt install -y unzip
    
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    unzip awscliv2.zip
    sudo ./aws/install
    rm -rf awscliv2.zip aws/
fi

# Refresh group membership for ubuntu user
echo "Refreshing group membership..."
newgrp docker << EONG
# Login to ECR
echo "Logging into ECR..."
aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {docker_image_uri.split('/')[0]}

if [ $? -eq 0 ]; then
    echo "ECR login successful"
    
    # Pull Docker image
    echo "Pulling Docker image: {docker_image_uri}"
    docker pull {docker_image_uri}
    
    if [ $? -eq 0 ]; then
        echo "Docker image pulled successfully"
        
        # Stop any existing container on port 80
        echo "Stopping existing containers on port 80..."
        docker stop \$(docker ps -q --filter "publish=80") 2>/dev/null || true
        docker rm \$(docker ps -aq --filter "publish=80") 2>/dev/null || true
        
        # Run the container (mapping port 80 to container port 3000)
        echo "Starting Docker container..."
        docker run -d -p 80:3000 --restart=unless-stopped --name backend-service {docker_image_uri}
        
        if [ $? -eq 0 ]; then
            echo "Container started successfully"
            docker ps
        else
            echo "Failed to start container"
        fi
    else
        echo "Failed to pull Docker image"
    fi
else
    echo "ECR login failed"
fi
EONG

echo "User data script completed"
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