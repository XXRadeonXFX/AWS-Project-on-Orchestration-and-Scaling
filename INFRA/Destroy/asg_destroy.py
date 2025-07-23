#!/usr/bin/env python3
"""
Precise ASG Infrastructure Destroy Script
Only destroys resources created by asg_deployment.py using the deployment JSON file
"""

import boto3
import json
import time
import os
from botocore.exceptions import ClientError


class PreciseASGDestroyer:
    def __init__(self, region='ap-south-1', backend_file='States/Backend-Deploy-Info.json'):
        self.region = region
        self.ec2 = boto3.client('ec2', region_name=region)
        self.autoscaling = boto3.client('autoscaling', region_name=region)
        self.elbv2 = boto3.client('elbv2', region_name=region)
        self.iam = boto3.client('iam', region_name=region)
        self.backend_file = backend_file
        self.backend_info = None
        
    def load_backend_info(self):
        """Load backend deployment information from JSON file"""
        try:
            with open(self.backend_file, 'r') as f:
                self.backend_info = json.load(f)
                print(f"✅ Loaded backend deployment info from {self.backend_file}")
                print(f"📋 Resources to destroy:")
                print(f"   - Launch Template: {self.backend_info.get('template_id', 'Not found')}")
                print(f"   - ALB ARN: {self.backend_info.get('alb_arn', 'Not found')}")
                print(f"   - ALB DNS: {self.backend_info.get('alb_dns', 'Not found')}")
                print(f"   - ASG Name: {self.backend_info.get('asg_name', 'Not found')}")
                print(f"   - Target Groups: {len(self.backend_info.get('target_groups', {}))}")
                return True
        except FileNotFoundError:
            print(f"❌ Backend deployment file not found: {self.backend_file}")
            print("   Cannot proceed without deployment information!")
            return False
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON in file: {self.backend_file}")
            return False
    
    def wait_with_progress(self, seconds, message):
        """Wait with progress indicator"""
        print(f"⏳ {message}")
        for i in range(seconds):
            print(".", end="", flush=True)
            time.sleep(1)
        print(" Done!")
    
    def delete_auto_scaling_group(self):
        """Delete the specific Auto Scaling Group"""
        asg_name = self.backend_info.get('asg_name')
        if not asg_name:
            print("⚠️  No ASG name found in deployment info")
            return True
        
        try:
            print(f"\n🔄 Processing Auto Scaling Group: {asg_name}")
            
            # Check if ASG exists
            try:
                asg_response = self.autoscaling.describe_auto_scaling_groups(
                    AutoScalingGroupNames=[asg_name]
                )
                if not asg_response['AutoScalingGroups']:
                    print(f"ℹ️  ASG {asg_name} does not exist")
                    return True
            except ClientError as e:
                if 'does not exist' in str(e):
                    print(f"ℹ️  ASG {asg_name} does not exist")
                    return True
                raise
            
            # Delete scaling policies first
            try:
                policies_response = self.autoscaling.describe_policies(
                    AutoScalingGroupName=asg_name
                )
                for policy in policies_response['ScalingPolicies']:
                    print(f"   Deleting scaling policy: {policy['PolicyName']}")
                    self.autoscaling.delete_policy(
                        AutoScalingGroupName=asg_name,
                        PolicyName=policy['PolicyName']
                    )
            except ClientError as e:
                print(f"   ⚠️  Could not delete scaling policies: {e}")
            
            # Cancel any ongoing instance refresh
            try:
                self.autoscaling.cancel_instance_refresh(AutoScalingGroupName=asg_name)
                print("   Cancelled any ongoing instance refresh")
            except ClientError:
                pass  # No refresh to cancel
            
            # Set capacity to 0 to terminate instances
            print(f"   Setting ASG capacity to 0...")
            self.autoscaling.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MinSize=0,
                MaxSize=0,
                DesiredCapacity=0
            )
            
            # Wait for instances to terminate
            print(f"   Waiting for instances to terminate...")
            max_attempts = 24  # 12 minutes max
            attempt = 0
            
            while attempt < max_attempts:
                try:
                    asg_info = self.autoscaling.describe_auto_scaling_groups(
                        AutoScalingGroupNames=[asg_name]
                    )
                    
                    if not asg_info['AutoScalingGroups']:
                        break
                        
                    current_asg = asg_info['AutoScalingGroups'][0]
                    instance_count = len(current_asg['Instances'])
                    
                    if instance_count == 0:
                        print("   ✅ All instances terminated")
                        break
                    else:
                        print(f"   ⏳ {instance_count} instances still terminating...")
                        time.sleep(30)  # Wait 30 seconds between checks
                        
                except ClientError:
                    break
                
                attempt += 1
            
            if attempt >= max_attempts:
                print(f"   ⚠️  Timeout waiting for instances to terminate, proceeding with force delete")
            
            # Delete the ASG
            print(f"   Deleting ASG: {asg_name}")
            self.autoscaling.delete_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                ForceDelete=True
            )
            
            print(f"   ✅ ASG {asg_name} deleted successfully")
            return True
            
        except ClientError as e:
            print(f"   ❌ Error deleting ASG {asg_name}: {e}")
            return False
    
    def delete_load_balancer(self):
        """Delete the specific Application Load Balancer"""
        alb_arn = self.backend_info.get('alb_arn')
        alb_dns = self.backend_info.get('alb_dns', 'Unknown')
        
        if not alb_arn:
            print("⚠️  No ALB ARN found in deployment info")
            return True
        
        try:
            print(f"\n🔄 Processing Load Balancer: {alb_dns}")
            
            # Check if ALB exists
            try:
                alb_response = self.elbv2.describe_load_balancers(
                    LoadBalancerArns=[alb_arn]
                )
                if not alb_response['LoadBalancers']:
                    print(f"ℹ️  ALB does not exist")
                    return True
            except ClientError as e:
                if 'does not exist' in str(e) or 'not found' in str(e):
                    print(f"ℹ️  ALB does not exist")
                    return True
                raise
            
            # Delete listeners first
            try:
                listeners_response = self.elbv2.describe_listeners(
                    LoadBalancerArn=alb_arn
                )
                for listener in listeners_response['Listeners']:
                    print(f"   Deleting listener on port {listener['Port']}")
                    self.elbv2.delete_listener(ListenerArn=listener['ListenerArn'])
            except ClientError as e:
                print(f"   ⚠️  Could not delete listeners: {e}")
            
            # Delete the load balancer
            print(f"   Deleting ALB...")
            self.elbv2.delete_load_balancer(LoadBalancerArn=alb_arn)
            print(f"   ✅ ALB deletion initiated")
            
            return True
            
        except ClientError as e:
            print(f"   ❌ Error deleting ALB: {e}")
            return False
    
    def delete_target_groups(self):
        """Delete the specific Target Groups"""
        target_groups = self.backend_info.get('target_groups', {})
        
        if not target_groups:
            print("ℹ️  No target groups found in deployment info")
            return True
        
        print(f"\n🔄 Processing Target Groups ({len(target_groups)} groups)")
        
        success = True
        for tg_name, tg_arn in target_groups.items():
            try:
                print(f"   Processing target group: {tg_name}")
                
                # Check if target group exists
                try:
                    tg_response = self.elbv2.describe_target_groups(
                        TargetGroupArns=[tg_arn]
                    )
                    if not tg_response['TargetGroups']:
                        print(f"     ℹ️  Target group {tg_name} does not exist")
                        continue
                except ClientError as e:
                    if 'does not exist' in str(e) or 'not found' in str(e):
                        print(f"     ℹ️  Target group {tg_name} does not exist")
                        continue
                    raise
                
                # Deregister all targets first
                try:
                    targets_response = self.elbv2.describe_target_health(
                        TargetGroupArn=tg_arn
                    )
                    if targets_response['TargetHealthDescriptions']:
                        target_list = [
                            {'Id': target['Target']['Id']} 
                            for target in targets_response['TargetHealthDescriptions']
                        ]
                        self.elbv2.deregister_targets(
                            TargetGroupArn=tg_arn,
                            Targets=target_list
                        )
                        print(f"     Deregistered {len(target_list)} targets")
                        time.sleep(10)  # Wait for deregistration
                except ClientError as e:
                    print(f"     ⚠️  Could not deregister targets: {e}")
                
                # Delete the target group
                self.elbv2.delete_target_group(TargetGroupArn=tg_arn)
                print(f"     ✅ Target group {tg_name} deleted")
                
            except ClientError as e:
                print(f"     ❌ Error deleting target group {tg_name}: {e}")
                success = False
        
        return success
    
    def delete_launch_template(self):
        """Delete the specific Launch Template"""
        template_id = self.backend_info.get('template_id')
        
        if not template_id:
            print("⚠️  No launch template ID found in deployment info")
            return True
        
        try:
            print(f"\n🔄 Processing Launch Template: {template_id}")
            
            # Check if launch template exists
            try:
                lt_response = self.ec2.describe_launch_templates(
                    LaunchTemplateIds=[template_id]
                )
                if not lt_response['LaunchTemplates']:
                    print(f"ℹ️  Launch template {template_id} does not exist")
                    return True
                    
                template_name = lt_response['LaunchTemplates'][0]['LaunchTemplateName']
                print(f"   Found template: {template_name}")
                
            except ClientError as e:
                if 'does not exist' in str(e) or 'not found' in str(e):
                    print(f"ℹ️  Launch template {template_id} does not exist")
                    return True
                raise
            
            # Delete the launch template
            self.ec2.delete_launch_template(LaunchTemplateId=template_id)
            print(f"   ✅ Launch template {template_id} deleted")
            
            return True
            
        except ClientError as e:
            print(f"   ❌ Error deleting launch template {template_id}: {e}")
            return False
    
    def cleanup_iam_role(self):
        """Clean up the IAM role (only if not used by other resources)"""
        role_name = 'EC2-ECR-CloudWatch-Role'
        
        try:
            print(f"\n🔄 Checking IAM role: {role_name}")
            
            # Check if role exists
            try:
                self.iam.get_role(RoleName=role_name)
            except ClientError as e:
                if e.response['Error']['Code'] == 'NoSuchEntity':
                    print(f"   ℹ️  IAM role {role_name} does not exist")
                    return True
                raise
            
            # Check if role is being used by other resources
            # For safety, we'll leave the role if there are other EC2 instances using it
            try:
                # Check if there are any instances with this instance profile
                instances_response = self.ec2.describe_instances(
                    Filters=[
                        {'Name': 'iam-instance-profile.arn', 'Values': [f'*{role_name}*']},
                        {'Name': 'instance-state-name', 'Values': ['running', 'stopped', 'stopping']}
                    ]
                )
                
                instance_count = sum(
                    len(reservation['Instances']) 
                    for reservation in instances_response['Reservations']
                )
                
                if instance_count > 0:
                    print(f"   ⚠️  IAM role {role_name} is still used by {instance_count} instances")
                    print(f"   Leaving role intact for safety")
                    return True
                
            except ClientError as e:
                print(f"   ⚠️  Could not check role usage: {e}")
                print(f"   Leaving role intact for safety")
                return True
            
            print(f"   ℹ️  IAM role {role_name} is not used by any instances")
            print(f"   Leaving role intact (can be manually deleted if not needed)")
            return True
            
        except ClientError as e:
            print(f"   ❌ Error checking IAM role: {e}")
            return True  # Don't fail the process for IAM issues
    
    def destroy_backend_infrastructure(self):
        """Destroy only the specific backend infrastructure from deployment file"""
        print("🎯 PRECISE BACKEND DESTRUCTION")
        print("This will ONLY destroy resources listed in the deployment JSON file:")
        print(f"   File: {self.backend_file}")
        
        if not self.load_backend_info():
            return False
        
        print("\n⚠️  WARNING: This will delete the specific backend infrastructure!")
        confirmation = input("\nType 'DELETE' to confirm destruction: ")
        if confirmation != 'DELETE':
            print("❌ Destruction cancelled")
            return False
        
        print("\n🚀 Starting precise backend infrastructure destruction...")
        
        # Destruction sequence (order matters due to dependencies)
        steps = [
            ("Auto Scaling Group", self.delete_auto_scaling_group),
            ("Load Balancer", self.delete_load_balancer),
            ("Target Groups", self.delete_target_groups),
            ("Launch Template", self.delete_launch_template),
            ("IAM Role Check", self.cleanup_iam_role)
        ]
        
        overall_success = True
        
        for step_name, step_function in steps:
            print(f"\n{'='*50}")
            print(f"STEP: {step_name}")
            print('='*50)
            
            try:
                if not step_function():
                    print(f"⚠️  Step '{step_name}' completed with warnings")
                    overall_success = False
            except Exception as e:
                print(f"❌ Step '{step_name}' failed: {e}")
                overall_success = False
            
            # Brief pause between steps
            time.sleep(3)
        
        # Wait for ALB to be fully deleted before declaring success
        if self.backend_info.get('alb_arn'):
            self.wait_with_progress(60, "Waiting for Load Balancer to be fully deleted")
        
        print(f"\n{'='*50}")
        if overall_success:
            print("🎉 Backend infrastructure destruction completed successfully!")
        else:
            print("⚠️  Backend infrastructure destruction completed with some warnings")
            print("   Check the output above for any issues")
        
        # Clean up the deployment file
        try:
            if os.path.exists(self.backend_file):
                os.remove(self.backend_file)
                print(f"🗑️  Removed deployment file: {self.backend_file}")
        except Exception as e:
            print(f"⚠️  Could not remove deployment file: {e}")
        
        print("\n📝 Summary:")
        print("   ✅ Only resources from deployment file were targeted")
        print("   ✅ VPC and other infrastructure remains intact")
        print("   ✅ IAM role preserved (check manually if cleanup needed)")
        
        return overall_success


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Destroy Specific Backend Infrastructure')
    parser.add_argument('--region', default='ap-south-1', help='AWS region (default: ap-south-1)')
    parser.add_argument('--backend-file', default='../Apply/States/Ubuntu-Backend-Deploy-Info.json',
                       help='Backend deployment info JSON file')
    parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    
    args = parser.parse_args()
    
    destroyer = PreciseASGDestroyer(
        region=args.region,
        backend_file=args.backend_file
    )
    
    try:
        if args.force:
            print("🚀 Force mode: Skipping confirmation")
            # Mock the confirmation
            import unittest.mock
            with unittest.mock.patch('builtins.input', return_value='DELETE'):
                success = destroyer.destroy_backend_infrastructure()
        else:
            success = destroyer.destroy_backend_infrastructure()
        
        if success:
            print("\n✅ Precise destruction completed successfully!")
        else:
            print("\n⚠️  Precise destruction completed with warnings!")
            
    except KeyboardInterrupt:
        print("\n❌ Destruction cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()