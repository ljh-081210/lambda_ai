"""
Lambda@Edge - Viewer Request
역할:
  1. POST 요청에서 이미지 읽기
  2. pHash 계산 (순수 Python - numpy/ImageHash 불필요)
  3. 이미지 S3 저장
  4. POST → GET /infer?hash={pHash} 변환
"""
import os
import base64
import math
import boto3
from PIL import Image, ExifTags
import io

S3_BUCKET = os.environ.get('S3_BUCKET', '')
s3_client = boto3.client('s3', region_name='ap-northeast-2')


def fix_exif_rotation(img):
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


def dct1d(seq):
    N = len(seq)
    result = []
    for k in range(N):
        s = sum(seq[n] * math.cos(math.pi * (2*n+1) * k / (2*N)) for n in range(N))
        result.append(s * (math.sqrt(1.0/N) if k == 0 else math.sqrt(2.0/N)))
    return result


def phash_pure(img, hash_size=8):
    img_size = hash_size * 4  # 32x32
    img = img.convert('L').resize((img_size, img_size))
    pixels = list(img.getdata())
    matrix = [pixels[i*img_size:(i+1)*img_size] for i in range(img_size)]

    # rows DCT
    dct_rows = [dct1d(row) for row in matrix]
    # transpose → columns DCT
    transposed = [[dct_rows[r][c] for r in range(img_size)] for c in range(img_size)]
    dct_cols = [dct1d(col) for col in transposed]
    # transpose back
    dct_2d = [[dct_cols[c][r] for c in range(img_size)] for r in range(img_size)]

    # low frequency 8x8
    low_freq = [dct_2d[r][c] for r in range(hash_size) for c in range(hash_size)]
    med = sorted(low_freq)[len(low_freq) // 2]
    bits = [1 if v > med else 0 for v in low_freq]
    return f'{int("".join(map(str, bits)), 2):016x}'


def compute_canonical_hash(img):
    hashes = [phash_pure(img.rotate(angle)) for angle in [0, 90, 180, 270]]
    return min(hashes)


def lambda_handler(event, context):
    request = event['Records'][0]['cf']['request']

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

    # pHash 계산 (순수 Python)
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

    # POST → GET 변환
    request['method'] = 'GET'
    request['uri'] = '/infer'
    request['querystring'] = f'hash={image_hash}'
    request['body'] = {}

    return request
