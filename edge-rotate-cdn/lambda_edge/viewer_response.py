import base64
import io
import boto3
from botocore.exceptions import ClientError
from PIL import Image

S3_BUCKET = 'gj2026-cdn-bucket'
s3 = boto3.client('s3', region_name='us-east-1')

# Pillow transpose: 90°CW=ROTATE_270, 180°=ROTATE_180, 270°CW=ROTATE_90
ROTATE_MAP = {
    90: Image.Transpose.ROTATE_270,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}


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

    s3_key = f'images/{image_name}.bmp'
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        bmp_bytes = obj['Body'].read()
    except ClientError as e:
        print(f"[ERROR] S3 fetch failed: {e}")
        return response

    img = Image.open(io.BytesIO(bmp_bytes))
    if rotate in ROTATE_MAP:
        img = img.transpose(ROTATE_MAP[rotate])

    buf = io.BytesIO()
    img.save(buf, format='BMP')
    rotated_bmp = buf.getvalue()
    print(f"[INFO] Rotated {rotate}°, original={len(bmp_bytes)}, new={len(rotated_bmp)}")

    response['body'] = base64.b64encode(rotated_bmp).decode()
    response['bodyEncoding'] = 'base64'
    response['headers']['content-type'] = [{'key': 'Content-Type', 'value': 'image/bmp'}]
    response['headers'].pop('content-length', None)
    return response
