import os
import json
import base64
import boto3

S3_BUCKET = os.environ.get('S3_BUCKET', '')
s3_client = boto3.client('s3')


def lambda_handler(event, context):
    params = event.get('queryStringParameters') or {}
    image_hash = params.get('hash')
    image_name = params.get('image', '')

    if not image_hash:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'hash parameter required'})
        }

    # S3에서 이미지 로드
    s3_key = f'images/{image_name}.png'
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
        img_bytes = obj['Body'].read()
    except Exception as e:
        return {
            'statusCode': 404,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Image not found: {e}'})
        }

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'image/png',
            'Cache-Control': 'max-age=86400, public'
        },
        'body': base64.b64encode(img_bytes).decode(),
        'isBase64Encoded': True
    }
