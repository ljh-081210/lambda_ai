"""
End-to-End 테스트 스크립트
흐름:
  1. 이미지를 PNG로 변환
  2. 클라이언트에서 pHash 계산 (Lambda@Edge와 동일 알고리즘)
  3. S3에 이미지를 hash 키로 업로드 (origin Lambda가 추론에 사용)
  4. CloudFront에 POST (PNG body)
  5. Lambda@Edge가 동일 pHash 계산 → GET /infer?hash={hash} 변환
  6. X-Cache 헤더로 HIT/MISS 확인

사용법:
  python3 test_e2e.py dog.png dog_rotated.png cat.png
"""
import sys
import os
import io
import math
import boto3
import requests
from PIL import Image, ImageFile, ExifTags

ImageFile.LOAD_TRUNCATED_IMAGES = True

CLOUDFRONT_URL = os.environ.get('CLOUDFRONT_URL', '')
S3_BUCKET = os.environ.get('S3_BUCKET', '')

s3_client = boto3.client('s3', region_name='ap-northeast-2')

MAX_SIZE = 512

# ── Lambda@Edge와 동일한 pHash 알고리즘 ──────────────────
_N = 32
_COS = [[math.cos(math.pi * k * (2 * n + 1) / (2 * _N))
         for n in range(_N)] for k in range(_N)]


def dct1d(x):
    return [sum(x[n] * _COS[k][n] for n in range(_N)) for k in range(_N)]


def phash(img, hash_size=8):
    img = img.convert('L').resize((_N, _N), Image.LANCZOS)
    pixels = list(img.getdata())
    matrix = [[pixels[r * _N + c] for c in range(_N)] for r in range(_N)]
    col_dct = [dct1d([matrix[r][c] for r in range(_N)]) for c in range(_N)]
    row_dct = [dct1d([col_dct[c][k] for c in range(_N)]) for k in range(_N)]
    vals = [row_dct[k][m] for k in range(hash_size) for m in range(hash_size)]
    med = sorted(vals[1:])[len(vals) // 2]
    return int(''.join('1' if v > med else '0' for v in vals), 2)


def canonical_hash(img):
    return format(
        min(phash(img.rotate(a, expand=True)) for a in [0, 90, 180, 270]),
        '016x'
    )


def to_png_bytes(img):
    img = img.convert('RGB')
    if img.width > MAX_SIZE or img.height > MAX_SIZE:
        img.thumbnail((MAX_SIZE, MAX_SIZE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def upload_to_s3(img, image_hash):
    """S3에 JPEG로 저장 (origin Lambda가 MobileNetV2 추론에 사용)"""
    buf = io.BytesIO()
    img.convert('RGB').save(buf, format='JPEG')
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=image_hash,
        Body=buf.getvalue(),
        ContentType='image/jpeg'
    )
    print(f"  S3 업로드: s3://{S3_BUCKET}/{image_hash}")


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


def send_request(image_path):
    img = Image.open(image_path)
    img = fix_exif_rotation(img)

    # 1. pHash 계산 (Lambda@Edge와 동일 알고리즘)
    png_img = img.copy()
    if png_img.width > MAX_SIZE or png_img.height > MAX_SIZE:
        png_img.thumbnail((MAX_SIZE, MAX_SIZE), Image.LANCZOS)
    image_hash = canonical_hash(png_img)

    # 2. S3 업로드 (hash를 키로 저장)
    if S3_BUCKET:
        upload_to_s3(img, image_hash)

    # 3. PNG 바이트 생성
    png_bytes = to_png_bytes(img)

    # 4. CloudFront에 POST (Lambda@Edge가 pHash 계산 → GET 변환)
    response = requests.post(
        CLOUDFRONT_URL,
        data=png_bytes,
        headers={'Content-Type': 'image/png'},
    )

    # 5. 결과 출력
    x_cache = response.headers.get('X-Cache', 'unknown')
    cache_result = 'HIT' if 'Hit' in x_cache else 'MISS'

    print(f"[{image_path}]")
    print(f"  hash   : {image_hash}")
    print(f"  PNG 크기: {len(png_bytes):,} bytes")
    print(f"  X-Cache: {x_cache}")
    print(f"  결과   : Cache {cache_result}")
    try:
        print(f"  응답   : {response.json()}")
    except Exception:
        print(f"  응답   : {response.status_code} {response.text[:200]}")
    print()


if __name__ == '__main__':
    if not CLOUDFRONT_URL:
        print("환경변수 설정 필요:")
        print("  export CLOUDFRONT_URL=https://xxxx.cloudfront.net")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("사용법: python3 test_e2e.py <이미지1> <이미지2> ...")
        sys.exit(1)

    print("=" * 60)
    for path in sys.argv[1:]:
        send_request(path)
    print("=" * 60)
