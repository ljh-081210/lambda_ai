"""
End-to-End 테스트 스크립트
흐름:
  1. 이미지를 PNG로 변환 (Lambda@Edge에서 Pillow로 디코딩)
  2. S3에 이미지 업로드 (origin Lambda가 추론에 사용)
  3. CloudFront에 POST (PNG body 포함)
  4. Lambda@Edge가 pHash 계산 → GET /infer?hash={hash} 변환
  5. X-Cache 헤더로 HIT/MISS 확인

사용법:
  python3 test_e2e.py dog.jpeg dog_rotated.jpeg dog2.jpeg
"""
import sys
import os
import io
import boto3
import requests
from PIL import Image, ExifTags

CLOUDFRONT_URL = os.environ.get('CLOUDFRONT_URL', '')
S3_BUCKET = os.environ.get('S3_BUCKET', '')

s3_client = boto3.client('s3', region_name='ap-northeast-2')

MAX_SIZE = 512  # 최대 512x512 (PNG 1MB 이내 유지)


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


def to_png_bytes(img):
    """이미지를 PNG 바이트로 변환 (최대 512x512 리사이즈)"""
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


def send_request(image_path):
    img = Image.open(image_path)
    img = fix_exif_rotation(img)

    # PNG 바이트 변환
    png_bytes = to_png_bytes(img)
    print(f"[{image_path}]")
    print(f"  PNG 크기: {len(png_bytes):,} bytes")

    # CloudFront에 POST (PNG body)
    # Lambda@Edge가 pHash 계산 → GET /infer?hash={hash} 변환
    response = requests.post(
        CLOUDFRONT_URL,
        data=png_bytes,
        headers={'Content-Type': 'image/png'},
    )

    x_cache = response.headers.get('X-Cache', 'unknown')
    cache_result = 'HIT' if 'Hit' in x_cache else 'MISS'

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
