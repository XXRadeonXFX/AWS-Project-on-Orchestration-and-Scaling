import boto3

# ----------------------------------------
# 🔧 CONFIGURE THESE VARIABLES
# ----------------------------------------
region = "ap-south-1"
ami_id = "ami-0f918f7e67a3323f0"  # Amazon Linux 2 (ap-south-1)
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
# ✅ Create launch template with user-data
# ----------------------------------------
ec2_client = boto3.client('ec2', region_name=region)

user_data_script = f"""#!/bin/bash
yum update -y
yum install -y docker
systemctl start docker
systemctl enable docker
$(aws ecr get-login --no-include-email --region {region})
docker run -d -p 3000:3000 {docker_image_uri}
"""

print("➡️ Creating Launch Template...")
response = ec2_client.create_launch_template(
    LaunchTemplateName=launch_template_name,
    LaunchTemplateData={
        'ImageId': ami_id,
        'InstanceType': instance_type,
        'KeyName': key_name,
        'SecurityGroupIds': [security_group_id],
        'IamInstanceProfile': {
            'Name': iam_instance_profile_name
        },
        'UserData': user_data_script.encode('base64').decode('utf-8')
    }
)
launch_template_id = response['LaunchTemplate']['LaunchTemplateId']
print(f"✅ Launch Template created: {launch_template_id}")

# ----------------------------------------
# ✅ Create Auto Scaling Group
# ----------------------------------------
asg_client = boto3.client('autoscaling', region_name=region)

print("➡️ Creating Auto Scaling Group...")
asg_client.create_auto_scaling_group(
    AutoScalingGroupName=asg_name,
    LaunchTemplate={
        'LaunchTemplateId': launch_template_id,
        'Version': '$Latest'
    },
    MinSize=min_size,
    MaxSize=max_size,
    DesiredCapacity=desired_capacity,
    VPCZoneIdentifier=",".join(subnet_ids),
    Tags=[
        {
            'Key': 'Name',
            'Value': 'backend-ec2',
            'PropagateAtLaunch': True
        }
    ]
)
print(f"✅ ASG '{asg_name}' created with desired capacity {desired_capacity}")
