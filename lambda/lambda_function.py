import boto3

def lambda_handler(event, context):
    sns = boto3.client('sns', region_name='ap-south-1')

    # Static SNS topic ARN
    topic_arn = "arn:aws:sns:ap-south-1:975050024946:prince-topic"

    # Allow dynamic subject/message from event or default fallback
    subject = event.get('subject', 'Jenkins Deployment Status')
    message = event.get('message', '✅ Jenkins build completed successfully.')

    try:
        response = sns.publish(
            TopicArn=topic_arn,
            Message=message,
            Subject=subject
        )
        return {
            'statusCode': 200,
            'body': f"✅ Notification sent! MessageId: {response['MessageId']}"
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f"❌ Error sending notification: {str(e)}"
        }
#this is the lambda function
