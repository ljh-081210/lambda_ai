"""
hash 없이 캐시 테스트 (비교용)
- 이미지를 그대로 캐시 키로 사용
- 회전 시켜도 항상 Cache Miss 됨을 확인

사용법: python3 test_no_hash.py dog.jpeg dog_rotated.jpeg
"""
import sys
import hashlib
from PIL import Image
import io

# 캐시 (이미지 raw bytes → 결과)
raw_cache = {}

def request(image_path):
    img = Image.open(image_path)

    # hash 없이 raw bytes 그대로 캐시 키로 사용
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    raw_key = hashlib.md5(buf.getvalue()).hexdigest()

    if raw_key in raw_cache:
        print(f"[{image_path}] → Cache HIT  (key: {raw_key[:16]}...)")
    else:
        raw_cache[raw_key] = True
        print(f"[{image_path}] → Cache MISS (key: {raw_key[:16]}...)")

if len(sys.argv) < 2:
    print("사용법: python3 test_no_hash.py <이미지1> <이미지2> ...")
    sys.exit(1)

# 회전 이미지 자동 생성
original_path = sys.argv[1]
img = Image.open(original_path)
rotated_path = original_path.replace('.', '_rotated.')
img.rotate(90).save(rotated_path)
print(f"회전 이미지 생성: {rotated_path}\n")

print("=" * 60)
print("[hash 없음] raw bytes 기반 캐시 테스트")
print("=" * 60)

for path in sys.argv[1:] + [rotated_path]:
    request(path)

print("=" * 60)
print("\n※ 회전된 이미지는 bytes가 달라서 항상 Cache MISS")
print("※ pHash를 써야 회전 이미지도 Cache HIT 가능")
