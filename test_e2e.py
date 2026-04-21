"""
End-to-End 테스트 스크립트
흐름:
  1. 이미지 pHash 계산 (클라이언트)
  2. S3에 이미지 업로드
  3. CloudFront에 POST (X-Image-Hash 헤더 포함)
  4. X-Cache 헤더로 HIT/MISS 확인

사용법:
  python3 test_e2e.py dog.jpeg dog_rotated.jpeg dog2.jpeg
"""
import sys
import os
import boto3
import requests
import imagehash
from PIL import Image, ExifTags
import io

CLOUDFRONT_URL = os.environ.get('CLOUDFRONT_URL', '')
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


def compute_canonical_hash(img):
    hashes = [str(imagehash.phash(img.rotate(angle))) for angle in [0, 90, 180, 270]]
    return min(hashes)


def upload_to_s3(img, image_hash):
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

    # 1. pHash 계산
    image_hash = compute_canonical_hash(img)

    # 2. S3 업로드 (MISS일 때 Origin Lambda가 사용)
    upload_to_s3(img, image_hash)

    # 3. CloudFront에 POST (X-Image-Hash 헤더 포함)
    with open(image_path, 'rb') as f:
        response = requests.post(
            CLOUDFRONT_URL,
            data=f,
            headers={
                'Content-Type': 'image/jpeg',
                'X-Image-Hash': image_hash,
            }
        )

    # 4. X-Cache 헤더로 HIT/MISS 확인
    x_cache = response.headers.get('X-Cache', 'unknown')
    cache_result = 'HIT' if 'Hit' in x_cache else 'MISS'

    print(f"[{image_path}]")
    print(f"  hash   : {image_hash}")
    print(f"  X-Cache: {x_cache}")
    print(f"  결과   : Cache {cache_result}")
    print(f"  응답   : {response.json()}")
    print()


if __name__ == '__main__':
    if not CLOUDFRONT_URL or not S3_BUCKET:
        print("환경변수 설정 필요:")
        print("  export CLOUDFRONT_URL=https://xxxx.cloudfront.net")
        print("  export S3_BUCKET=mobilenet-images-xxxx")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("사용법: python3 test_e2e.py <이미지1> <이미지2> ...")
        sys.exit(1)

    print("=" * 60)
    for path in sys.argv[1:]:
        send_request(path)
    print("=" * 60)
