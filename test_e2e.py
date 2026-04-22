"""
End-to-End 테스트 스크립트
흐름:
  1. 클라이언트: 이미지를 PNG로 변환 후 POST
  2. Lambda@Edge: pHash 계산 + S3 업로드 + GET 변환
  3. CloudFront: hash 기준으로 캐시 (HIT/MISS)
  4. Origin Lambda: S3에서 이미지 가져와서 MobileNetV2 추론

사용법:
  export CLOUDFRONT_URL=https://xxxx.cloudfront.net
  python3 test_e2e.py dog.png dog_rotated.png cat.png
"""
import sys
import os
import io
import requests
from PIL import Image, ImageFile, ExifTags

ImageFile.LOAD_TRUNCATED_IMAGES = True

CLOUDFRONT_URL = os.environ.get('CLOUDFRONT_URL', '')
MAX_SIZE = 512


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
    img = img.convert('RGB')
    if img.width > MAX_SIZE or img.height > MAX_SIZE:
        img.thumbnail((MAX_SIZE, MAX_SIZE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def send_request(image_path):
    img = Image.open(image_path)
    img = fix_exif_rotation(img)
    png_bytes = to_png_bytes(img)

    # CloudFront에 POST (Lambda@Edge가 pHash 계산 + S3 업로드 + GET 변환)
    response = requests.post(
        CLOUDFRONT_URL,
        data=png_bytes,
        headers={'Content-Type': 'image/png'},
    )

    x_cache = response.headers.get('X-Cache', 'unknown')
    cache_result = 'HIT' if 'Hit' in x_cache else 'MISS'

    print(f"[{image_path}]")
    print(f"  PNG 크기: {len(png_bytes):,} bytes")
    print(f"  X-Cache : {x_cache}")
    print(f"  결과    : Cache {cache_result}")
    try:
        print(f"  응답    : {response.json()}")
    except Exception:
        print(f"  응답    : {response.status_code} {response.text[:200]}")
    print()


if __name__ == '__main__':
    if not CLOUDFRONT_URL:
        print("환경변수 설정 필요: export CLOUDFRONT_URL=https://xxxx.cloudfront.net")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("사용법: python3 test_e2e.py <이미지1> <이미지2> ...")
        sys.exit(1)

    print("=" * 60)
    for path in sys.argv[1:]:
        send_request(path)
    print("=" * 60)
