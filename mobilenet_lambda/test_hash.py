"""
회전 불변 pHash 검증 스크립트
사용법: python3 test_hash.py cat.jpeg
"""
import sys
from PIL import Image
from app import compute_canonical_hash, fix_exif_rotation

if len(sys.argv) < 2:
    print("사용법: python3 test_hash.py <이미지파일>")
    sys.exit(1)

img = Image.open(sys.argv[1])
img = fix_exif_rotation(img)

print("=== 회전별 정규 해시 검증 ===\n")
for angle in [0, 90, 180, 270]:
    rotated = img.rotate(angle)
    h = compute_canonical_hash(rotated)
    print(f"  {angle:3d}도 회전 → hash: {h}")

print()
hashes = {compute_canonical_hash(img.rotate(a)) for a in [0, 90, 180, 270]}
if len(hashes) == 1:
    print("✅ 모든 회전에서 동일한 해시 → CloudFront cache hit 가능")
else:
    print("⚠️  해시가 다름 → 이미지가 회전 시 시각적으로 크게 달라지는 경우")
