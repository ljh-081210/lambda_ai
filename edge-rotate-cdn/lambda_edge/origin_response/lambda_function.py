import base64
import io
import boto3
from botocore.exceptions import ClientError
from PIL import Image

S3_BUCKET = 'gj2026-cdn-bucket'
s3 = boto3.client('s3', region_name='us-east-1')


def parse_qs(qs):
    params = {}
    for kv in (qs or '').split('&'):
        if '=' in kv:
            k, v = kv.split('=', 1)
            params[k.strip()] = v.strip()
    return params


def lambda_handler(event, context):
    cf = event['Records'][0]['cf']
    request = cf['request']
    response = cf['response']

    params = parse_qs(request.get('querystring', ''))
    rotate = int(params.get('rotate', '0')) % 360
    image_name = params.get('image', '')
    print(f"[INFO] image={image_name}, rotate={rotate}")

    if rotate == 0:
        return response

    s3_key = f'images/{image_name}.png'
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        png_bytes = obj['Body'].read()
    except ClientError as e:
        print(f"[ERROR] S3 fetch failed: {e}")
        return response

    img = Image.open(io.BytesIO(png_bytes))
    # PIL rotate: 양수 = 반시계방향(CCW), 음수 = 시계방향(CW)
    rotated = img.rotate(-rotate, expand=True)

    buf = io.BytesIO()
    rotated.save(buf, format='PNG')
    rotated_png = buf.getvalue()
    print(f"[INFO] Rotated {rotate}deg ({img.width}x{img.height} -> {rotated.width}x{rotated.height}), size={len(rotated_png)}")

    response['body'] = base64.b64encode(rotated_png).decode()
    response['bodyEncoding'] = 'base64'
    response['headers']['content-type'] = [{'key': 'Content-Type', 'value': 'image/png'}]
    response['headers'].pop('content-length', None)
    return response
