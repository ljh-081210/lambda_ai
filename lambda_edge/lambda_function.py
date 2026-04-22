"""
Lambda@Edge - Viewer Request
역할:
  1. POST body에서 이미지 읽기 (PNG)
  2. 순수 Python pHash 계산 (numpy 없음)
  3. POST → GET /infer?hash={pHash} 변환
"""
import base64
import io
import math
from PIL import Image, ImageFile

# 잘린 이미지도 처리 허용 (CloudFront body 전달 시 truncation 대응)
ImageFile.LOAD_TRUNCATED_IMAGES = True

# cos 테이블 미리 계산 (속도 최적화)
_N = 32
_COS = [[math.cos(math.pi * k * (2 * n + 1) / (2 * _N))
         for n in range(_N)] for k in range(_N)]


def dct1d(x):
    return [sum(x[n] * _COS[k][n] for n in range(_N)) for k in range(_N)]


def phash(img, hash_size=8):
    """순수 Python pHash - numpy/scipy 없이 구현"""
    img = img.convert('L').resize((_N, _N), Image.LANCZOS)
    pixels = list(img.getdata())
    matrix = [[pixels[r * _N + c] for c in range(_N)] for r in range(_N)]

    # 열 방향 DCT
    col_dct = [dct1d([matrix[r][c] for r in range(_N)]) for c in range(_N)]
    # 행 방향 DCT
    row_dct = [dct1d([col_dct[c][k] for c in range(_N)]) for k in range(_N)]

    # 좌상단 8x8
    vals = [row_dct[k][m] for k in range(hash_size) for m in range(hash_size)]
    med = sorted(vals[1:])[len(vals) // 2]  # DC 성분(index 0) 제외
    return int(''.join('1' if v > med else '0' for v in vals), 2)


def canonical_hash(img):
    """회전 불변 해시: 0/90/180/270도 회전 중 최솟값"""
    return format(
        min(phash(img.rotate(a, expand=True)) for a in [0, 90, 180, 270]),
        '016x'
    )


def lambda_handler(event, context):
    request = event['Records'][0]['cf']['request']

    # POST 요청만 처리
    if request['method'] != 'POST':
        return request

    # body 읽기
    body_obj = request.get('body', {})
    if not body_obj or not body_obj.get('data'):
        return request

    raw = body_obj['data']
    if body_obj.get('encoding') == 'base64':
        img_bytes = base64.b64decode(raw)
    else:
        img_bytes = raw.encode('latin-1') if isinstance(raw, str) else raw

    # pHash 계산 (PNG로 전송 필요 - stub libjpeg는 JPEG 디코딩 불가)
    img = Image.open(io.BytesIO(img_bytes))
    image_hash = canonical_hash(img)

    # POST → GET /infer?hash={pHash} 변환
    request['method'] = 'GET'
    request['uri'] = '/infer'
    request['querystring'] = f'hash={image_hash}'
    request.pop('body', None)

    return request
