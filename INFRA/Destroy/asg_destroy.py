#!/usr/bin/env python3
"""
ASG Infrastructure Destroy Script
Safely removes Auto Scaling Groups, Load Balancers, and all related components
"""

import boto3
import json
import time
import os
from botocore.exceptions import ClientError


class ASGDestroyer:
    def __init__(self, region='ap-south-1', backend_file='States/Backend-Deploy-Info.json'):
        self.region = region
        self.ec2 = boto3.client('ec2', region_name=region)
        self.autoscaling = boto3.client('autoscaling', region_name=region)
        self.elbv2 = boto3.client('elbv2', region_name=region)
        self.iam = boto3.client('iam', region_name=region)
        self.backend_file = backend_file
        self.backend_info = None
        
    def load_backend_info(self):
        """Load backend deployment information"""
        try:
            with open(self.backend_file, 'r') as f:
                self.backend_info = json.load(f)
                print(f"✅ Loaded backend info from {self.backend_file}")
                return True
        except FileNotFoundError:
            print(f"⚠️  Backend file {self.backend_file} not found")
            print("   Will attempt to discover resources by name/tags")
            return False
        except json.JSONDecodeError:
            print(f"❌ Error reading backend file {self.backend_file}")
            return False
    
    def discover_backend_resources(self):
        """Discover backend resources by name/tags if deployment file not found"""
        resources = {
            'asg_names': [],
            'launch_templates': [],
            'load_balancers': [],
            'target_groups': [],
            'iam_roles': []
        }
        
        try:
            # Discover Auto Scaling Groups
            asg_response = self.autoscaling.describe_auto_scaling_groups()
            for asg in asg_response['AutoScalingGroups']:
                asg_name = asg['AutoScalingGroupName']
                if 'MERN' in asg_name or 'Backend' in asg_name:
                    resources['asg_names'].append(asg_name)
            
            # Discover Launch Templates
            lt_response = self.ec2.describe_launch_templates()
            for lt in lt_response['LaunchTemplates']:
                lt_name = lt['LaunchTemplateName']
                if 'MERN' in lt_name or 'Backend' in lt_name:
                    resources['launch_templates'].append({
                        'id': lt['LaunchTemplateId'],
                        'name': lt_name
                    })
            
            # Discover Load Balancers
            lb_response = self.elbv2.describe_load_balancers()
            for lb in lb_response['LoadBalancers']:
                lb_name = lb['LoadBalancerName']
                if 'MERN' in lb_name or 'Backend' in lb_name:
                    resources['load_balancers'].append({
                        'arn': lb['LoadBalancerArn'],
                        'name': lb_name
                    })
            
            # Discover Target Groups
            tg_response = self.elbv2.describe_target_groups()
            for tg in tg_response['TargetGroups']:
                tg_name = tg['TargetGroupName']
                if 'MERN' in tg_name:
                    resources['target_groups'].append({
                        'arn': tg['TargetGroupArn'],
                        'name': tg_name
                    })
            
            # Discover IAM Roles
            try:
                role = self.iam.get_role(RoleName='EC2-ECR-CloudWatch-Role')
                resources['iam_roles'].append('EC2-ECR-CloudWatch-Role')
            except ClientError:
                pass
            
            print(f"📋 Discovered backend resources:")
            for resource_type, resource_list in resources.items():
                if resource_list:
                    print(f"   {resource_type}: {len(resource_list)} items")
            
            return resources
            
        except ClientError as e:
            print(f"❌ Error discovering resources: {e}")
            return None
    
    def terminate_auto_scaling_groups(self, asg_names):
        """Terminate Auto Scaling Groups"""
        if not asg_names:
            print("ℹ️  No Auto Scaling Groups to terminate")
            return True
            
        try:
            for asg_name in asg_names:
                print(f"🔄 Scaling down ASG: {asg_name}")
                
                # Set desired capacity to 0
                self.autoscaling.update_auto_scaling_group(
                    AutoScalingGroupName=asg_name,
                    MinSize=0,
                    MaxSize=0,
                    DesiredCapacity=0
                )
                
                print(f"⏳ Waiting for instances to terminate in {asg_name}...")
                
                # Wait for instances to terminate
                max_attempts = 30
                attempt = 0
                
                while attempt < max_attempts:
                    try:
                        response = self.autoscaling.describe_auto_scaling_groups(
                            AutoScalingGroupNames=[asg_name]
                        )
                        
                        if not response['AutoScalingGroups']:
                            break
                            
                        asg = response['AutoScalingGroups'][0]
                        instance_count = len(asg['Instances'])
                        
                        if instance_count == 0:
                            print(f"✅ All instances terminated in {asg_name}")
                            break
                        else:
                            print(f"⏳ Waiting... {instance_count} instances still running")
                            time.sleep(30)
                            
                    except Exception as e:
                        print(f"⚠️  Error checking ASG status: {e}")
                        
                    attempt += 1
                
                if attempt >= max_attempts:
                    print(f"⚠️  Timeout waiting for instances to terminate, proceeding with force delete")
                
                # Delete scaling policies first
                try:
                    policies_response = self.autoscaling.describe_policies(
                        AutoScalingGroupName=asg_name
                    )
                    
                    for policy in policies_response['ScalingPolicies']:
                        print(f"🔄 Deleting scaling policy: {policy['PolicyName']}")
                        self.autoscaling.delete_policy(
                            AutoScalingGroupName=asg_name,
                            PolicyName=policy['PolicyName']
                        )
                        
                except ClientError as e:
                    print(f"⚠️  Could not delete scaling policies: {e}")
                
                # Delete ASG
                print(f"🔄 Deleting Auto Scaling Group: {asg_name}")
                self.autoscaling.delete_auto_scaling_group(
                    AutoScalingGroupName=asg_name,
                    ForceDelete=True
                )
            
            print(f"✅ Successfully deleted {len(asg_names)} Auto Scaling Groups")
            return True
            
        except ClientError as e:
            print(f"❌ Error deleting Auto Scaling Groups: {e}")
            return False
    
    def delete_load_balancers(self, load_balancers):
        """Delete Application Load Balancers"""
        if not load_balancers:
            print("ℹ️  No load balancers to delete")
            return True
            
        try:
            for lb in load_balancers:
                lb_arn = lb.get('arn', lb) if isinstance(lb, dict) else lb
                lb_name = lb.get('name', 'Unknown') if isinstance(lb, dict) else lb_arn
                
                print(f"🔄 Deleting load balancer: {lb_name}")
                self.elbv2.delete_load_balancer(LoadBalancerArn=lb_arn)
            
            # Wait for load balancers to be deleted
            print("⏳ Waiting for load balancers to be deleted...")
            time.sleep(60)  # ALB deletion takes time
            
            print(f"✅ Successfully deleted {len(load_balancers)} load balancers")
            return True
            
        except ClientError as e:
            print(f"❌ Error deleting load balancers: {e}")
            return False
    
    def delete_target_groups(self, target_groups):
        """Delete Target Groups"""
        if not target_groups:
            print("ℹ️  No target groups to delete")
            return True
            
        try:
            for tg in target_groups:
                tg_arn = tg.get('arn', tg) if isinstance(tg, dict) else tg
                tg_name = tg.get('name', 'Unknown') if isinstance(tg, dict) else tg_arn
                
                print(f"🔄 Deleting target group: {tg_name}")
                self.elbv2.delete_target_group(TargetGroupArn=tg_arn)
            
            print(f"✅ Successfully deleted {len(target_groups)} target groups")
            return True
            
        except ClientError as e:
            print(f"❌ Error deleting target groups: {e}")
            return False
    
    def delete_launch_templates(self, launch_templates):
        """Delete Launch Templates"""
        if not launch_templates:
            print("ℹ️  No launch templates to delete")
            return True
            
        try:
            for lt in launch_templates:
                lt_id = lt.get('id', lt) if isinstance(lt, dict) else lt
                lt_name = lt.get('name', 'Unknown') if isinstance(lt, dict) else lt_id
                
                print(f"🔄 Deleting launch template: {lt_name}")
                self.ec2.delete_launch_template(LaunchTemplateId=lt_id)
            
            print(f"✅ Successfully deleted {len(launch_templates)} launch templates")
            return True
            
        except ClientError as e:
            print(f"❌ Error deleting launch templates: {e}")
            return False
    
    def delete_iam_roles(self, role_names):
        """Delete IAM roles and instance profiles"""
        if not role_names:
            print("ℹ️  No IAM roles to delete")
            return True
            
        try:
            for role_name in role_names:
                print(f"🔄 Deleting IAM role: {role_name}")
                
                # First, get all instance profiles that use this role
                instance_profiles = []
                try:
                    profiles_response = self.iam.list_instance_profiles_for_role(RoleName=role_name)
                    instance_profiles = [profile['InstanceProfileName'] for profile in profiles_response['InstanceProfiles']]
                except ClientError:
                    pass
                
                # Detach all policies from the role
                try:
                    policies_response = self.iam.list_attached_role_policies(RoleName=role_name)
                    for policy in policies_response['AttachedPolicies']:
                        self.iam.detach_role_policy(
                            RoleName=role_name,
                            PolicyArn=policy['PolicyArn']
                        )
                        print(f"   Detached policy: {policy['PolicyName']}")
                except ClientError as e:
                    print(f"⚠️  Could not detach policies: {e}")
                
                # Remove role from all instance profiles
                for profile_name in instance_profiles:
                    try:
                        self.iam.remove_role_from_instance_profile(
                            InstanceProfileName=profile_name,
                            RoleName=role_name
                        )
                        print(f"   Removed from instance profile: {profile_name}")
                    except ClientError as e:
                        print(f"⚠️  Could not remove from instance profile {profile_name}: {e}")
                
                # Delete all instance profiles that were using this role
                for profile_name in instance_profiles:
                    try:
                        # Check if instance profile has any other roles
                        profile_response = self.iam.get_instance_profile(InstanceProfileName=profile_name)
                        if not profile_response['InstanceProfile']['Roles']:
                            self.iam.delete_instance_profile(InstanceProfileName=profile_name)
                            print(f"   Deleted instance profile: {profile_name}")
                    except ClientError as e:
                        print(f"⚠️  Could not delete instance profile {profile_name}: {e}")
                
                # Wait a bit for AWS to propagate the changes
                time.sleep(10)
                
                # Now try to delete the role
                try:
                    self.iam.delete_role(RoleName=role_name)
                    print(f"   Deleted role: {role_name}")
                except ClientError as e:
                    if 'DeleteConflict' in str(e):
                        print(f"⚠️  Role {role_name} still has dependencies, trying force cleanup...")
                        
                        # Try to find and remove any remaining dependencies
                        try:
                            # List inline policies
                            inline_policies = self.iam.list_role_policies(RoleName=role_name)
                            for policy_name in inline_policies['PolicyNames']:
                                self.iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
                                print(f"   Deleted inline policy: {policy_name}")
                        except ClientError:
                            pass
                        
                        # Wait and try again
                        time.sleep(15)
                        try:
                            self.iam.delete_role(RoleName=role_name)
                            print(f"   Deleted role: {role_name}")
                        except ClientError as final_error:
                            print(f"⚠️  Could not delete role {role_name}: {final_error}")
                            print(f"   You may need to manually delete this role from AWS Console")
                            # Don't fail the entire process for this
                            continue
                    else:
                        raise e
            
            print(f"✅ Successfully processed {len(role_names)} IAM roles")
            return True
            
        except ClientError as e:
            print(f"❌ Error deleting IAM roles: {e}")
            print("⚠️  Some IAM resources may need manual cleanup")
            return True  # Don't fail the entire process for IAM cleanup issues
    
    def destroy_backend_infrastructure(self, confirm=True):
        """Destroy all backend infrastructure"""
        if confirm:
            print("⚠️  WARNING: This will delete ALL backend infrastructure!")
            confirmation = input("Type 'DELETE' to confirm destruction: ")
            if confirmation != 'DELETE':
                print("❌ Destruction cancelled")
                return False
        
        print("🚀 Starting backend infrastructure destruction...")
        
        # Try to load deployment info, fall back to discovery
        resources = None
        if self.backend_info:
            # Use deployment file info
            resources = {
                'asg_names': [self.backend_info.get('asg_name', 'MERN-Backend-ASG')],
                'launch_templates': [{'id': self.backend_info.get('template_id')}] if self.backend_info.get('template_id') else [],
                'load_balancers': [{'arn': self.backend_info.get('alb_arn')}] if self.backend_info.get('alb_arn') else [],
                'target_groups': [{'arn': arn} for arn in self.backend_info.get('target_groups', {}).values()],
                'iam_roles': ['EC2-ECR-CloudWatch-Role']
            }
        else:
            # Discover resources
            resources = self.discover_backend_resources()
            
        if not resources:
            print("❌ Could not discover backend resources")
            return False
        
        # Delete in correct order to handle dependencies
        steps = [
            ("Auto Scaling Groups", lambda: self.terminate_auto_scaling_groups(resources['asg_names'])),
            ("Load Balancers", lambda: self.delete_load_balancers(resources['load_balancers'])),
            ("Target Groups", lambda: self.delete_target_groups(resources['target_groups'])),
            ("Launch Templates", lambda: self.delete_launch_templates(resources['launch_templates'])),
            ("IAM Roles", lambda: self.delete_iam_roles(resources['iam_roles']))
        ]
        
        for step_name, step_function in steps:
            print(f"\n🔄 Step: {step_name}")
            if not step_function():
                print(f"❌ Failed at step: {step_name}")
                return False
            time.sleep(5)  # Brief pause between steps
        
        print("\n🎉 Backend infrastructure destruction completed successfully!")
        
        # Clean up backend deployment file
        try:
            if os.path.exists(self.backend_file):
                os.remove(self.backend_file)
                print(f"🗑️  Removed backend deployment file: {self.backend_file}")
        except Exception as e:
            print(f"⚠️  Could not remove deployment file: {e}")
        
        return True


def main():
    """Main function to destroy backend infrastructure"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Destroy ASG Backend Infrastructure')
    parser.add_argument('--region', default='ap-south-1', help='AWS region')
    parser.add_argument('--backend-file', default='States/Backend-Deploy-Info.json',
                       help='Backend deployment info JSON file')
    parser.add_argument('--force', action='store_true',
                       help='Skip confirmation prompt')
    
    args = parser.parse_args()
    
    destroyer = ASGDestroyer(
        region=args.region,
        backend_file=args.backend_file
    )
    
    try:
        # Load backend deployment info
        destroyer.load_backend_info()
        
        # Destroy infrastructure
        success = destroyer.destroy_backend_infrastructure(confirm=not args.force)
        if success:
            print("\n✅ All backend infrastructure components destroyed successfully!")
            print("\n📝 Note: VPC infrastructure remains intact")
            print("   Use vpc_destroy.py to remove VPC if needed")
        else:
            print("\n❌ Backend infrastructure destruction failed!")
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()