#!/usr/bin/env python3
"""
Deploy Auto Scaling Group for MERN Backend Services - UBUNTU OPTIMIZED
"""
import boto3
import json
import base64
import time
import os
from botocore.exceptions import ClientError


class UbuntuASGDeployment:
    def __init__(self, region='ap-south-1'):
        self.region = region
        self.ec2 = boto3.client('ec2', region_name=region)
        self.autoscaling = boto3.client('autoscaling', region_name=region)
        self.elbv2 = boto3.client('elbv2', region_name=region)
        self.iam = boto3.client('iam', region_name=region)
        
    def create_instance_role(self):
        """Create IAM role for Ubuntu EC2 instances"""
        role_name = 'Ubuntu-ECR-CloudWatch-Role'
        
        # Trust policy for EC2
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        try:
            # Check if role exists
            try:
                role = self.iam.get_role(RoleName=role_name)
                print(f"✅ IAM role already exists: {role_name}")
                return role_name
            except ClientError:
                pass
            
            # Create role
            self.iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description='IAM role for Ubuntu EC2 instances to access ECR and CloudWatch'
            )
            
            # Attach policies
            policies = [
                'arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly',
                'arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy'
            ]
            
            for policy_arn in policies:
                self.iam.attach_role_policy(
                    RoleName=role_name,
                    PolicyArn=policy_arn
                )
            
            # Create instance profile
            try:
                self.iam.create_instance_profile(InstanceProfileName=role_name)
                self.iam.add_role_to_instance_profile(
                    InstanceProfileName=role_name,
                    RoleName=role_name
                )
            except ClientError as e:
                if e.response['Error']['Code'] != 'EntityAlreadyExists':
                    raise
            
            time.sleep(10)  # Wait for role to be available
            print(f"✅ IAM role created: {role_name}")
            return role_name
            
        except ClientError as e:
            print(f"❌ Error creating IAM role: {e}")
            return None
    
    def create_launch_template(self, security_group_id, subnet_ids):
        """Create Ubuntu-optimized launch template for ASG instances"""
        
        template_name = 'MERN-Ubuntu-Backend-Template'
        
        # Check if launch template already exists
        try:
            response = self.ec2.describe_launch_templates(
                LaunchTemplateNames=[template_name]
            )
            if response['LaunchTemplates']:
                existing_template = response['LaunchTemplates'][0]
                template_id = existing_template['LaunchTemplateId']
                print(f"✅ Launch template already exists: {template_id}")
                return template_id
        except ClientError as e:
            if e.response['Error']['Code'] != 'InvalidLaunchTemplateName.NotFoundException':
                print(f"⚠️  Error checking existing launch template: {e}")
        
        # Ubuntu-optimized user data script
        user_data_script = """#!/bin/bash
set -e  # Exit on any error
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "🚀 Starting Ubuntu MERN Backend deployment..."
echo "Timestamp: $(date)"

# Update system packages
echo "📦 Updating Ubuntu packages..."
export DEBIAN_FRONTEND=noninteractive
sudo apt update -y
sudo apt upgrade -y

# Install essential packages
echo "🔧 Installing prerequisites..."
sudo apt install -y \\
    curl \\
    unzip \\
    apt-transport-https \\
    ca-certificates \\
    gnupg \\
    lsb-release \\
    software-properties-common

# Install Docker Engine for Ubuntu
echo "🐳 Installing Docker Engine..."

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Set up the stable repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package index with Docker repo
sudo apt update -y

# Install Docker Engine, containerd, and Docker Compose
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Start and enable Docker
sudo systemctl start docker
sudo systemctl enable docker

# Add ubuntu user to docker group
sudo usermod -aG docker ubuntu

# Install AWS CLI v2
echo "☁️ Installing AWS CLI v2..."
cd /tmp
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
sudo ./aws/install --update

# Install Docker Compose standalone (backup)
echo "📋 Installing Docker Compose standalone..."
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Wait for Docker to be fully ready
echo "⏳ Waiting for Docker to initialize..."
sleep 15

# Test Docker installation
echo "🧪 Testing Docker installation..."
sudo docker --version
/usr/local/bin/docker-compose --version

# Login to ECR with retry mechanism
echo "🔐 Logging into ECR..."
ECR_LOGIN_SUCCESS=false
for i in {1..5}; do
    if aws ecr get-login-password --region ap-south-1 | sudo docker login --username AWS --password-stdin 975050024946.dkr.ecr.ap-south-1.amazonaws.com; then
        echo "✅ ECR login successful on attempt $i"
        ECR_LOGIN_SUCCESS=true
        break
    else
        echo "⚠️ ECR login attempt $i failed, retrying in 10 seconds..."
        sleep 10
    fi
done

if [ "$ECR_LOGIN_SUCCESS" = false ]; then
    echo "❌ ECR login failed after 5 attempts"
    exit 1
fi

# Create docker-compose.yml for backend services
echo "📝 Creating Docker Compose configuration..."
cat > /home/ubuntu/docker-compose.yml << 'EOF'
version: '3.8'
services:
  hello-service:
    image: 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:hs-radeon
    container_name: mern-hello-service
    ports:
      - "3001:3001"
    environment:
      - PORT=3001
      - NODE_ENV=production
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    
  profile-service:
    image: 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:ps-radeon
    container_name: mern-profile-service
    ports:
      - "3002:3002"
    environment:
      - PORT=3002
      - NODE_ENV=production
      - MONGO_URL=mongodb+srv://radeonxfx:1029384756!Sound@cluster0.gdl7f.mongodb.net/SimpleMern
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3002/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
EOF

# Set proper ownership
sudo chown ubuntu:ubuntu /home/ubuntu/docker-compose.yml

# Pull Docker images with retry mechanism
echo "📥 Pulling Docker images..."
cd /home/ubuntu

PULL_SUCCESS=false
for i in {1..3}; do
    echo "🔄 Pull attempt $i..."
    if sudo docker pull 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:hs-radeon && \\
       sudo docker pull 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:ps-radeon; then
        echo "✅ Docker images pulled successfully"
        PULL_SUCCESS=true
        break
    else
        echo "⚠️ Docker pull attempt $i failed, retrying in 15 seconds..."
        sleep 15
    fi
done

if [ "$PULL_SUCCESS" = false ]; then
    echo "❌ Failed to pull Docker images after 3 attempts"
    exit 1
fi

# Start services with retry mechanism
echo "🚀 Starting MERN backend services..."
COMPOSE_SUCCESS=false
for i in {1..3}; do
    echo "🔄 Service start attempt $i..."
    if sudo /usr/local/bin/docker-compose up -d; then
        echo "✅ Services started successfully"
        COMPOSE_SUCCESS=true
        break
    else
        echo "⚠️ Service start attempt $i failed, retrying in 10 seconds..."
        sleep 10
    fi
done

if [ "$COMPOSE_SUCCESS" = false ]; then
    echo "❌ Failed to start services after 3 attempts"
    exit 1
fi

# Wait for services to initialize
echo "⏳ Waiting for services to initialize..."
sleep 45

# Install CloudWatch agent for Ubuntu
echo "📊 Installing CloudWatch agent..."
cd /tmp
wget -q https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb

# Create CloudWatch configuration
echo "⚙️ Configuring CloudWatch agent..."
sudo mkdir -p /opt/aws/amazon-cloudwatch-agent/bin
sudo tee /opt/aws/amazon-cloudwatch-agent/bin/config.json > /dev/null << 'EOF'
{
    "metrics": {
        "namespace": "MERN/Ubuntu/Backend",
        "metrics_collected": {
            "cpu": {
                "measurement": [
                    "cpu_usage_idle",
                    "cpu_usage_iowait", 
                    "cpu_usage_user",
                    "cpu_usage_system"
                ],
                "metrics_collection_interval": 60,
                "totalcpu": false
            },
            "disk": {
                "measurement": [
                    "used_percent"
                ],
                "metrics_collection_interval": 60,
                "resources": [
                    "*"
                ]
            },
            "diskio": {
                "measurement": [
                    "io_time"
                ],
                "metrics_collection_interval": 60,
                "resources": [
                    "*"
                ]
            },
            "mem": {
                "measurement": [
                    "mem_used_percent"
                ],
                "metrics_collection_interval": 60
            },
            "netstat": {
                "measurement": [
                    "tcp_established",
                    "tcp_time_wait"
                ],
                "metrics_collection_interval": 60
            }
        }
    },
    "logs": {
        "logs_collected": {
            "files": {
                "collect_list": [
                    {
                        "file_path": "/var/log/user-data.log",
                        "log_group_name": "/aws/ec2/mern-backend",
                        "log_stream_name": "{instance_id}/user-data.log"
                    }
                ]
            }
        }
    }
}
EOF

# Start CloudWatch agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/bin/config.json -s

# Create comprehensive health check script
echo "🏥 Creating health check script..."
cat > /home/ubuntu/health-check.sh << 'EOF'
#!/bin/bash
echo "=============================================="
echo "🏥 MERN Ubuntu Backend Health Check"
echo "Time: $(date)"
echo "Host: $(hostname)"
echo "=============================================="

echo -e "\\n🐳 Docker System Info:"
sudo docker version --format 'Version: {{.Server.Version}}'
sudo docker system df

echo -e "\\n📊 System Resources:"
echo "CPU Usage: $(top -bn1 | grep "Cpu(s)" | awk '{print $2 + $4}')%"
echo "Memory: $(free -m | awk 'NR==2{printf "%.1f%%", $3*100/$2 }')"
echo "Disk: $(df -h / | awk 'NR==2{print $5}')"

echo -e "\\n📦 Running Containers:"
sudo docker ps --format "table {{.Names}}\\t{{.Status}}\\t{{.Ports}}"

echo -e "\\n🔍 Docker Compose Status:"
cd /home/ubuntu
sudo /usr/local/bin/docker-compose ps

echo -e "\\n🌐 Service Health Checks:"
# Hello Service
if curl -f -s --max-time 10 http://localhost:3001/health >/dev/null 2>&1; then
    HELLO_STATUS="✅ HEALTHY"
    HELLO_RESPONSE=$(curl -s --max-time 5 http://localhost:3001/health 2>/dev/null | head -c 100)
else
    HELLO_STATUS="❌ UNHEALTHY"
    HELLO_RESPONSE="No response"
fi
echo "  Hello Service (3001): $HELLO_STATUS"
echo "    Response: $HELLO_RESPONSE"

# Profile Service  
if curl -f -s --max-time 10 http://localhost:3002/health >/dev/null 2>&1; then
    PROFILE_STATUS="✅ HEALTHY"
    PROFILE_RESPONSE=$(curl -s --max-time 5 http://localhost:3002/health 2>/dev/null | head -c 100)
else
    PROFILE_STATUS="❌ UNHEALTHY"
    PROFILE_RESPONSE="No response"
fi
echo "  Profile Service (3002): $PROFILE_STATUS"
echo "    Response: $PROFILE_RESPONSE"

echo -e "\\n🔧 Network Ports:"
sudo ss -tlnp | grep -E ':(3001|3002)' || echo "  No services listening on 3001/3002"

echo -e "\\n📋 Recent Container Logs:"
echo "Hello Service (last 5 lines):"
sudo docker logs --tail 5 mern-hello-service 2>/dev/null || echo "  No logs available"

echo -e "\\nProfile Service (last 5 lines):"
sudo docker logs --tail 5 mern-profile-service 2>/dev/null || echo "  No logs available"

echo -e "\\n=============================================="
echo "Health check completed at $(date)"
echo "=============================================="
EOF

chmod +x /home/ubuntu/health-check.sh
chown ubuntu:ubuntu /home/ubuntu/health-check.sh

# Create service management script
echo "⚙️ Creating service management script..."
cat > /home/ubuntu/manage-services.sh << 'EOF'
#!/bin/bash
# Ubuntu MERN Backend Service Management

show_usage() {
    echo "Usage: $0 {start|stop|restart|status|logs|health|pull}"
    echo "  start   - Start all MERN services"
    echo "  stop    - Stop all MERN services"  
    echo "  restart - Restart all MERN services"
    echo "  status  - Show service status"
    echo "  logs    - Show recent service logs"
    echo "  health  - Run comprehensive health check"
    echo "  pull    - Pull latest images and restart"
}

case "$1" in
    start)
        echo "🚀 Starting MERN backend services..."
        cd /home/ubuntu
        sudo /usr/local/bin/docker-compose up -d
        echo "✅ Services started"
        ;;
    stop)
        echo "🛑 Stopping MERN backend services..."
        cd /home/ubuntu
        sudo /usr/local/bin/docker-compose down
        echo "✅ Services stopped"
        ;;
    restart)
        echo "🔄 Restarting MERN backend services..."
        cd /home/ubuntu
        sudo /usr/local/bin/docker-compose down
        sleep 5
        sudo /usr/local/bin/docker-compose up -d
        echo "✅ Services restarted"
        ;;
    status)
        echo "📊 MERN backend service status:"
        cd /home/ubuntu
        sudo /usr/local/bin/docker-compose ps
        ;;
    logs)
        echo "📋 Recent service logs:"
        cd /home/ubuntu
        sudo /usr/local/bin/docker-compose logs --tail 30
        ;;
    health)
        /home/ubuntu/health-check.sh
        ;;
    pull)
        echo "📥 Pulling latest images and restarting..."
        cd /home/ubuntu
        sudo /usr/local/bin/docker-compose down
        sudo docker pull 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:hs-radeon
        sudo docker pull 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:ps-radeon
        sudo /usr/local/bin/docker-compose up -d
        echo "✅ Update completed"
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
EOF

chmod +x /home/ubuntu/manage-services.sh
chown ubuntu:ubuntu /home/ubuntu/manage-services.sh

# Final status verification
echo "🔍 Final deployment verification..."
echo "=== System Info ==="
echo "OS: $(lsb_release -d | cut -f2)"
echo "Docker: $(sudo docker --version)"
echo "Compose: $(/usr/local/bin/docker-compose --version)"
echo "AWS CLI: $(aws --version)"

echo -e "\\n=== Services Status ==="
cd /home/ubuntu
sudo docker ps --format "table {{.Names}}\\t{{.Status}}\\t{{.Ports}}"
sudo /usr/local/bin/docker-compose ps

echo -e "\\n=== Quick Health Check ==="
sleep 10
curl -s --max-time 5 http://localhost:3001/health && echo " (Hello service OK)" || echo " (Hello service not responding)"
curl -s --max-time 5 http://localhost:3002/health && echo " (Profile service OK)" || echo " (Profile service not responding)"

# Log success
echo "🎉 Ubuntu MERN Backend deployment completed successfully!" | sudo tee /var/log/user-data-success.log
echo "Deployment completed at: $(date)"
echo "Instance ready for production traffic!"
"""
        
        # Encode user data
        user_data_encoded = base64.b64encode(user_data_script.encode()).decode()
        
        try:
            # Create launch template
            response = self.ec2.create_launch_template(
                LaunchTemplateName=template_name,
                LaunchTemplateData={
                    'ImageId': 'ami-0ad21ae1d0696ad58',  # Ubuntu 20.04 LTS AMI (ap-south-1)
                    'InstanceType': 't3.medium',
                    'KeyName': 'prince-pair-x',  # SSH key pair
                    'SecurityGroupIds': [security_group_id],
                    'UserData': user_data_encoded,
                    'IamInstanceProfile': {
                        'Name': 'Ubuntu-ECR-CloudWatch-Role'
                    },
                    'TagSpecifications': [
                        {
                            'ResourceType': 'instance',
                            'Tags': [
                                {'Key': 'Name', 'Value': 'MERN-Ubuntu-Backend'},
                                {'Key': 'Project', 'Value': 'MERN-Microservices'},
                                {'Key': 'Environment', 'Value': 'Production'},
                                {'Key': 'Service', 'Value': 'Backend'},
                                {'Key': 'OS', 'Value': 'Ubuntu-20.04'}
                            ]
                        }
                    ],
                    'Monitoring': {'Enabled': True},
                    'MetadataOptions': {
                        'HttpEndpoint': 'enabled',
                        'HttpTokens': 'required',
                        'HttpPutResponseHopLimit': 2
                    }
                },
                TagSpecifications=[
                    {
                        'ResourceType': 'launch-template',
                        'Tags': [
                            {'Key': 'Name', 'Value': template_name},
                            {'Key': 'Project', 'Value': 'MERN-Microservices'},
                            {'Key': 'OS', 'Value': 'Ubuntu'}
                        ]
                    }
                ]
            )
            
            template_id = response['LaunchTemplate']['LaunchTemplateId']
            print(f"✅ Ubuntu launch template created: {template_id}")
            return template_id
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidLaunchTemplateName.AlreadyExistsException':
                # Try to get existing template
                try:
                    response = self.ec2.describe_launch_templates(
                        LaunchTemplateNames=[template_name]
                    )
                    template_id = response['LaunchTemplates'][0]['LaunchTemplateId']
                    print(f"✅ Using existing Ubuntu launch template: {template_id}")
                    return template_id
                except ClientError:
                    print(f"❌ Launch template exists but cannot retrieve it")
                    return None
            else:
                print(f"❌ Error creating launch template: {e}")
                return None
    
    def create_application_load_balancer(self, vpc_id, subnet_ids, security_group_id):
        """Create Application Load Balancer for backend services"""
        alb_name = 'MERN-Ubuntu-Backend-ALB'
        
        # Check if ALB already exists
        try:
            response = self.elbv2.describe_load_balancers(Names=[alb_name])
            if response['LoadBalancers']:
                existing_alb = response['LoadBalancers'][0]
                alb_arn = existing_alb['LoadBalancerArn']
                alb_dns = existing_alb['DNSName']
                print(f"✅ ALB already exists: {alb_arn}")
                print(f"🌐 ALB DNS: {alb_dns}")
                
                # Get existing target groups
                target_groups = {}
                try:
                    tg_response = self.elbv2.describe_target_groups()
                    for tg in tg_response['TargetGroups']:
                        if 'MERN-Ubuntu-Hello-TG' in tg['TargetGroupName']:
                            target_groups['hello'] = tg['TargetGroupArn']
                        elif 'MERN-Ubuntu-Profile-TG' in tg['TargetGroupName']:
                            target_groups['profile'] = tg['TargetGroupArn']
                    print(f"✅ Found existing target groups: {list(target_groups.keys())}")
                except ClientError as e:
                    print(f"⚠️  Could not retrieve target groups: {e}")
                
                return alb_arn, alb_dns, target_groups
        except ClientError as e:
            if e.response['Error']['Code'] != 'LoadBalancerNotFound':
                print(f"⚠️  Error checking existing ALB: {e}")
        
        try:
            # Create ALB
            response = self.elbv2.create_load_balancer(
                Name=alb_name,
                Subnets=subnet_ids,
                SecurityGroups=[security_group_id],
                Scheme='internet-facing',
                Tags=[
                    {'Key': 'Name', 'Value': alb_name},
                    {'Key': 'Project', 'Value': 'MERN-Microservices'},
                    {'Key': 'Environment', 'Value': 'Production'},
                    {'Key': 'OS', 'Value': 'Ubuntu'}
                ],
                Type='application',
                IpAddressType='ipv4'
            )
            
            alb_arn = response['LoadBalancers'][0]['LoadBalancerArn']
            alb_dns = response['LoadBalancers'][0]['DNSName']
            
            print(f"✅ ALB created: {alb_arn}")
            print(f"🌐 ALB DNS: {alb_dns}")
            
            # Create target groups
            target_groups = {}
            
            # Hello Service Target Group
            try:
                hello_tg_response = self.elbv2.create_target_group(
                    Name='MERN-Ubuntu-Hello-TG',
                    Protocol='HTTP',
                    Port=3001,
                    VpcId=vpc_id,
                    HealthCheckEnabled=True,
                    HealthCheckIntervalSeconds=30,
                    HealthCheckPath='/health',
                    HealthCheckProtocol='HTTP',
                    HealthCheckTimeoutSeconds=5,
                    HealthyThresholdCount=2,
                    UnhealthyThresholdCount=3,
                    Tags=[
                        {'Key': 'Name', 'Value': 'MERN-Ubuntu-Hello-TG'},
                        {'Key': 'Service', 'Value': 'hello-service'},
                        {'Key': 'OS', 'Value': 'Ubuntu'}
                    ]
                )
                target_groups['hello'] = hello_tg_response['TargetGroups'][0]['TargetGroupArn']
            except ClientError as e:
                if 'already exists' in str(e):
                    # Get existing target group
                    tg_response = self.elbv2.describe_target_groups(Names=['MERN-Ubuntu-Hello-TG'])
                    target_groups['hello'] = tg_response['TargetGroups'][0]['TargetGroupArn']
                    print(f"✅ Using existing Hello target group")
                else:
                    raise e
            
            # Profile Service Target Group
            try:
                profile_tg_response = self.elbv2.create_target_group(
                    Name='MERN-Ubuntu-Profile-TG',
                    Protocol='HTTP',
                    Port=3002,
                    VpcId=vpc_id,
                    HealthCheckEnabled=True,
                    HealthCheckIntervalSeconds=30,
                    HealthCheckPath='/health',
                    HealthCheckProtocol='HTTP',
                    HealthCheckTimeoutSeconds=5,
                    HealthyThresholdCount=2,
                    UnhealthyThresholdCount=3,
                    Tags=[
                        {'Key': 'Name', 'Value': 'MERN-Ubuntu-Profile-TG'},
                        {'Key': 'Service', 'Value': 'profile-service'},
                        {'Key': 'OS', 'Value': 'Ubuntu'}
                    ]
                )
                target_groups['profile'] = profile_tg_response['TargetGroups'][0]['TargetGroupArn']
            except ClientError as e:
                if 'already exists' in str(e):
                    # Get existing target group
                    tg_response = self.elbv2.describe_target_groups(Names=['MERN-Ubuntu-Profile-TG'])
                    target_groups['profile'] = tg_response['TargetGroups'][0]['TargetGroupArn']
                    print(f"✅ Using existing Profile target group")
                else:
                    raise e
            
            # Create listeners
            # Default listener (Hello Service)
            try:
                self.elbv2.create_listener(
                    LoadBalancerArn=alb_arn,
                    Protocol='HTTP',
                    Port=80,
                    DefaultActions=[
                        {
                            'Type': 'forward',
                            'TargetGroupArn': target_groups['hello']
                        }
                    ]
                )
            except ClientError as e:
                if 'already exists' not in str(e):
                    raise e
                print(f"✅ Listener already exists")
            
            # Listener rule for Profile Service
            try:
                listener_response = self.elbv2.describe_listeners(LoadBalancerArn=alb_arn)
                listener_arn = listener_response['Listeners'][0]['ListenerArn']
                
                self.elbv2.create_rule(
                    ListenerArn=listener_arn,
                    Priority=100,
                    Conditions=[
                        {
                            'Field': 'path-pattern',
                            'Values': ['/api/profile*']
                        }
                    ],
                    Actions=[
                        {
                            'Type': 'forward',
                            'TargetGroupArn': target_groups['profile']
                        }
                    ]
                )
            except ClientError as e:
                if 'already exists' not in str(e) and 'Priority is already in use' not in str(e):
                    raise e
                print(f"✅ Listener rule already exists")
            
            print(f"✅ Target groups created: {list(target_groups.keys())}")
            
            return alb_arn, alb_dns, target_groups
            
        except ClientError as e:
            print(f"❌ Error creating ALB: {e}")
            return None, None, None
    
    def create_auto_scaling_group(self, template_id, subnet_ids, target_group_arns):
        """Create Ubuntu-optimized Auto Scaling Group"""
        asg_name = 'MERN-Ubuntu-Backend-ASG'
        
        # Check if ASG already exists
        try:
            response = self.autoscaling.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )
            if response['AutoScalingGroups']:
                print(f"✅ Auto Scaling Group already exists: {asg_name}")
                
                # Update existing ASG with new template
                try:
                    self.autoscaling.update_auto_scaling_group(
                        AutoScalingGroupName=asg_name,
                        LaunchTemplate={
                            'LaunchTemplateId': template_id,
                            'Version': '$Latest'
                        }
                    )
                    print(f"✅ ASG updated with new launch template: {template_id}")
                    
                    # Start instance refresh to replace old instances
                    self.autoscaling.start_instance_refresh(
                        AutoScalingGroupName=asg_name,
                        Strategy='Rolling',
                        DesiredConfiguration={
                            'LaunchTemplate': {
                                'LaunchTemplateId': template_id,
                                'Version': '$Latest'
                            }
                        },
                        Preferences={
                            'InstanceWarmup': 300,
                            'MinHealthyPercentage': 50
                        }
                    )
                    print(f"✅ Instance refresh started for ASG: {asg_name}")
                    return True
                except ClientError as e:
                    print(f"⚠️  Could not update ASG: {e}")
                    return True  # Continue anyway
        except ClientError as e:
            if e.response['Error']['Code'] != 'ValidationError':
                print(f"⚠️  Error checking existing ASG: {e}")
        
        try:
            # Create Auto Scaling Group
            self.autoscaling.create_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                LaunchTemplate={
                    'LaunchTemplateId': template_id,
                    'Version': '$Latest'
                },
                MinSize=2,
                MaxSize=6,
                DesiredCapacity=2,
                VPCZoneIdentifier=','.join(subnet_ids),
                TargetGroupARNs=list(target_group_arns.values()),
                HealthCheckType='ELB',
                HealthCheckGracePeriod=300,
                DefaultCooldown=300,
                Tags=[
                    {
                        'Key': 'Name',
                        'Value': asg_name,
                        'PropagateAtLaunch': True,
                        'ResourceId': asg_name,
                        'ResourceType': 'auto-scaling-group'
                    },
                    {
                        'Key': 'Project',
                        'Value': 'MERN-Microservices',
                        'PropagateAtLaunch': True,
                        'ResourceId': asg_name,
                        'ResourceType': 'auto-scaling-group'
                    },
                    {
                        'Key': 'OS',
                        'Value': 'Ubuntu-20.04',
                        'PropagateAtLaunch': True,
                        'ResourceId': asg_name,
                        'ResourceType': 'auto-scaling-group'
                    }
                ]
            )
            
            print(f"✅ Auto Scaling Group created: {asg_name}")
            
            # Create scaling policy
            self._create_scaling_policy(asg_name)
            
            return True
            
        except ClientError as e:
            if 'already exists' in str(e):
                print(f"✅ Auto Scaling Group already exists: {asg_name}")
                return True
            else:
                print(f"❌ Error creating ASG: {e}")
                return False
    
    def _create_scaling_policy(self, asg_name):
        """Create Ubuntu-optimized scaling policy for ASG"""
        try:
            # Target tracking scaling policy
            scale_up_policy = self.autoscaling.put_scaling_policy(
                AutoScalingGroupName=asg_name,
                PolicyName='MERN-Ubuntu-Backend-Scale-Up',
                PolicyType='TargetTrackingScaling',
                TargetTrackingConfiguration={
                    'TargetValue': 65.0,  # Lower threshold for Ubuntu
                    'PredefinedMetricSpecification': {
                        'PredefinedMetricType': 'ASGAverageCPUUtilization'
                    },
                    'DisableScaleIn': False
                }
            )
            print(f"✅ Ubuntu-optimized scaling policies created")
        except ClientError as e:
            if 'already exists' not in str(e):
                print(f"⚠️  Could not create scaling policy: {e}")
            else:
                print(f"✅ Scaling policy already exists")
    
    def deploy_ubuntu_backend_infrastructure(self, infrastructure_info):
        """Deploy complete Ubuntu backend infrastructure"""
        print("🚀 Deploying Ubuntu-optimized MERN backend infrastructure with ASG...")
        
        # Extract infrastructure info
        vpc_id = infrastructure_info['vpc_id']
        public_subnets = infrastructure_info['public_subnets']
        
        # Get security groups from infrastructure info
        backend_sg_id = infrastructure_info['security_groups']['MERN-Backend-SG']
        alb_sg_id = infrastructure_info['security_groups']['MERN-ALB-SG']
        
        # Create IAM role for Ubuntu instances
        role_name = self.create_instance_role()
        if not role_name:
            return False
        
        # Create Ubuntu launch template
        template_id = self.create_launch_template(backend_sg_id, public_subnets)
        if not template_id:
            return False
        
        # Create ALB
        alb_arn, alb_dns, target_groups = self.create_application_load_balancer(
            vpc_id, public_subnets, alb_sg_id
        )
        if not alb_arn:
            return False
        
        # Create/Update ASG
        success = self.create_auto_scaling_group(template_id, public_subnets, target_groups)
        if not success:
            return False
        
        print(f"\n🎉 Ubuntu MERN Backend infrastructure deployed successfully!")
        print(f"📋 Deployment Summary:")
        print(f"   Launch Template: {template_id}")
        print(f"   ALB DNS: {alb_dns}")
        print(f"   Auto Scaling Group: MERN-Ubuntu-Backend-ASG")
        print(f"   Operating System: Ubuntu 20.04 LTS")
        print(f"   Instance Type: t3.medium")
        print(f"   Min/Max/Desired: 2/6/2 instances")
        print(f"   Health Check: ELB")
        print(f"   Scaling Policy: Target 65% CPU")
        
        # Save deployment info to States folder
        states_dir = 'States'
        if not os.path.exists(states_dir):
            os.makedirs(states_dir)
            
        deployment_info = {
            'template_id': template_id,
            'alb_arn': alb_arn,
            'alb_dns': alb_dns,
            'target_groups': target_groups,
            'asg_name': 'MERN-Ubuntu-Backend-ASG',
            'os': 'Ubuntu-20.04',
            'instance_type': 't3.medium'
        }
        
        output_file = os.path.join(states_dir, 'Ubuntu-Backend-Deploy-Info.json')
        with open(output_file, 'w') as f:
            json.dump(deployment_info, f, indent=2)
        
        print(f"💾 Ubuntu backend deployment info saved to '{output_file}'")
        return True


def main():
    """Main function to deploy Ubuntu backend infrastructure"""
    
    # Load infrastructure info from States folder
    infrastructure_file = 'States/VPC-Deploy-Info.json'
    try:
        with open(infrastructure_file, 'r') as f:
            infrastructure_info = json.load(f)
    except FileNotFoundError:
        print(f"❌ {infrastructure_file} not found!")
        print("   Please run vpc_infrastructure.py first.")
        return
    
    deployment = UbuntuASGDeployment()
    
    try:
        success = deployment.deploy_ubuntu_backend_infrastructure(infrastructure_info)
        if success:
            print("\n✅ Ubuntu MERN Backend infrastructure deployment completed!")
            print("\n📊 Next Steps:")
            print("   1. Wait 5-10 minutes for instances to be ready")
            print("   2. Check ALB target group health")
            print("   3. Test backend services via ALB DNS")
            print("   4. Monitor CloudWatch metrics")
            print("\n🔗 Service Endpoints:")
            print("   Hello Service: http://<ALB-DNS>/")
            print("   Profile Service: http://<ALB-DNS>/api/profile")
            print("\n🔧 Debugging Commands (SSH as ubuntu user):")
            print("   ./health-check.sh           - Complete health check")
            print("   ./manage-services.sh status  - Service status")
            print("   ./manage-services.sh logs    - View logs")
            print("   ./manage-services.sh restart - Restart services")
            print("   sudo cat /var/log/user-data.log - View deployment logs")
            print("\n🐧 Ubuntu-specific features:")
            print("   - Docker CE with official Ubuntu packages")
            print("   - Enhanced CloudWatch monitoring")
            print("   - Comprehensive health checking")
            print("   - Service management scripts")
        else:
            print("\n❌ Ubuntu backend infrastructure deployment failed!")
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()
