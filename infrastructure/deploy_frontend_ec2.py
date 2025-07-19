import boto3
import base64
import time
from botocore.exceptions import ClientError

# ----------------------------------------
# 🔧 CONFIGURE THESE VARIABLES
# ----------------------------------------
region = "ap-south-1"
ami_id = "ami-0f918f7e67a3323f0"  # Ubuntu AMI
instance_type = "t2.micro"
key_name = "prince-pair-x"
security_group_id = "sg-0d87019135757e907"  # Use your existing security group
subnet_id = "subnet-0fe9c16f3384ed76e"  # Use your existing subnet
iam_instance_profile_name = "Prince_EC2_ECR_PullAccess"
instance_name = "prince-frontend-ec2"
docker_image_uri = "975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:frontend"

# ----------------------------------------
# ✅ User Data Script for Frontend (Ubuntu)
# ----------------------------------------
user_data_script = f"""#!/bin/bash
# Log everything for debugging
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
echo "Starting user data script execution for frontend..."

# Update system
echo "Updating system packages..."
sudo apt update -y

# Install Docker
echo "Installing Docker..."
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -

# Add Docker repository
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"

# Update package database
sudo apt update -y

# Install Docker CE
sudo apt install -y docker-ce

# Enable and start Docker
sudo systemctl enable docker
sudo systemctl start docker

# Add ubuntu user to docker group
sudo usermod -aG docker ubuntu

# Install AWS CLI v2
echo "Installing AWS CLI v2..."
sudo apt install -y unzip
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
rm -rf awscliv2.zip aws/

# Wait for Docker to be ready
sleep 10

# Login to ECR and run frontend container
newgrp docker << EONG
echo "Logging into ECR..."
aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {docker_image_uri.split('/')[0]}

if [ $? -eq 0 ]; then
    echo "ECR login successful"
    
    echo "Pulling frontend image: {docker_image_uri}"
    docker pull {docker_image_uri}
    
    if [ $? -eq 0 ]; then
        echo "Frontend image pulled successfully"
        
        # Stop any existing container on port 80
        docker stop \$(docker ps -q --filter "publish=80") 2>/dev/null || true
        docker rm \$(docker ps -aq --filter "publish=80") 2>/dev/null || true
        
        # Run the frontend container
        echo "Starting frontend container..."
        docker run -d -p 80:3000 --restart=unless-stopped --name frontend-service {docker_image_uri}
        
        if [ $? -eq 0 ]; then
            echo "Frontend container started successfully"
            docker ps
        else
            echo "Failed to start frontend container"
        fi
    else
        echo "Failed to pull frontend image"
    fi
else
    echo "ECR login failed"
fi
EONG

echo "Frontend deployment completed"
"""

# Base64 encode
encoded_user_data = base64.b64encode(user_data_script.encode("utf-8")).decode("utf-8")

# Initialize clients
ec2_client = boto3.client("ec2", region_name=region)

def deploy_frontend_instance():
    """Deploy frontend EC2 instance"""
    try:
        print("🚀 Deploying Frontend EC2 Instance...")
        
        response = ec2_client.run_instances(
            ImageId=ami_id,
            InstanceType=instance_type,
            KeyName=key_name,
            MinCount=1,
            MaxCount=1,
            SecurityGroupIds=[security_group_id],
            SubnetId=subnet_id,
            IamInstanceProfile={"Name": iam_instance_profile_name},
            UserData=encoded_user_data,
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": instance_name},
                        {"Key": "Type", "Value": "Frontend"},
                        {"Key": "Project", "Value": "MERN-Deployment"}
                    ]
                }
            ]
        )
        
        instance_id = response["Instances"][0]["InstanceId"]
        print(f"✅ Frontend EC2 Instance launched: {instance_id}")
        
        # Wait for instance to be running
        print("⏳ Waiting for instance to be running...")
        waiter = ec2_client.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id])
        
        # Get instance details
        instances = ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = instances['Reservations'][0]['Instances'][0]
        public_ip = instance.get('PublicIpAddress', 'N/A')
        private_ip = instance.get('PrivateIpAddress', 'N/A')
        
        print(f"✅ Frontend Instance Details:")
        print(f"   Instance ID: {instance_id}")
        print(f"   Public IP: {public_ip}")
        print(f"   Private IP: {private_ip}")
        print(f"   Frontend URL: http://{public_ip}")
        
        return instance_id, public_ip
        
    except ClientError as e:
        print(f"❌ Error deploying frontend instance: {e}")
        return None, None

if __name__ == "__main__":
    instance_id, public_ip = deploy_frontend_instance()
    if instance_id:
        print(f"🎉 Frontend deployment completed successfully!")
        print(f"   Access your frontend at: http://{public_ip}")
        print(f"   SSH access: ssh -i {key_name}.pem ubuntu@{public_ip}")
    else:
        print("❌ Frontend deployment failed!")