"""
Lambda@Edge - Viewer Request
역할:
  1. GET /infer?image=<name> 요청에서 image 파라미터 추출
  2. S3 examples/<name>.png 에서 이미지 로드
  3. 회전 불변 pHash 계산 (rotate 파라미터 무관하게 동일 hash)
  4. /infer?hash=xxx 로 리라이트
  5. CloudFront가 hash 기준으로 네이티브 캐시
     → ?image=dog 와 ?image=dog&rotate=90 모두 동일 hash → Cache HIT
"""
import base64
import json
import math
import struct
import zlib
import boto3
from botocore.exceptions import ClientError

S3_BUCKET = 'lambda-ai-ljh'
s3 = boto3.client('s3', region_name='ap-northeast-2')

# DCT cos 테이블 미리 계산
_N = 32
_COS = [[math.cos(math.pi * k * (2 * n + 1) / (2 * _N))
         for n in range(_N)] for k in range(_N)]


# ── 순수 Python PNG 디코더 ──────────────────────────────
def decode_png(data):
    """PNG bytes → (width, height, grayscale_pixels_flat)"""
    assert data[:8] == b'\x89PNG\r\n\x1a\n', "PNG 형식이 아님"
    pos, width, height, color_type, idat = 8, 0, 0, 0, b''
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b'IHDR':
            width, height = struct.unpack('>II', chunk[:8])
            color_type = chunk[9]
        elif tag == b'IDAT':
            idat += chunk
        elif tag == b'IEND':
            break

    print(f"[DEBUG] PNG {width}x{height} color_type={color_type} idat_len={len(idat)}")
    d = zlib.decompressobj()
    parts = []
    try:
        parts.append(d.decompress(idat))
        parts.append(d.flush())
    except zlib.error:
        parts.append(d.decompress(idat))
    raw = b''.join(parts)

    ch = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type, 3)
    stride = width * ch
    prev = bytearray(stride)
    pixels = []
    actual_rows = len(raw) // (stride + 1)
    print(f"[DEBUG] actual_rows={actual_rows}/{height}")

    for y in range(min(height, actual_rows)):
        off = y * (stride + 1)
        ft = raw[off]
        row = bytearray(raw[off + 1:off + 1 + stride])
        if ft == 1:   # Sub
            for x in range(ch, stride):
                row[x] = (row[x] + row[x - ch]) & 0xFF
        elif ft == 2:  # Up
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 0xFF
        elif ft == 3:  # Average
            for x in range(stride):
                a = row[x - ch] if x >= ch else 0
                row[x] = (row[x] + (a + prev[x]) // 2) & 0xFF
        elif ft == 4:  # Paeth
            for x in range(stride):
                a = row[x - ch] if x >= ch else 0
                b, c = prev[x], (prev[x - ch] if x >= ch else 0)
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                p = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                row[x] = (row[x] + p) & 0xFF
        prev = row

        for x in range(width):
            if color_type in (2, 6):   # RGB / RGBA
                r, g, b = row[x * ch], row[x * ch + 1], row[x * ch + 2]
                pixels.append((77 * r + 150 * g + 29 * b) >> 8)
            else:                       # Grayscale / Grayscale+Alpha
                pixels.append(row[x * ch])

    return width, actual_rows, pixels


def resize_nn(pixels, sw, sh, dw=_N, dh=_N):
    """Nearest-neighbor 리사이즈"""
    return [pixels[(y * sh // dh) * sw + (x * sw // dw)]
            for y in range(dh) for x in range(dw)]


def rotate90(pixels, w, h):
    """90도 시계 방향 회전"""
    return ([pixels[(h - 1 - nx) * w + ny]
             for ny in range(w) for nx in range(h)],
            h, w)


# ── pHash ───────────────────────────────────────────────
def dct1d(x):
    return [sum(x[n] * _COS[k][n] for n in range(_N)) for k in range(_N)]


def phash(pixels_flat, hash_size=8):
    """_N×_N 그레이스케일 픽셀 리스트 → pHash 정수"""
    matrix = [[pixels_flat[r * _N + c] for c in range(_N)] for r in range(_N)]
    col_dct = [dct1d([matrix[r][c] for r in range(_N)]) for c in range(_N)]
    row_dct = [dct1d([col_dct[c][k] for c in range(_N)]) for k in range(_N)]
    vals = [row_dct[k][m] for k in range(hash_size) for m in range(hash_size)]
    sv = sorted(vals)
    med = (sv[31] + sv[32]) / 2
    return int(''.join('1' if v > med else '0' for v in vals), 2)


def canonical_hash(img_bytes):
    """회전 불변 pHash: 0/90/180/270도 회전 중 최솟값"""
    w, h, pixels = decode_png(img_bytes)
    hashes = []
    for _ in range(4):
        resized = resize_nn(pixels, w, h)
        hashes.append(phash(resized))
        pixels, w, h = rotate90(pixels, w, h)
    return format(min(hashes), '016x')


# ── 쿼리스트링 파싱 ──────────────────────────────────────
def parse_qs(qs):
    params = {}
    for kv in (qs or '').split('&'):
        if '=' in kv:
            k, v = kv.split('=', 1)
            params[k.strip()] = v.strip()
    return params


# ── Lambda 핸들러 ────────────────────────────────────────
def lambda_handler(event, context):
    request = event['Records'][0]['cf']['request']

    if request['method'] != 'GET':
        return request

    params = parse_qs(request.get('querystring', ''))
    image_name = params.get('image')

    # image 파라미터 없으면 그대로 통과
    # (CloudFront가 캐시된 /infer?hash=xxx 응답을 반환하는 경우)
    if not image_name:
        return request

    # ── S3에서 예시 이미지 로드 ───────────────────────────
    # S3 경로: examples/<name>.png
    s3_key = f'example/{image_name}.png'
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        img_bytes = obj['Body'].read()
        print(f"[INFO] Loaded image from S3: {s3_key} ({len(img_bytes)} bytes)")
    except ClientError as e:
        print(f"[ERROR] Image not found in S3: {s3_key} - {e}")
        return {
            'status': '404',
            'statusDescription': 'Not Found',
            'headers': {
                'content-type': [{'key': 'Content-Type', 'value': 'application/json'}],
            },
            'body': json.dumps({'error': f'Image not found: {image_name}'})
        }

    # ── 회전 불변 pHash 계산 ──────────────────────────────
    # canonical_hash는 0/90/180/270도 중 최솟값 사용
    # → ?rotate=90 파라미터가 있어도 동일한 hash 반환
    image_hash = canonical_hash(img_bytes)
    rotate = params.get('rotate', '0')
    print(f"[INFO] image={image_name}, rotate={rotate}, hash={image_hash}")

    # ── origin Lambda용 이미지 S3 저장 (없을 때만) ────────
    try:
        s3.head_object(Bucket=S3_BUCKET, Key=image_hash)
        print(f"[INFO] Image already cached in S3: {image_hash}")
    except ClientError as e:
        if e.response['Error']['Code'] in ('404', 'NoSuchKey'):
            s3.put_object(Bucket=S3_BUCKET, Key=image_hash,
                          Body=img_bytes, ContentType='image/png')
            print(f"[INFO] Image saved to S3: {image_hash}")
        else:
            print(f"[WARN] S3 head_object error: {e}")

    # ── /infer?hash=xxx 로 리라이트 ───────────────────────
    # CloudFront가 hash 기준으로 캐시:
    #   ?image=dog           → hash=abc → Miss (첫 요청) → 추론 후 캐시
    #   ?image=dog           → hash=abc → Hit from cloudfront ✅
    #   ?image=dog&rotate=90 → hash=abc (동일!) → Hit from cloudfront ✅
    request['uri'] = '/infer'
    request['querystring'] = f'hash={image_hash}'

    return request
