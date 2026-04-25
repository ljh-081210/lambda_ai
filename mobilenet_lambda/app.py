import time
import os
import json
import base64
import boto3
from PIL import Image
from io import BytesIO

cold_start_begin = time.perf_counter()
cold_start_end = time.perf_counter()
cold_start_time = cold_start_end - cold_start_begin

S3_BUCKET = os.environ.get('S3_BUCKET', '')
s3_client = boto3.client('s3')


def build_response(status_code: int, body: dict, cache: bool = False) -> dict:
    headers = {'Content-Type': 'application/json'}
    if cache:
        headers['Cache-Control'] = 'max-age=86400, public'
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps(body, ensure_ascii=False)
    }


def lambda_handler(event, context):
    execution_start = time.perf_counter()

    params = event.get('queryStringParameters') or {}
    image_hash = params.get('hash')
    image_name = params.get('image', '')

    if not image_hash:
        return build_response(400, {'error': 'hash parameter required'})

    # S3에서 이미지 로드
    s3_key = f'images/{image_name}.png'
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
        img_bytes = obj['Body'].read()
    except Exception as e:
        return build_response(404, {'error': f'Image not found in S3: {e}'})

    # 이미지 base64 인코딩
    try:
        img = Image.open(BytesIO(img_bytes)).convert('RGB')
        buf = BytesIO()
        img.save(buf, format='PNG')
        image_b64 = base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        return build_response(500, {'error': f'Image processing failed: {e}'})

    result = {
        'hash': image_hash,
        'image': f'{image_name}.png',
        'image_base64': image_b64,
        'cold_start_time_s': round(cold_start_time, 4),
        'execution_time_s': round(time.perf_counter() - execution_start, 4),
    }

    return build_response(200, result, cache=True)
