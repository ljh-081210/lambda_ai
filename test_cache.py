"""
pHash 기반 캐시 HIT/MISS 로컬 테스트
사용법: python test_cache.py <이미지1> <이미지2> ...
예시:  python test_cache.py dog.jpg dog_rotated.jpg dog2.jpg
"""
import sys
import imagehash
from PIL import Image

cache = {}  # pHash → 결과 저장


def compute_canonical_hash(img: Image.Image) -> str:
    hashes = [str(imagehash.phash(img.rotate(angle))) for angle in [0, 90, 180, 270]]
    return min(hashes)


def request(image_path: str):
    img = Image.open(image_path)
    h = compute_canonical_hash(img)

    if h in cache:
        print(f"[{image_path}] → Cache HIT  (hash: {h})")
    else:
        cache[h] = image_path
        print(f"[{image_path}] → Cache MISS (hash: {h})")


if len(sys.argv) < 2:
    print("사용법: python test_cache.py <이미지1> <이미지2> ...")
    sys.exit(1)

print("=" * 60)
for path in sys.argv[1:]:
    request(path)
print("=" * 60)
