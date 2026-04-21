"""
Lambda@Edge - Viewer Request
역할:
  1. POST 요청에서 이미지 읽기
  2. pHash 계산 (회전 불변)
  3. 이미지 S3 저장
  4. POST → GET /infer?hash={pHash} 변환
"""
import os
import base64
import boto3
import imagehash
from PIL import Image, ExifTags
import io

S3_BUCKET = os.environ.get('S3_BUCKET', '')

s3_client = boto3.client('s3', region_name='ap-northeast-2')


def fix_exif_rotation(img: Image.Image) -> Image.Image:
    try:
        exif = img._getexif()
        if exif is None:
            return img
        orientation_key = next(k for k, v in ExifTags.TAGS.items() if v == 'Orientation')
        orientation = exif.get(orientation_key)
        rotations = {3: 180, 6: 270, 8: 90}
        if orientation in rotations:
            img = img.rotate(rotations[orientation], expand=True)
    except Exception:
        pass
    return img


def compute_canonical_hash(img: Image.Image) -> str:
    hashes = [str(imagehash.phash(img.rotate(angle))) for angle in [0, 90, 180, 270]]
    return min(hashes)


def lambda_handler(event, context):
    request = event['Records'][0]['cf']['request']

    # POST 요청만 처리
    if request['method'] != 'POST':
        return request

    # body 읽기
    body_data = request.get('body', {})
    body = body_data.get('data', '')
    encoding = body_data.get('encoding', 'text')

    if encoding == 'base64':
        img_bytes = base64.b64decode(body)
    else:
        img_bytes = body.encode('utf-8') if isinstance(body, str) else body

    # 이미지 로드
    img = Image.open(io.BytesIO(img_bytes))
    img = fix_exif_rotation(img)

    # pHash 계산
    image_hash = compute_canonical_hash(img)

    # S3에 이미지 저장
    buf = io.BytesIO()
    img.convert('RGB').save(buf, format='JPEG')
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=image_hash,
        Body=buf.getvalue(),
        ContentType='image/jpeg'
    )

    # POST → GET 변환 (/infer?hash={pHash})
    request['method'] = 'GET'
    request['uri'] = '/infer'
    request['querystring'] = f'hash={image_hash}'
    request['body'] = {}

    return request
