import boto3
import json
from botocore.exceptions import ClientError

# ----------------------------------------
# 🔧 CONFIGURE THESE VARIABLES
# ----------------------------------------
region = "ap-south-1"
sns_topic_arn = "arn:aws:sns:ap-south-1:975050024946:prince-topic"
asg_name = "prince-backend-asg"
alb_name = "prince-backend-alb"

# Initialize AWS clients
cloudwatch = boto3.client('cloudwatch', region_name=region)
logs_client = boto3.client('logs', region_name=region)
ec2_client = boto3.client('ec2', region_name=region)

def create_log_groups():
    """Create CloudWatch Log Groups"""
    log_groups = [
        '/aws/ec2/backend',
        '/aws/ec2/frontend',
        '/aws/lambda/mongo-backup',
        '/aws/application/mern-app'
    ]
    
    for log_group in log_groups:
        try:
            print(f"📊 Creating log group: {log_group}")
            logs_client.create_log_group(
                logGroupName=log_group,
                tags={
                    'Project': 'MERN-Deployment',
                    'Environment': 'Production'
                }
            )
            
            # Set retention policy (30 days)
            logs_client.put_retention_policy(
                logGroupName=log_group,
                retentionInDays=30
            )
            
            print(f"✅ Log group created: {log_group}")
            
        except ClientError as e:
            if "ResourceAlreadyExistsException" in str(e):
                print(f"ℹ️ Log group already exists: {log_group}")
            else:
                print(f"❌ Error creating log group {log_group}: {e}")

def create_cpu_alarm():
    """Create CPU utilization alarm for ASG"""
    try:
        print("🚨 Creating CPU utilization alarm...")
        
        cloudwatch.put_metric_alarm(
            AlarmName='MERN-Backend-High-CPU',
            ComparisonOperator='GreaterThanThreshold',
            EvaluationPeriods=2,
            MetricName='CPUUtilization',
            Namespace='AWS/EC2',
            Period=300,  # 5 minutes
            Statistic='Average',
            Threshold=80.0,
            ActionsEnabled=True,
            AlarmActions=[sns_topic_arn],
            AlarmDescription='Alarm when backend CPU exceeds 80%',
            Dimensions=[
                {
                    'Name': 'AutoScalingGroupName',
                    'Value': asg_name
                }
            ],
            Unit='Percent',
            TreatMissingData='notBreaching'
        )
        
        print("✅ CPU utilization alarm created")
        
    except ClientError as e:
        print(f"❌ Error creating CPU alarm: {e}")

def create_memory_alarm():
    """Create Memory utilization alarm"""
    try:
        print("🧠 Creating Memory utilization alarm...")
        
        cloudwatch.put_metric_alarm(
            AlarmName='MERN-Backend-High-Memory',
            ComparisonOperator='GreaterThanThreshold',
            EvaluationPeriods=2,
            MetricName='MemoryUtilization',
            Namespace='CWAgent',
            Period=300,
            Statistic='Average',
            Threshold=85.0,
            ActionsEnabled=True,
            AlarmActions=[sns_topic_arn],
            AlarmDescription='Alarm when backend memory exceeds 85%',
            Dimensions=[
                {
                    'Name': 'AutoScalingGroupName',
                    'Value': asg_name
                }
            ],
            Unit='Percent'
        )
        
        print("✅ Memory utilization alarm created")
        
    except ClientError as e:
        print(f"❌ Error creating memory alarm: {e}")

def create_disk_alarm():
    """Create Disk utilization alarm"""
    try:
        print("💽 Creating Disk utilization alarm...")
        
        cloudwatch.put_metric_alarm(
            AlarmName='MERN-Backend-High-Disk',
            ComparisonOperator='GreaterThanThreshold',
            EvaluationPeriods=1,
            MetricName='DiskSpaceUtilization',
            Namespace='CWAgent',
            Period=300,
            Statistic='Average',
            Threshold=90.0,
            ActionsEnabled=True,
            AlarmActions=[sns_topic_arn],
            AlarmDescription='Alarm when backend disk usage exceeds 90%',
            Dimensions=[
                {
                    'Name': 'AutoScalingGroupName',
                    'Value': asg_name
                },
                {
                    'Name': 'MountPath',
                    'Value': '/'
                }
            ],
            Unit='Percent'
        )
        
        print("✅ Disk utilization alarm created")
        
    except ClientError as e:
        print(f"❌ Error creating disk alarm: {e}")

def create_application_error_alarm():
    """Create application error alarm based on log patterns"""
    try:
        print("⚠️ Creating application error alarm...")
        
        # First create a metric filter for error logs
        logs_client.put_metric_filter(
            logGroupName='/aws/ec2/backend',
            filterName='ApplicationErrors',
            filterPattern='[timestamp, request_id, "ERROR"]',
            metricTransformations=[
                {
                    'metricName': 'ApplicationErrors',
                    'metricNamespace': 'MERN/Application',
                    'metricValue': '1',
                    'defaultValue': 0
                }
            ]
        )
        
        # Create alarm based on the metric filter
        cloudwatch.put_metric_alarm(
            AlarmName='MERN-Application-Errors',
            ComparisonOperator='GreaterThanThreshold',
            EvaluationPeriods=1,
            MetricName='ApplicationErrors',
            Namespace='MERN/Application',
            Period=300,
            Statistic='Sum',
            Threshold=5.0,
            ActionsEnabled=True,
            AlarmActions=[sns_topic_arn],
            AlarmDescription='Alarm when application errors exceed 5 in 5 minutes',
            TreatMissingData='notBreaching'
        )
        
        print("✅ Application error alarm created")
        
    except ClientError as e:
        print(f"❌ Error creating application error alarm: {e}")

def create_lambda_error_alarm():
    """Create Lambda function error alarm"""
    try:
        print("🔧 Creating Lambda error alarm...")
        
        cloudwatch.put_metric_alarm(
            AlarmName='MERN-Lambda-Backup-Errors',
            ComparisonOperator='GreaterThanThreshold',
            EvaluationPeriods=1,
            MetricName='Errors',
            Namespace='AWS/Lambda',
            Period=300,
            Statistic='Sum',
            Threshold=0.0,
            ActionsEnabled=True,
            AlarmActions=[sns_topic_arn],
            AlarmDescription='Alarm when Lambda backup function fails',
            Dimensions=[
                {
                    'Name': 'FunctionName',
                    'Value': 'prince-mongo-backup'
                }
            ]
        )
        
        print("✅ Lambda error alarm created")
        
    except ClientError as e:
        print(f"❌ Error creating Lambda error alarm: {e}")

def create_custom_dashboard():
    """Create CloudWatch Dashboard"""
    try:
        print("📊 Creating CloudWatch Dashboard...")
        
        dashboard_body = {
            "widgets": [
                {
                    "type": "metric",
                    "x": 0,
                    "y": 0,
                    "width": 12,
                    "height": 6,
                    "properties": {
                        "metrics": [
                            ["AWS/EC2", "CPUUtilization", "AutoScalingGroupName", asg_name],
                            ["CWAgent", "MemoryUtilization", "AutoScalingGroupName", asg_name]
                        ],
                        "period": 300,
                        "stat": "Average",
                        "region": region,
                        "title": "Backend Instance Metrics",
                        "yAxis": {
                            "left": {
                                "min": 0,
                                "max": 100
                            }
                        }
                    }
                },
                {
                    "type": "metric",
                    "x": 12,
                    "y": 0,
                    "width": 12,
                    "height": 6,
                    "properties": {
                        "metrics": [
                            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", alb_name],
                            [".", "TargetResponseTime", ".", "."]
                        ],
                        "period": 300,
                        "stat": "Sum",
                        "region": region,
                        "title": "Load Balancer Metrics"
                    }
                },
                {
                    "type": "metric",
                    "x": 0,
                    "y": 6,
                    "width": 24,
                    "height": 6,
                    "properties": {
                        "metrics": [
                            ["AWS/Lambda", "Duration", "FunctionName", "prince-mongo-backup"],
                            [".", "Errors", ".", "."],
                            [".", "Invocations", ".", "."]
                        ],
                        "period": 300,
                        "stat": "Average",
                        "region": region,
                        "title": "Lambda Backup Function Metrics"
                    }
                },
                {
                    "type": "log",
                    "x": 0,
                    "y": 12,
                    "width": 24,
                    "height": 6,
                    "properties": {
                        "query": f"SOURCE '/aws/ec2/backend' | fields @timestamp, @message\n| filter @message like /ERROR/\n| sort @timestamp desc\n| limit 20",
                        "region": region,
                        "title": "Recent Application Errors",
                        "view": "table"
                    }
                }
            ]
        }
        
        cloudwatch.put_dashboard(
            DashboardName='MERN-Application-Monitoring',
            DashboardBody=json.dumps(dashboard_body)
        )
        
        print("✅ CloudWatch Dashboard created: MERN-Application-Monitoring")
        
    except ClientError as e:
        print(f"❌ Error creating dashboard: {e}")

def main():
    """Main function to set up complete monitoring"""
    print("🚀 Setting up CloudWatch Monitoring...")
    
    # Create log groups
    create_log_groups()
    
    # Create alarms
    create_cpu_alarm()
    create_memory_alarm()
    create_disk_alarm()
    create_application_error_alarm()
    create_lambda_error_alarm()
    
    # Create dashboard
    create_custom_dashboard()
    
    print("\n🎉 CloudWatch Monitoring Setup Complete!")
    print("\n📊 Created Components:")
    print("   • Log Groups for application logs")
    print("   • CPU utilization alarm (>80%)")
    print("   • Memory utilization alarm (>85%)")
    print("   • Disk utilization alarm (>90%)")
    print("   • Application error alarm (>5 errors/5min)")
    print("   • Lambda backup error alarm")
    print("   • Comprehensive monitoring dashboard")
    
    print(f"\n🔗 Access Dashboard:")
    print(f"   https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#dashboards:name=MERN-Application-Monitoring")
    
    print(f"\n📧 Notifications will be sent to: {sns_topic_arn}")

if __name__ == "__main__":
    main()