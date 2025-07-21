#!/usr/bin/env python3
"""
AWS Lambda Function for MongoDB Atlas Backup
Backs up MongoDB data and stores in S3 with timestamping
"""

import json
import boto3
import pymongo
import datetime
import os
import zipfile
import tempfile
from botocore.exceptions import ClientError


def lambda_handler(event, context):
    """
    AWS Lambda handler for MongoDB backup
    """
    
    # Environment variables
    MONGO_CONNECTION_STRING = os.environ.get('MONGO_CONNECTION_STRING')
    S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'mern-app-database-backups')
    DATABASE_NAME = os.environ.get('DATABASE_NAME', 'SimpleMern')
    
    # Initialize AWS clients
    s3_client = boto3.client('s3')
    
    try:
        # Generate timestamp
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_filename = f"mongodb_backup_{timestamp}.json"
        
        print(f"🔄 Starting MongoDB backup at {timestamp}")
        
        # Connect to MongoDB
        client = pymongo.MongoClient(MONGO_CONNECTION_STRING)
        db = client[DATABASE_NAME]
        
        # Create temporary directory for backup
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_data = {}
            
            # Get all collections
            collections = db.list_collection_names()
            print(f"📊 Found {len(collections)} collections to backup")
            
            # Backup each collection
            for collection_name in collections:
                print(f"📦 Backing up collection: {collection_name}")
                collection = db[collection_name]
                
                # Get all documents from collection
                documents = list(collection.find())
                
                # Convert ObjectId to string for JSON serialization
                for doc in documents:
                    if '_id' in doc:
                        doc['_id'] = str(doc['_id'])
                
                backup_data[collection_name] = {
                    'count': len(documents),
                    'documents': documents
                }
                
                print(f"✅ Backed up {len(documents)} documents from {collection_name}")
            
            # Add metadata
            backup_data['_metadata'] = {
                'timestamp': timestamp,
                'database_name': DATABASE_NAME,
                'total_collections': len(collections),
                'backup_type': 'full',
                'lambda_function': context.function_name if context else 'local'
            }
            
            # Save backup to temporary file
            backup_file_path = os.path.join(temp_dir, backup_filename)
            with open(backup_file_path, 'w') as f:
                json.dump(backup_data, f, indent=2, default=str)
            
            # Create compressed backup
            zip_filename = f"mongodb_backup_{timestamp}.zip"
            zip_file_path = os.path.join(temp_dir, zip_filename)
            
            with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(backup_file_path, backup_filename)
            
            # Upload to S3
            s3_key = f"backups/{datetime.datetime.now().year}/{datetime.datetime.now().month:02d}/{zip_filename}"
            
            print(f"📤 Uploading backup to S3: s3://{S3_BUCKET_NAME}/{s3_key}")
            
            s3_client.upload_file(
                zip_file_path,
                S3_BUCKET_NAME,
                s3_key,
                ExtraArgs={
                    'Metadata': {
                        'timestamp': timestamp,
                        'database': DATABASE_NAME,
                        'collections': str(len(collections)),
                        'backup-type': 'mongodb-full'
                    }
                }
            )
            
            # Calculate file size
            file_size = os.path.getsize(zip_file_path)
            file_size_mb = round(file_size / (1024 * 1024), 2)
            
            print(f"✅ Backup completed successfully!")
            print(f"📁 File size: {file_size_mb} MB")
            print(f"🔗 S3 location: s3://{S3_BUCKET_NAME}/{s3_key}")
            
            # Clean up old backups (keep last 30 days)
            cleanup_old_backups(s3_client, S3_BUCKET_NAME)
            
            # Close MongoDB connection
            client.close()
            
            # Return success response
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Backup completed successfully',
                    'timestamp': timestamp,
                    'backup_file': zip_filename,
                    's3_location': f"s3://{S3_BUCKET_NAME}/{s3_key}",
                    'file_size_mb': file_size_mb,
                    'collections_backed_up': len(collections),
                    'total_documents': sum(collection['count'] for collection in backup_data.values() if isinstance(collection, dict) and 'count' in collection)
                })
            }
            
    except pymongo.errors.ConnectionFailure as e:
        error_message = f"MongoDB connection failed: {str(e)}"
        print(f"❌ {error_message}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_message,
                'timestamp': datetime.datetime.now().isoformat()
            })
        }
        
    except ClientError as e:
        error_message = f"AWS S3 error: {str(e)}"
        print(f"❌ {error_message}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_message,
                'timestamp': datetime.datetime.now().isoformat()
            })
        }
        
    except Exception as e:
        error_message = f"Unexpected error: {str(e)}"
        print(f"❌ {error_message}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_message,
                'timestamp': datetime.datetime.now().isoformat()
            })
        }


def cleanup_old_backups(s3_client, bucket_name, retention_days=30):
    """
    Clean up backups older than retention_days
    """
    try:
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=retention_days)
        
        # List objects in backup folder
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix='backups/'
        )
        
        if 'Contents' in response:
            old_objects = []
            for obj in response['Contents']:
                if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                    old_objects.append({'Key': obj['Key']})
            
            if old_objects:
                print(f"🧹 Cleaning up {len(old_objects)} old backup files")
                s3_client.delete_objects(
                    Bucket=bucket_name,
                    Delete={'Objects': old_objects}
                )
                print(f"✅ Cleaned up {len(old_objects)} old backups")
            else:
                print("ℹ️  No old backups to clean up")
                
    except Exception as e:
        print(f"⚠️  Warning: Could not clean up old backups: {e}")


# For local testing
if __name__ == "__main__":
    # Set environment variables for testing
    os.environ['MONGO_CONNECTION_STRING'] = 'mongodb+srv://radeonxfx:1029384756!Sound@cluster0.gdl7f.mongodb.net/SimpleMern'
    os.environ['S3_BUCKET_NAME'] = 'mern-app-database-backups'
    os.environ['DATABASE_NAME'] = 'SimpleMern'
    
    # Test the function
    result = lambda_handler({}, None)
    print(json.dumps(result, indent=2))