import boto3
import time
from botocore.exceptions import ClientError

# ----------------------------------------
# 🔧 CONFIGURE THESE VARIABLES
# ----------------------------------------
region = "ap-south-1"
vpc_id = "vpc-xxxxxxxxx"  # Replace with your VPC ID
subnet_ids = ["subnet-0fe9c16f3384ed76e", "subnet-xxxxxxxxx"]  # Add more subnets for ALB
security_group_id = "sg-0d87019135757e907"
asg_name = "prince-backend-asg"
alb_name = "prince-backend-alb"
target_group_name = "prince-backend-tg"

# Initialize clients
elbv2_client = boto3.client("elbv2", region_name=region)
autoscaling_client = boto3.client("autoscaling", region_name=region)
ec2_client = boto3.client("ec2", region_name=region)

def get_vpc_subnets():
    """Get all available subnets in the VPC"""
    try:
        response = ec2_client.describe_subnets(
            Filters=[
                {"Name": "vpc-id", "Values": [vpc_id]},
                {"Name": "state", "Values": ["available"]}
            ]
        )
        return [subnet["SubnetId"] for subnet in response["Subnets"]]
    except ClientError as e:
        print(f"❌ Error getting subnets: {e}")
        return []

def create_target_group():
    """Create target group for backend instances"""
    try:
        print("🎯 Creating Target Group...")
        
        response = elbv2_client.create_target_group(
            Name=target_group_name,
            Protocol="HTTP",
            Port=80,
            VpcId=vpc_id,
            HealthCheckProtocol="HTTP",
            HealthCheckPath="/",  # Adjust based on your backend health check endpoint
            HealthCheckPort="80",
            HealthCheckIntervalSeconds=30,
            HealthCheckTimeoutSeconds=5,
            HealthyThresholdCount=2,
            UnhealthyThresholdCount=3,
            TargetType="instance",
            Tags=[
                {"Key": "Name", "Value": target_group_name},
                {"Key": "Project", "Value": "MERN-Deployment"}
            ]
        )
        
        target_group_arn = response["TargetGroups"][0]["TargetGroupArn"]
        print(f"✅ Target Group created: {target_group_arn}")
        return target_group_arn
        
    except ClientError as e:
        if "already exists" in str(e):
            print(f"ℹ️ Target Group '{target_group_name}' already exists")
            # Get existing target group ARN
            response = elbv2_client.describe_target_groups(Names=[target_group_name])
            return response["TargetGroups"][0]["TargetGroupArn"]
        else:
            print(f"❌ Error creating target group: {e}")
            return None

def create_application_load_balancer(target_group_arn):
    """Create Application Load Balancer"""
    try:
        print("⚖️ Creating Application Load Balancer...")
        
        # Get available subnets
        available_subnets = get_vpc_subnets()
        if len(available_subnets) < 2:
            print("❌ ALB requires at least 2 subnets in different AZs")
            return None
            
        response = elbv2_client.create_load_balancer(
            Name=alb_name,
            Subnets=available_subnets[:2],  # Use first 2 subnets
            SecurityGroups=[security_group_id],
            Scheme="internet-facing",
            Tags=[
                {"Key": "Name", "Value": alb_name},
                {"Key": "Project", "Value": "MERN-Deployment"}
            ],
            Type="application",
            IpAddressType="ipv4"
        )
        
        alb_arn = response["LoadBalancers"][0]["LoadBalancerArn"]
        alb_dns = response["LoadBalancers"][0]["DNSName"]
        
        print(f"✅ Application Load Balancer created:")
        print(f"   ARN: {alb_arn}")
        print(f"   DNS: {alb_dns}")
        
        # Wait for ALB to be active
        print("⏳ Waiting for ALB to be active...")
        waiter = elbv2_client.get_waiter('load_balancer_available')
        waiter.wait(LoadBalancerArns=[alb_arn])
        
        # Create listener
        print("🎧 Creating ALB Listener...")
        elbv2_client.create_listener(
            LoadBalancerArn=alb_arn,
            Protocol="HTTP",
            Port=80,
            DefaultActions=[
                {
                    "Type": "forward",
                    "TargetGroupArn": target_group_arn
                }
            ]
        )
        
        print("✅ ALB Listener created")
        return alb_arn, alb_dns
        
    except ClientError as e:
        if "already exists" in str(e):
            print(f"ℹ️ Load Balancer '{alb_name}' already exists")
            # Get existing ALB
            response = elbv2_client.describe_load_balancers(Names=[alb_name])
            alb_arn = response["LoadBalancers"][0]["LoadBalancerArn"]
            alb_dns = response["LoadBalancers"][0]["DNSName"]
            return alb_arn, alb_dns
        else:
            print(f"❌ Error creating load balancer: {e}")
            return None, None

def attach_asg_to_target_group(target_group_arn):
    """Attach Auto Scaling Group to Target Group"""
    try:
        print("🔗 Attaching ASG to Target Group...")
        
        autoscaling_client.attach_load_balancer_target_groups(
            AutoScalingGroupName=asg_name,
            TargetGroupARNs=[target_group_arn]
        )
        
        print("✅ ASG attached to Target Group successfully")
        
    except ClientError as e:
        print(f"❌ Error attaching ASG to target group: {e}")

def main():
    """Main function to create complete load balancer setup"""
    print("🚀 Setting up Application Load Balancer for Backend...")
    
    # Step 1: Create Target Group
    target_group_arn = create_target_group()
    if not target_group_arn:
        print("❌ Failed to create target group")
        return
    
    # Step 2: Create Application Load Balancer
    alb_arn, alb_dns = create_application_load_balancer(target_group_arn)
    if not alb_arn:
        print("❌ Failed to create load balancer")
        return
    
    # Step 3: Attach ASG to Target Group
    attach_asg_to_target_group(target_group_arn)
    
    print("\n🎉 Load Balancer Setup Complete!")
    print(f"   Target Group ARN: {target_group_arn}")
    print(f"   Load Balancer ARN: {alb_arn}")
    print(f"   Load Balancer DNS: {alb_dns}")
    print(f"   Backend API URL: http://{alb_dns}")
    
    return alb_dns

if __name__ == "__main__":
    backend_url = main()