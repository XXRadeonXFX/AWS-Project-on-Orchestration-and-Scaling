#!/usr/bin/env python3
"""
Deploy Auto Scaling Group for MERN Backend Services
"""
import boto3
import json
import base64
import time
import os
from botocore.exceptions import ClientError


class ASGDeployment:
    def __init__(self, region='ap-south-1'):
        self.region = region
        self.ec2 = boto3.client('ec2', region_name=region)
        self.autoscaling = boto3.client('autoscaling', region_name=region)
        self.elbv2 = boto3.client('elbv2', region_name=region)
        self.iam = boto3.client('iam', region_name=region)
        
    def create_instance_role(self):
        """Create IAM role for EC2 instances"""
        role_name = 'EC2-ECR-CloudWatch-Role'
        
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
                Description='IAM role for EC2 instances to access ECR and CloudWatch'
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
        """Create launch template for ASG instances"""
        
        template_name = 'MERN-Backend-Template'
        
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
        
        # User data script to install Docker and run containers
        user_data_script = """#!/bin/bash
yum update -y
yum install -y docker
# Start Docker service
systemctl start docker
systemctl enable docker
# Add ec2-user to docker group
usermod -a -G docker ec2-user

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Login to ECR
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 975050024946.dkr.ecr.ap-south-1.amazonaws.com

# Create docker-compose.yml for backend services
cat > /home/ec2-user/docker-compose.yml << 'EOF'
version: '3.8'
services:
  hello-service:
    image: 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:hs-radeon
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
    
  profile-service:
    image: 975050024946.dkr.ecr.ap-south-1.amazonaws.com/prince-reg:ps-radeon
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
EOF

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Start services
cd /home/ec2-user
/usr/local/bin/docker-compose up -d

# Install CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
rpm -U ./amazon-cloudwatch-agent.rpm

# Create CloudWatch config
cat > /opt/aws/amazon-cloudwatch-agent/bin/config.json << 'EOF'
{
    "metrics": {
        "namespace": "MERN/Backend",
        "metrics_collected": {
            "cpu": {
                "measurement": ["cpu_usage_idle", "cpu_usage_iowait", "cpu_usage_user", "cpu_usage_system"],
                "metrics_collection_interval": 60
            },
            "disk": {
                "measurement": ["used_percent"],
                "metrics_collection_interval": 60,
                "resources": ["*"]
            },
            "mem": {
                "measurement": ["mem_used_percent"],
                "metrics_collection_interval": 60
            }
        }
    }
}
EOF

# Start CloudWatch agent
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/bin/config.json -s

echo "Backend services deployment completed" > /var/log/user-data.log
"""
        
        # Encode user data
        user_data_encoded = base64.b64encode(user_data_script.encode()).decode()
        
        try:
            # Create launch template
            response = self.ec2.create_launch_template(
                LaunchTemplateName=template_name,
                LaunchTemplateData={
                    'ImageId': 'ami-0c2af51e265bd5e0e',  # Amazon Linux 2 AMI (ap-south-1)
                    'InstanceType': 't3.medium',
                    'KeyName': 'prince-pair-x',  # SSH key pair
                    'SecurityGroupIds': [security_group_id],
                    'UserData': user_data_encoded,
                    'IamInstanceProfile': {
                        'Name': 'EC2-ECR-CloudWatch-Role'
                    },
                    'TagSpecifications': [
                        {
                            'ResourceType': 'instance',
                            'Tags': [
                                {'Key': 'Name', 'Value': 'MERN-Backend-Instance'},
                                {'Key': 'Project', 'Value': 'MERN-Microservices'},
                                {'Key': 'Environment', 'Value': 'Production'},
                                {'Key': 'Service', 'Value': 'Backend'}
                            ]
                        }
                    ],
                    'Monitoring': {'Enabled': True}
                },
                TagSpecifications=[
                    {
                        'ResourceType': 'launch-template',
                        'Tags': [
                            {'Key': 'Name', 'Value': template_name},
                            {'Key': 'Project', 'Value': 'MERN-Microservices'}
                        ]
                    }
                ]
            )
            
            template_id = response['LaunchTemplate']['LaunchTemplateId']
            print(f"✅ Launch template created: {template_id}")
            return template_id
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidLaunchTemplateName.AlreadyExistsException':
                # Try to get existing template
                try:
                    response = self.ec2.describe_launch_templates(
                        LaunchTemplateNames=[template_name]
                    )
                    template_id = response['LaunchTemplates'][0]['LaunchTemplateId']
                    print(f"✅ Using existing launch template: {template_id}")
                    return template_id
                except ClientError:
                    print(f"❌ Launch template exists but cannot retrieve it")
                    return None
            else:
                print(f"❌ Error creating launch template: {e}")
                return None
    
    def create_application_load_balancer(self, vpc_id, subnet_ids, security_group_id):
        """Create Application Load Balancer for backend services"""
        alb_name = 'MERN-Backend-ALB'
        
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
                        if 'MERN-Hello-TG' in tg['TargetGroupName']:
                            target_groups['hello'] = tg['TargetGroupArn']
                        elif 'MERN-Profile-TG' in tg['TargetGroupName']:
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
                    {'Key': 'Environment', 'Value': 'Production'}
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
                    Name='MERN-Hello-TG',
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
                        {'Key': 'Name', 'Value': 'MERN-Hello-TG'},
                        {'Key': 'Service', 'Value': 'hello-service'}
                    ]
                )
                target_groups['hello'] = hello_tg_response['TargetGroups'][0]['TargetGroupArn']
            except ClientError as e:
                if 'already exists' in str(e):
                    # Get existing target group
                    tg_response = self.elbv2.describe_target_groups(Names=['MERN-Hello-TG'])
                    target_groups['hello'] = tg_response['TargetGroups'][0]['TargetGroupArn']
                    print(f"✅ Using existing Hello target group")
                else:
                    raise e
            
            # Profile Service Target Group
            try:
                profile_tg_response = self.elbv2.create_target_group(
                    Name='MERN-Profile-TG',
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
                        {'Key': 'Name', 'Value': 'MERN-Profile-TG'},
                        {'Key': 'Service', 'Value': 'profile-service'}
                    ]
                )
                target_groups['profile'] = profile_tg_response['TargetGroups'][0]['TargetGroupArn']
            except ClientError as e:
                if 'already exists' in str(e):
                    # Get existing target group
                    tg_response = self.elbv2.describe_target_groups(Names=['MERN-Profile-TG'])
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
            if 'already exists' in str(e):
                print(f"⚠️  ALB components already exist, trying to retrieve...")
                return self.create_application_load_balancer(vpc_id, subnet_ids, security_group_id)
            else:
                print(f"❌ Error creating ALB: {e}")
                return None, None, None
    
    def create_auto_scaling_group(self, template_id, subnet_ids, target_group_arns):
        """Create Auto Scaling Group"""
        asg_name = 'MERN-Backend-ASG'
        
        # Check if ASG already exists
        try:
            response = self.autoscaling.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )
            if response['AutoScalingGroups']:
                print(f"✅ Auto Scaling Group already exists: {asg_name}")
                
                # Check if scaling policy exists
                try:
                    policies_response = self.autoscaling.describe_policies(
                        AutoScalingGroupName=asg_name
                    )
                    if policies_response['ScalingPolicies']:
                        print(f"✅ Scaling policies already exist")
                    else:
                        # Create scaling policy if it doesn't exist
                        self._create_scaling_policy(asg_name)
                except ClientError as e:
                    print(f"⚠️  Could not check scaling policies: {e}")
                
                return True
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
        """Create scaling policy for ASG"""
        try:
            scale_up_policy = self.autoscaling.put_scaling_policy(
                AutoScalingGroupName=asg_name,
                PolicyName='MERN-Backend-Scale-Up',
                PolicyType='TargetTrackingScaling',
                TargetTrackingConfiguration={
                    'TargetValue': 70.0,
                    'PredefinedMetricSpecification': {
                        'PredefinedMetricType': 'ASGAverageCPUUtilization'
                    }
                }
            )
            print(f"✅ Scaling policies created")
        except ClientError as e:
            if 'already exists' not in str(e):
                print(f"⚠️  Could not create scaling policy: {e}")
            else:
                print(f"✅ Scaling policy already exists")
    
    def deploy_backend_infrastructure(self, infrastructure_info):
        """Deploy complete backend infrastructure"""
        print("🚀 Deploying backend infrastructure with ASG...")
        
        # Extract infrastructure info
        vpc_id = infrastructure_info['vpc_id']
        public_subnets = infrastructure_info['public_subnets']
        
        # Get security groups from infrastructure info
        backend_sg_id = infrastructure_info['security_groups']['MERN-Backend-SG']
        alb_sg_id = infrastructure_info['security_groups']['MERN-ALB-SG']
        
        # Create IAM role for instances
        role_name = self.create_instance_role()
        if not role_name:
            return False
        
        # Create launch template
        template_id = self.create_launch_template(backend_sg_id, public_subnets)
        if not template_id:
            return False
        
        # Create ALB
        alb_arn, alb_dns, target_groups = self.create_application_load_balancer(
            vpc_id, public_subnets, alb_sg_id
        )
        if not alb_arn:
            return False
        
        # Create ASG
        success = self.create_auto_scaling_group(template_id, public_subnets, target_groups)
        if not success:
            return False
        
        print(f"\n🎉 Backend infrastructure deployed successfully!")
        print(f"📋 Deployment Summary:")
        print(f"   Launch Template: {template_id}")
        print(f"   ALB DNS: {alb_dns}")
        print(f"   Auto Scaling Group: MERN-Backend-ASG")
        print(f"   Min/Max/Desired: 2/6/2 instances")
        print(f"   Health Check: ELB")
        print(f"   Scaling Policy: Target 70% CPU")
        
        # Save deployment info to States folder
        states_dir = 'States'
        if not os.path.exists(states_dir):
            os.makedirs(states_dir)
            
        deployment_info = {
            'template_id': template_id,
            'alb_arn': alb_arn,
            'alb_dns': alb_dns,
            'target_groups': target_groups,
            'asg_name': 'MERN-Backend-ASG'
        }
        
        output_file = os.path.join(states_dir, 'Backend-Deploy-Info.json')
        with open(output_file, 'w') as f:
            json.dump(deployment_info, f, indent=2)
        
        print(f"💾 Backend deployment info saved to '{output_file}'")
        return True


def main():
    """Main function to deploy backend infrastructure"""
    
    # Load infrastructure info from States folder
    infrastructure_file = 'States/VPC-Deploy-Info.json'
    try:
        with open(infrastructure_file, 'r') as f:
            infrastructure_info = json.load(f)
    except FileNotFoundError:
        print(f"❌ {infrastructure_file} not found!")
        print("   Please run vpc_infrastructure.py first.")
        return
    
    deployment = ASGDeployment()
    
    try:
        success = deployment.deploy_backend_infrastructure(infrastructure_info)
        if success:
            print("\n✅ Backend infrastructure deployment completed!")
            print("\n📊 Next Steps:")
            print("   1. Wait 5-10 minutes for instances to be ready")
            print("   2. Check ALB target group health")
            print("   3. Test backend services via ALB DNS")
            print("   4. Monitor CloudWatch metrics")
            print("\n🔗 Service Endpoints:")
            print("   Hello Service: http://<ALB-DNS>/")
            print("   Profile Service: http://<ALB-DNS>/api/profile")
        else:
            print("\n❌ Backend infrastructure deployment failed!")
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()