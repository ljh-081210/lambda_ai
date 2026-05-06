import os
import json
import base64
import boto3
from PIL import Image
from io import BytesIO

S3_BUCKET = os.environ.get('S3_BUCKET', 'gj2026-cdn-bucket')
s3_client = boto3.client('s3')


def lambda_handler(event, context):
    params = event.get('queryStringParameters') or {}
    image_hash = params.get('hash')
    image_name = params.get('image', '')
    rotate = int(params.get('rotate', '0'))

    if not image_hash:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'hash parameter required'})
        }

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

    # rotate 파라미터가 있으면 origin에서 회전 처리
    if rotate != 0:
        try:
            img = Image.open(BytesIO(img_bytes))
            img = img.rotate(-rotate, expand=True)
            buf = BytesIO()
            img.save(buf, format='PNG')
            img_bytes = buf.getvalue()
            print(f"[INFO] Rotated {rotate}° → {img.size}")
        except Exception as e:
            print(f"[WARN] Rotation failed: {e}")

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'image/png',
            'Cache-Control': 'max-age=86400, public'
        },
        'body': base64.b64encode(img_bytes).decode(),
        'isBase64Encoded': True
    }
