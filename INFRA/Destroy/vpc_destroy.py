#!/usr/bin/env python3
"""
AWS VPC Infrastructure Destroy Script using Boto3
Safely removes VPC, subnets, security groups, and all networking components
"""

import boto3
import json
import time
from botocore.exceptions import ClientError


class VPCDestroyer:
    def __init__(self, region='ap-south-1', vpc_id=None, infrastructure_file='States/VPC-Deploy-Info.json'):
        self.region = region
        self.ec2 = boto3.client('ec2', region_name=region)
        self.vpc_id = vpc_id
        self.infrastructure_file = infrastructure_file
        self.infrastructure_info = None
        
    def load_infrastructure_info(self):
        """Load infrastructure information from JSON file"""
        try:
            with open(self.infrastructure_file, 'r') as f:
                self.infrastructure_info = json.load(f)
                self.vpc_id = self.infrastructure_info.get('vpc_id')
                print(f"✅ Loaded infrastructure info from {self.infrastructure_file}")
                print(f"📋 VPC ID: {self.vpc_id}")
                return True
        except FileNotFoundError:
            print(f"⚠️  Infrastructure file {self.infrastructure_file} not found")
            if self.vpc_id:
                print(f"📋 Using provided VPC ID: {self.vpc_id}")
                return True
            return False
        except json.JSONDecodeError:
            print(f"❌ Error reading infrastructure file {self.infrastructure_file}")
            return False
    
    def get_vpc_resources(self):
        """Discover all resources associated with the VPC"""
        if not self.vpc_id:
            print("❌ No VPC ID provided")
            return None
            
        resources = {
            'instances': [],
            'load_balancers': [],
            'nat_gateways': [],
            'internet_gateways': [],
            'route_tables': [],
            'network_acls': [],
            'security_groups': [],
            'subnets': [],
            'elastic_ips': [],
            'endpoints': []
        }
        
        try:
            # Get EC2 instances
            instances_response = self.ec2.describe_instances(
                Filters=[{'Name': 'vpc-id', 'Values': [self.vpc_id]}]
            )
            for reservation in instances_response['Reservations']:
                for instance in reservation['Instances']:
                    if instance['State']['Name'] != 'terminated':
                        resources['instances'].append(instance['InstanceId'])
            
            # Get NAT Gateways
            nat_response = self.ec2.describe_nat_gateways(
                Filters=[{'Name': 'vpc-id', 'Values': [self.vpc_id]}]
            )
            for nat in nat_response['NatGateways']:
                if nat['State'] not in ['deleted', 'deleting']:
                    resources['nat_gateways'].append(nat['NatGatewayId'])
            
            # Get Internet Gateways
            igw_response = self.ec2.describe_internet_gateways(
                Filters=[{'Name': 'attachment.vpc-id', 'Values': [self.vpc_id]}]
            )
            for igw in igw_response['InternetGateways']:
                resources['internet_gateways'].append(igw['InternetGatewayId'])
            
            # Get Route Tables (exclude main route table)
            rt_response = self.ec2.describe_route_tables(
                Filters=[{'Name': 'vpc-id', 'Values': [self.vpc_id]}]
            )
            for rt in rt_response['RouteTables']:
                # Skip main route table
                is_main = any(assoc.get('Main', False) for assoc in rt.get('Associations', []))
                if not is_main:
                    resources['route_tables'].append(rt['RouteTableId'])
            
            # Get Security Groups (exclude default)
            sg_response = self.ec2.describe_security_groups(
                Filters=[{'Name': 'vpc-id', 'Values': [self.vpc_id]}]
            )
            for sg in sg_response['SecurityGroups']:
                if sg['GroupName'] != 'default':
                    resources['security_groups'].append(sg['GroupId'])
            
            # Get Subnets
            subnet_response = self.ec2.describe_subnets(
                Filters=[{'Name': 'vpc-id', 'Values': [self.vpc_id]}]
            )
            for subnet in subnet_response['Subnets']:
                resources['subnets'].append(subnet['SubnetId'])
            
            # Get VPC Endpoints
            endpoint_response = self.ec2.describe_vpc_endpoints(
                Filters=[{'Name': 'vpc-id', 'Values': [self.vpc_id]}]
            )
            for endpoint in endpoint_response['VpcEndpoints']:
                if endpoint['State'] not in ['deleted', 'deleting']:
                    resources['endpoints'].append(endpoint['VpcEndpointId'])
            
            print(f"📋 Discovered VPC resources:")
            for resource_type, resource_list in resources.items():
                if resource_list:
                    print(f"   {resource_type}: {len(resource_list)} items")
            
            return resources
            
        except ClientError as e:
            print(f"❌ Error discovering VPC resources: {e}")
            return None
    
    def terminate_instances(self, instance_ids):
        """Terminate EC2 instances"""
        if not instance_ids:
            print("ℹ️  No EC2 instances to terminate")
            return True
            
        try:
            print(f"🔄 Terminating {len(instance_ids)} EC2 instances...")
            self.ec2.terminate_instances(InstanceIds=instance_ids)
            
            # Wait for instances to terminate
            print("⏳ Waiting for instances to terminate...")
            waiter = self.ec2.get_waiter('instance_terminated')
            waiter.wait(InstanceIds=instance_ids)
            
            print(f"✅ Successfully terminated {len(instance_ids)} instances")
            return True
            
        except ClientError as e:
            print(f"❌ Error terminating instances: {e}")
            return False
    
    def delete_load_balancers(self):
        """Delete Application Load Balancers"""
        try:
            # Use ELBv2 client for Application Load Balancers
            elbv2 = boto3.client('elbv2', region_name=self.region)
            
            # Get load balancers in the VPC
            response = elbv2.describe_load_balancers()
            vpc_load_balancers = []
            
            for lb in response['LoadBalancers']:
                if lb.get('VpcId') == self.vpc_id:
                    vpc_load_balancers.append(lb['LoadBalancerArn'])
            
            if not vpc_load_balancers:
                print("ℹ️  No load balancers to delete")
                return True
            
            for lb_arn in vpc_load_balancers:
                print(f"🔄 Deleting load balancer: {lb_arn}")
                elbv2.delete_load_balancer(LoadBalancerArn=lb_arn)
            
            print(f"✅ Successfully deleted {len(vpc_load_balancers)} load balancers")
            return True
            
        except ClientError as e:
            print(f"❌ Error deleting load balancers: {e}")
            return False
    
    def delete_nat_gateways(self, nat_gateway_ids):
        """Delete NAT Gateways and release associated Elastic IPs"""
        if not nat_gateway_ids:
            print("ℹ️  No NAT gateways to delete")
            return True
            
        try:
            # Get NAT Gateway details to find associated Elastic IPs
            nat_response = self.ec2.describe_nat_gateways(NatGatewayIds=nat_gateway_ids)
            elastic_ips = []
            
            for nat in nat_response['NatGateways']:
                for address in nat.get('NatGatewayAddresses', []):
                    if 'AllocationId' in address:
                        elastic_ips.append(address['AllocationId'])
            
            # Delete NAT Gateways
            for nat_id in nat_gateway_ids:
                print(f"🔄 Deleting NAT Gateway: {nat_id}")
                self.ec2.delete_nat_gateway(NatGatewayId=nat_id)
            
            # Wait for NAT Gateways to be deleted
            print("⏳ Waiting for NAT Gateways to be deleted...")
            waiter = self.ec2.get_waiter('nat_gateway_deleted')
            waiter.wait(NatGatewayIds=nat_gateway_ids)
            
            # Release Elastic IPs
            for eip_id in elastic_ips:
                try:
                    print(f"🔄 Releasing Elastic IP: {eip_id}")
                    self.ec2.release_address(AllocationId=eip_id)
                except ClientError as e:
                    print(f"⚠️  Could not release Elastic IP {eip_id}: {e}")
            
            print(f"✅ Successfully deleted {len(nat_gateway_ids)} NAT gateways")
            return True
            
        except ClientError as e:
            print(f"❌ Error deleting NAT gateways: {e}")
            return False
    
    def delete_vpc_endpoints(self, endpoint_ids):
        """Delete VPC Endpoints"""
        if not endpoint_ids:
            print("ℹ️  No VPC endpoints to delete")
            return True
            
        try:
            for endpoint_id in endpoint_ids:
                print(f"🔄 Deleting VPC endpoint: {endpoint_id}")
                self.ec2.delete_vpc_endpoint(VpcEndpointId=endpoint_id)
            
            print(f"✅ Successfully deleted {len(endpoint_ids)} VPC endpoints")
            return True
            
        except ClientError as e:
            print(f"❌ Error deleting VPC endpoints: {e}")
            return False
    
    def delete_route_tables(self, route_table_ids):
        """Delete route tables"""
        if not route_table_ids:
            print("ℹ️  No custom route tables to delete")
            return True
            
        try:
            for rt_id in route_table_ids:
                # First, disassociate all subnets
                rt_response = self.ec2.describe_route_tables(RouteTableIds=[rt_id])
                route_table = rt_response['RouteTables'][0]
                
                for association in route_table.get('Associations', []):
                    if not association.get('Main', False) and 'RouteTableAssociationId' in association:
                        print(f"🔄 Disassociating route table {rt_id} from subnet")
                        self.ec2.disassociate_route_table(
                            AssociationId=association['RouteTableAssociationId']
                        )
                
                # Delete the route table
                print(f"🔄 Deleting route table: {rt_id}")
                self.ec2.delete_route_table(RouteTableId=rt_id)
            
            print(f"✅ Successfully deleted {len(route_table_ids)} route tables")
            return True
            
        except ClientError as e:
            print(f"❌ Error deleting route tables: {e}")
            return False
    
    def delete_security_groups(self, security_group_ids):
        """Delete security groups"""
        if not security_group_ids:
            print("ℹ️  No custom security groups to delete")
            return True
            
        try:
            # First, remove all rules to avoid dependency issues
            for sg_id in security_group_ids:
                try:
                    sg_response = self.ec2.describe_security_groups(GroupIds=[sg_id])
                    sg = sg_response['SecurityGroups'][0]
                    
                    # Remove ingress rules
                    if sg['IpPermissions']:
                        self.ec2.revoke_security_group_ingress(
                            GroupId=sg_id,
                            IpPermissions=sg['IpPermissions']
                        )
                    
                    # Remove egress rules
                    if sg['IpPermissionsEgress']:
                        self.ec2.revoke_security_group_egress(
                            GroupId=sg_id,
                            IpPermissions=sg['IpPermissionsEgress']
                        )
                        
                except ClientError as e:
                    print(f"⚠️  Could not remove rules from security group {sg_id}: {e}")
            
            # Now delete the security groups
            for sg_id in security_group_ids:
                print(f"🔄 Deleting security group: {sg_id}")
                self.ec2.delete_security_group(GroupId=sg_id)
            
            print(f"✅ Successfully deleted {len(security_group_ids)} security groups")
            return True
            
        except ClientError as e:
            print(f"❌ Error deleting security groups: {e}")
            return False
    
    def delete_subnets(self, subnet_ids):
        """Delete subnets"""
        if not subnet_ids:
            print("ℹ️  No subnets to delete")
            return True
            
        try:
            for subnet_id in subnet_ids:
                print(f"🔄 Deleting subnet: {subnet_id}")
                self.ec2.delete_subnet(SubnetId=subnet_id)
            
            print(f"✅ Successfully deleted {len(subnet_ids)} subnets")
            return True
            
        except ClientError as e:
            print(f"❌ Error deleting subnets: {e}")
            return False
    
    def detach_and_delete_internet_gateways(self, igw_ids):
        """Detach and delete Internet Gateways"""
        if not igw_ids:
            print("ℹ️  No internet gateways to delete")
            return True
            
        try:
            for igw_id in igw_ids:
                # Detach from VPC
                print(f"🔄 Detaching Internet Gateway {igw_id} from VPC {self.vpc_id}")
                self.ec2.detach_internet_gateway(
                    InternetGatewayId=igw_id,
                    VpcId=self.vpc_id
                )
                
                # Delete Internet Gateway
                print(f"🔄 Deleting Internet Gateway: {igw_id}")
                self.ec2.delete_internet_gateway(InternetGatewayId=igw_id)
            
            print(f"✅ Successfully deleted {len(igw_ids)} internet gateways")
            return True
            
        except ClientError as e:
            print(f"❌ Error deleting internet gateways: {e}")
            return False
    
    def delete_vpc(self):
        """Delete the VPC"""
        if not self.vpc_id:
            print("❌ No VPC ID to delete")
            return False
            
        try:
            print(f"🔄 Deleting VPC: {self.vpc_id}")
            self.ec2.delete_vpc(VpcId=self.vpc_id)
            print(f"✅ Successfully deleted VPC: {self.vpc_id}")
            return True
            
        except ClientError as e:
            print(f"❌ Error deleting VPC: {e}")
            return False
    
    def destroy_infrastructure(self, confirm=True):
        """Destroy all VPC infrastructure"""
        if confirm:
            print("⚠️  WARNING: This will delete ALL resources in the VPC!")
            print(f"VPC ID: {self.vpc_id}")
            confirmation = input("Type 'DELETE' to confirm destruction: ")
            if confirmation != 'DELETE':
                print("❌ Destruction cancelled")
                return False
        
        print("🚀 Starting VPC infrastructure destruction...")
        
        # Get all VPC resources
        resources = self.get_vpc_resources()
        if not resources:
            return False
        
        # Delete in the correct order to handle dependencies
        steps = [
            ("EC2 Instances", lambda: self.terminate_instances(resources['instances'])),
            ("Load Balancers", lambda: self.delete_load_balancers()),
            ("VPC Endpoints", lambda: self.delete_vpc_endpoints(resources['endpoints'])),
            ("NAT Gateways", lambda: self.delete_nat_gateways(resources['nat_gateways'])),
            ("Route Tables", lambda: self.delete_route_tables(resources['route_tables'])),
            ("Security Groups", lambda: self.delete_security_groups(resources['security_groups'])),
            ("Subnets", lambda: self.delete_subnets(resources['subnets'])),
            ("Internet Gateways", lambda: self.detach_and_delete_internet_gateways(resources['internet_gateways'])),
            ("VPC", lambda: self.delete_vpc())
        ]
        
        for step_name, step_function in steps:
            print(f"\n🔄 Step: {step_name}")
            if not step_function():
                print(f"❌ Failed at step: {step_name}")
                return False
            time.sleep(2)  # Brief pause between steps
        
        print("\n🎉 VPC Infrastructure destruction completed successfully!")
        
        # Clean up infrastructure file
        try:
            import os
            if os.path.exists(self.infrastructure_file):
                os.remove(self.infrastructure_file)
                print(f"🗑️  Removed infrastructure file: {self.infrastructure_file}")
        except Exception as e:
            print(f"⚠️  Could not remove infrastructure file: {e}")
        
        return True


def main():
    """Main function to destroy VPC infrastructure"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Destroy AWS VPC Infrastructure')
    parser.add_argument('--vpc-id', help='VPC ID to destroy')
    parser.add_argument('--region', default='ap-south-1', help='AWS region')
    parser.add_argument('--infrastructure-file', default='States/VPC-Deploy-Info.json', 
                       help='Infrastructure info JSON file')
    parser.add_argument('--force', action='store_true', 
                       help='Skip confirmation prompt')
    
    args = parser.parse_args()
    
    destroyer = VPCDestroyer(
        region=args.region, 
        vpc_id=args.vpc_id,
        infrastructure_file=args.infrastructure_file
    )
    
    try:
        # Load infrastructure info
        if not destroyer.load_infrastructure_info():
            if not args.vpc_id:
                print("❌ No VPC ID provided and no infrastructure file found")
                print("Use --vpc-id parameter or ensure infrastructure_info.json exists")
                return
        
        # Destroy infrastructure
        success = destroyer.destroy_infrastructure(confirm=not args.force)
        if success:
            print("\n✅ All infrastructure components destroyed successfully!")
        else:
            print("\n❌ Infrastructure destruction failed!")
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()