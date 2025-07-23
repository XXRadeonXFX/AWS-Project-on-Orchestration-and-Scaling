#!/usr/bin/env python3
"""
AWS VPC Infrastructure Setup using Boto3 - FIXED VERSION
Creates VPC, subnets, security groups, and networking components
"""

import boto3
import json
from botocore.exceptions import ClientError


class VPCInfrastructure:
    def __init__(self, region='ap-south-1'):
        self.region = region
        self.ec2 = boto3.client('ec2', region_name=region)
        self.vpc_id = None
        self.public_subnets = []
        self.private_subnets = []
        self.internet_gateway_id = None
        self.nat_gateway_id = None
        
    def create_vpc(self, vpc_cidr='10.0.0.0/16', vpc_name='MERN-VPC'):
        """Create VPC with specified CIDR block"""
        try:
            response = self.ec2.create_vpc(
                CidrBlock=vpc_cidr
            )
            self.vpc_id = response['Vpc']['VpcId']
            
            # Enable DNS hostnames and support separately
            self.ec2.modify_vpc_attribute(
                VpcId=self.vpc_id,
                EnableDnsHostnames={'Value': True}
            )
            
            self.ec2.modify_vpc_attribute(
                VpcId=self.vpc_id,
                EnableDnsSupport={'Value': True}
            )
            
            # Tag the VPC
            self.ec2.create_tags(
                Resources=[self.vpc_id],
                Tags=[
                    {'Key': 'Name', 'Value': vpc_name},
                    {'Key': 'Project', 'Value': 'MERN-Microservices'},
                    {'Key': 'Environment', 'Value': 'Development'}
                ]
            )
            
            print(f"✅ VPC created successfully: {self.vpc_id}")
            return self.vpc_id
            
        except ClientError as e:
            print(f"❌ Error creating VPC: {e}")
            return None
    
    def create_internet_gateway(self):
        """Create and attach Internet Gateway"""
        try:
            # Create Internet Gateway
            response = self.ec2.create_internet_gateway()
            self.internet_gateway_id = response['InternetGateway']['InternetGatewayId']
            
            # Tag the Internet Gateway
            self.ec2.create_tags(
                Resources=[self.internet_gateway_id],
                Tags=[
                    {'Key': 'Name', 'Value': 'MERN-IGW'},
                    {'Key': 'Project', 'Value': 'MERN-Microservices'}
                ]
            )
            
            # Attach to VPC
            self.ec2.attach_internet_gateway(
                InternetGatewayId=self.internet_gateway_id,
                VpcId=self.vpc_id
            )
            
            print(f"✅ Internet Gateway created and attached: {self.internet_gateway_id}")
            return self.internet_gateway_id
            
        except ClientError as e:
            print(f"❌ Error creating Internet Gateway: {e}")
            return None
    
    def create_subnets(self):
        """Create public and private subnets across AZs"""
        try:
            # Get available AZs
            azs = self.ec2.describe_availability_zones()['AvailabilityZones']
            az_names = [az['ZoneName'] for az in azs[:2]]  # Use first 2 AZs
            
            subnet_configs = [
                # Public Subnets
                {'cidr': '10.0.1.0/24', 'az': az_names[0], 'type': 'public', 'name': 'MERN-Public-1'},
                {'cidr': '10.0.2.0/24', 'az': az_names[1], 'type': 'public', 'name': 'MERN-Public-2'},
                # Private Subnets
                {'cidr': '10.0.11.0/24', 'az': az_names[0], 'type': 'private', 'name': 'MERN-Private-1'},
                {'cidr': '10.0.12.0/24', 'az': az_names[1], 'type': 'private', 'name': 'MERN-Private-2'},
            ]
            
            for config in subnet_configs:
                response = self.ec2.create_subnet(
                    VpcId=self.vpc_id,
                    CidrBlock=config['cidr'],
                    AvailabilityZone=config['az']
                )
                
                subnet_id = response['Subnet']['SubnetId']
                
                # Tag subnet
                self.ec2.create_tags(
                    Resources=[subnet_id],
                    Tags=[
                        {'Key': 'Name', 'Value': config['name']},
                        {'Key': 'Type', 'Value': config['type']},
                        {'Key': 'Project', 'Value': 'MERN-Microservices'}
                    ]
                )
                
                # Enable auto-assign public IPs for public subnets
                if config['type'] == 'public':
                    self.ec2.modify_subnet_attribute(
                        SubnetId=subnet_id,
                        MapPublicIpOnLaunch={'Value': True}
                    )
                    self.public_subnets.append(subnet_id)
                else:
                    self.private_subnets.append(subnet_id)
                
                print(f"✅ {config['type'].title()} subnet created: {subnet_id} in {config['az']}")
            
            return self.public_subnets, self.private_subnets
            
        except ClientError as e:
            print(f"❌ Error creating subnets: {e}")
            return None, None
    
    def create_route_tables(self):
        """Create and configure route tables"""
        try:
            # Create public route table
            public_rt_response = self.ec2.create_route_table(VpcId=self.vpc_id)
            public_rt_id = public_rt_response['RouteTable']['RouteTableId']
            
            # Tag public route table
            self.ec2.create_tags(
                Resources=[public_rt_id],
                Tags=[
                    {'Key': 'Name', 'Value': 'MERN-Public-RT'},
                    {'Key': 'Type', 'Value': 'Public'}
                ]
            )
            
            # Add route to Internet Gateway
            self.ec2.create_route(
                RouteTableId=public_rt_id,
                DestinationCidrBlock='0.0.0.0/0',
                GatewayId=self.internet_gateway_id
            )
            
            # Associate public subnets with public route table
            for subnet_id in self.public_subnets:
                self.ec2.associate_route_table(
                    RouteTableId=public_rt_id,
                    SubnetId=subnet_id
                )
            
            print(f"✅ Public route table created and configured: {public_rt_id}")
            
            # Create NAT Gateway (optional - for private subnet internet access)
            # Allocate Elastic IP for NAT Gateway
            eip_response = self.ec2.allocate_address(Domain='vpc')
            allocation_id = eip_response['AllocationId']
            
            # Create NAT Gateway in first public subnet
            nat_response = self.ec2.create_nat_gateway(
                SubnetId=self.public_subnets[0],
                AllocationId=allocation_id
            )
            self.nat_gateway_id = nat_response['NatGateway']['NatGatewayId']
            
            # Wait for NAT Gateway to be available
            print("⏳ Waiting for NAT Gateway to become available...")
            waiter = self.ec2.get_waiter('nat_gateway_available')
            waiter.wait(NatGatewayIds=[self.nat_gateway_id])
            
            # Create private route table
            private_rt_response = self.ec2.create_route_table(VpcId=self.vpc_id)
            private_rt_id = private_rt_response['RouteTable']['RouteTableId']
            
            # Tag private route table
            self.ec2.create_tags(
                Resources=[private_rt_id],
                Tags=[
                    {'Key': 'Name', 'Value': 'MERN-Private-RT'},
                    {'Key': 'Type', 'Value': 'Private'}
                ]
            )
            
            # Add route to NAT Gateway
            self.ec2.create_route(
                RouteTableId=private_rt_id,
                DestinationCidrBlock='0.0.0.0/0',
                NatGatewayId=self.nat_gateway_id
            )
            
            # Associate private subnets with private route table
            for subnet_id in self.private_subnets:
                self.ec2.associate_route_table(
                    RouteTableId=private_rt_id,
                    SubnetId=subnet_id
                )
            
            print(f"✅ Private route table created and configured: {private_rt_id}")
            print(f"✅ NAT Gateway created: {self.nat_gateway_id}")
            
            return public_rt_id, private_rt_id
            
        except ClientError as e:
            print(f"❌ Error creating route tables: {e}")
            return None, None
    
    def create_security_groups(self):
        """Create security groups for different components with proper access rules"""
        security_groups = {}
        
        sg_configs = [
            {
                'name': 'MERN-ALB-SG',
                'description': 'Security group for Application Load Balancer'
            },
            {
                'name': 'MERN-Frontend-SG',
                'description': 'Security group for Frontend instances'
            },
            {
                'name': 'MERN-Backend-SG',
                'description': 'Security group for Backend instances with internet and ALB access'
            }
        ]
        
        try:
            for config in sg_configs:
                response = self.ec2.create_security_group(
                    GroupName=config['name'],
                    Description=config['description'],
                    VpcId=self.vpc_id
                )
                
                sg_id = response['GroupId']
                security_groups[config['name']] = sg_id
                
                # Tag security group
                self.ec2.create_tags(
                    Resources=[sg_id],
                    Tags=[
                        {'Key': 'Name', 'Value': config['name']},
                        {'Key': 'Project', 'Value': 'MERN-Microservices'}
                    ]
                )
                
                print(f"✅ Security group created: {config['name']} ({sg_id})")
            
            # Add rules after all security groups are created
            self._add_security_group_rules(security_groups)
            
            return security_groups
            
        except ClientError as e:
            print(f"❌ Error creating security groups: {e}")
            return None
    
    def _add_security_group_rules(self, security_groups):
        """Add FIXED rules to security groups for proper MERN stack access"""
        try:
            # ALB Security Group Rules - Allow HTTP/HTTPS from internet
            print("Adding ALB security group rules...")
            self.ec2.authorize_security_group_ingress(
                GroupId=security_groups['MERN-ALB-SG'],
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 80,
                        'ToPort': 80,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTP from anywhere'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 443,
                        'ToPort': 443,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTPS from anywhere'}]
                    }
                ]
            )
            
            # Frontend Security Group Rules
            print("Adding Frontend security group rules...")
            self.ec2.authorize_security_group_ingress(
                GroupId=security_groups['MERN-Frontend-SG'],
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 3000,
                        'ToPort': 3000,
                        'UserIdGroupPairs': [{'GroupId': security_groups['MERN-ALB-SG'], 'Description': 'React app from ALB'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 3000,
                        'ToPort': 3000,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'React app from internet (dev/testing)'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 22,
                        'ToPort': 22,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'SSH access'}]
                    }
                ]
            )
            
            # FIXED Backend Security Group Rules - Allow multiple sources
            print("Adding FIXED Backend security group rules...")
            self.ec2.authorize_security_group_ingress(
                GroupId=security_groups['MERN-Backend-SG'],
                IpPermissions=[
                    # Allow ALB to access backend services
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 3001,
                        'ToPort': 3002,
                        'UserIdGroupPairs': [{'GroupId': security_groups['MERN-ALB-SG'], 'Description': 'API access from ALB'}]
                    },
                    # Allow frontend to access backend services
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 3001,
                        'ToPort': 3002,
                        'UserIdGroupPairs': [{'GroupId': security_groups['MERN-Frontend-SG'], 'Description': 'API access from frontend'}]
                    },
                    # Allow internet access to backend services (for testing and direct access)
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 3001,
                        'ToPort': 3002,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'API access from internet (testing/direct)'}]
                    },
                    # SSH access
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 22,
                        'ToPort': 22,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'SSH access'}]
                    }
                ]
            )
            
            # Backend outbound rules for Cloud MongoDB and external APIs
            print("Adding Backend outbound rules...")
            
            # First, remove default outbound rule (all traffic)
            try:
                default_rules = self.ec2.describe_security_groups(GroupIds=[security_groups['MERN-Backend-SG']])
                for rule in default_rules['SecurityGroups'][0]['IpPermissionsEgress']:
                    if rule.get('IpRanges') and rule['IpRanges'][0]['CidrIp'] == '0.0.0.0/0':
                        self.ec2.revoke_security_group_egress(
                            GroupId=security_groups['MERN-Backend-SG'],
                            IpPermissions=[rule]
                        )
            except ClientError:
                pass  # Continue if default rule doesn't exist
            
            # Add specific outbound rules
            self.ec2.authorize_security_group_egress(
                GroupId=security_groups['MERN-Backend-SG'],
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 443,
                        'ToPort': 443,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTPS for Cloud MongoDB and APIs'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 80,
                        'ToPort': 80,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTP for package downloads'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 27017,
                        'ToPort': 27017,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'MongoDB Atlas/Cloud access'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 53,
                        'ToPort': 53,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'DNS TCP'}]
                    },
                    {
                        'IpProtocol': 'udp',
                        'FromPort': 53,
                        'ToPort': 53,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'DNS UDP'}]
                    }
                ]
            )
            
            print("✅ FIXED security group rules added successfully!")
            print("   🔹 ALB can access backend services")
            print("   🔹 Frontend can access backend services") 
            print("   🔹 Internet can access backend services (for testing)")
            print("   🔹 Backend can access MongoDB Atlas and external APIs")
            
        except ClientError as e:
            if 'already exists' in str(e).lower():
                print("⚠️  Some security group rules already exist - continuing...")
            else:
                print(f"❌ Error adding security group rules: {e}")
                raise
    
    def get_infrastructure_info(self):
        """Return infrastructure information"""
        return {
            'vpc_id': self.vpc_id,
            'public_subnets': self.public_subnets,
            'private_subnets': self.private_subnets,
            'internet_gateway_id': self.internet_gateway_id,
            'nat_gateway_id': self.nat_gateway_id,
            'region': self.region
        }
    
    def deploy_infrastructure(self):
        """Deploy complete VPC infrastructure"""
        print("🚀 Starting FIXED VPC infrastructure deployment...")
        
        # Create VPC
        if not self.create_vpc():
            return False
        
        # Create Internet Gateway
        if not self.create_internet_gateway():
            return False
        
        # Create Subnets
        public_subnets, private_subnets = self.create_subnets()
        if not public_subnets:
            return False
        
        # Create Route Tables
        public_rt, private_rt = self.create_route_tables()
        if not public_rt:
            return False
        
        # Create Security Groups
        security_groups = self.create_security_groups()
        if not security_groups:
            return False
        
        print("\n🎉 FIXED VPC Infrastructure deployment completed successfully!")
        print(f"📋 Infrastructure Info:")
        info = self.get_infrastructure_info()
        for key, value in info.items():
            print(f"   {key}: {value}")
        
        print(f"\n🔐 Security Groups:")
        for sg_name, sg_id in security_groups.items():
            print(f"   {sg_name}: {sg_id}")
        
        # Save infrastructure info to States folder
        import os
        states_dir = 'States'
        if not os.path.exists(states_dir):
            os.makedirs(states_dir)
            
        output_data = {
            **info, 
            'security_groups': security_groups,
            'route_tables': {
                'public': public_rt,
                'private': private_rt
            }
        }
        
        output_file = os.path.join(states_dir, 'VPC-Deploy-Info.json')
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        print(f"💾 FIXED Infrastructure info saved to '{output_file}'")
        
        print(f"\n✨ Key Improvements in FIXED version:")
        print(f"   🔹 Backend SG allows ALB access (ports 3001-3002)")
        print(f"   🔹 Backend SG allows internet access (for testing)")
        print(f"   🔹 Backend SG allows frontend access")
        print(f"   🔹 Proper outbound rules for MongoDB Atlas")
        print(f"   🔹 DNS resolution support")
        
        return True


def main():
    """Main function to deploy FIXED VPC infrastructure"""
    infrastructure = VPCInfrastructure()
    
    try:
        success = infrastructure.deploy_infrastructure()
        if success:
            print("\n✅ All FIXED infrastructure components deployed successfully!")
            print("\n🧪 Ready for:")
            print("   - Direct backend testing (ports 3001-3002)")
            print("   - ALB-based load balancing")
            print("   - Frontend-to-backend communication")
            print("   - MongoDB Atlas connectivity")
        else:
            print("\n❌ Infrastructure deployment failed!")
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()