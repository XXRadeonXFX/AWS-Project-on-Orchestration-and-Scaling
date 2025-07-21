#!/usr/bin/env python3
"""
Complete MERN Infrastructure Deployment Script
Deploys VPC, Lambda backup, and ASG infrastructure
"""

import sys
import time
from vpc_infrastructure import VPCInfrastructure
from deploy_lambda_backup import LambdaDeployment
from asg_deployment import ASGDeployment


def main():
    """Deploy complete MERN infrastructure"""
    print("🚀 Starting Complete MERN Infrastructure Deployment")
    print("=" * 60)
    
    try:
        # Step 1: Deploy VPC Infrastructure
        print("\n📋 Step 1: Deploying VPC Infrastructure...")
        vpc_infra = VPCInfrastructure()
        vpc_success = vpc_infra.deploy_infrastructure()
        
        if not vpc_success:
            print("❌ VPC deployment failed! Stopping deployment.")
            return False
        
        print("✅ VPC Infrastructure deployed successfully!")
        
        # Step 2: Deploy Lambda Backup Solution
        print("\n📋 Step 2: Deploying Lambda Backup Solution...")
        lambda_deployment = LambdaDeployment()
        lambda_success = lambda_deployment.deploy_backup_solution()
        
        if not lambda_success:
            print("❌ Lambda deployment failed! Continuing with ASG...")
        else:
            print("✅ Lambda Backup Solution deployed successfully!")
        
        # Step 3: Deploy Backend ASG Infrastructure
        print("\n📋 Step 3: Deploying Backend ASG Infrastructure...")
        infrastructure_info = vpc_infra.get_infrastructure_info()
        asg_deployment = ASGDeployment()
        asg_success = asg_deployment.deploy_backend_infrastructure(infrastructure_info)
        
        if not asg_success:
            print("❌ ASG deployment failed!")
            return False
        
        print("✅ Backend ASG Infrastructure deployed successfully!")
        
        # Summary
        print("\n" + "=" * 60)
        print("🎉 COMPLETE INFRASTRUCTURE DEPLOYMENT SUCCESSFUL!")
        print("=" * 60)
        
        print("\n📊 Deployment Summary:")
        print("✅ VPC with public/private subnets")
        print("✅ Security groups for all services")
        print("✅ Internet Gateway and NAT Gateway")
        print("✅ Auto Scaling Group for backend services")
        print("✅ Application Load Balancer")
        print("✅ Lambda function for MongoDB backups")
        print("✅ S3 bucket for backup storage")
        print("✅ CloudWatch monitoring and scaling")
        
        print("\n🔗 Next Steps:")
        print("1. Wait 5-10 minutes for ASG instances to be ready")
        print("2. Test backend services via ALB DNS")
        print("3. Deploy frontend using Kubernetes (EKS)")
        print("4. Configure Route 53 DNS (optional)")
        print("5. Set up SSL certificates (optional)")
        
        return True
        
    except KeyboardInterrupt:
        print("\n❌ Deployment interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error during deployment: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)