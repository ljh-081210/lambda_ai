"""
Lambda@Edge - Viewer Request (GET + X-Image-Data header 방식)
역할:
  1. GET 요청의 X-Image-Data 헤더에서 base64 인코딩된 PNG 이미지 읽기
  2. pHash 계산 (순수 Python DCT)
  3. S3 결과 캐시 확인 → HIT이면 바로 반환
  4. MISS면 이미지 S3 저장 후 X-Image-Data 헤더 제거, ?hash=xxx 추가하여 origin으로 전달
  5. X-Image-Data 없는 GET은 그대로 통과 (CloudFront 캐시 응답)
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

    return width, height, pixels


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


# ── Lambda 핸들러 ────────────────────────────────────────
def lambda_handler(event, context):
    request = event['Records'][0]['cf']['request']

    # GET 요청이 아니거나 X-Image-Data 헤더가 없으면 그대로 통과
    # (CloudFront가 캐시된 응답을 반환하는 경우)
    if request['method'] != 'GET':
        return request

    headers = request.get('headers', {})
    image_data_header = headers.get('x-image-data', [])
    if not image_data_header:
        return request

    # X-Image-Data 헤더에서 base64 인코딩된 이미지 추출
    raw_b64 = image_data_header[0]['value']
    try:
        img_bytes = base64.b64decode(raw_b64)
    except Exception as e:
        print(f"[ERROR] base64 decode failed: {e}")
        return {
            'status': '400',
            'statusDescription': 'Bad Request',
            'headers': {
                'content-type': [{'key': 'Content-Type', 'value': 'application/json'}],
            },
            'body': json.dumps({'error': 'Invalid base64 in X-Image-Data header'})
        }

    image_hash = canonical_hash(img_bytes)
    print(f"[INFO] hash={image_hash}, size={len(img_bytes)}")

    # ── S3 결과 캐시 확인 ──────────────────────────────────
    result_key = f"result/{image_hash}.json"
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=result_key)
        cached = obj['Body'].read().decode('utf-8')
        print(f"[INFO] Cache HIT: {result_key}")
        return {
            'status': '200',
            'statusDescription': 'OK',
            'headers': {
                'content-type': [{'key': 'Content-Type', 'value': 'application/json'}],
                'x-cache-status': [{'key': 'X-Cache-Status', 'value': 'HIT'}],
                'cache-control': [{'key': 'Cache-Control', 'value': 'max-age=86400, public'}],
            },
            'body': cached
        }
    except ClientError as e:
        if e.response['Error']['Code'] != 'NoSuchKey':
            print(f"[WARN] S3 cache check error: {e}")
    except Exception as e:
        print(f"[WARN] S3 cache check error: {e}")

    # ── Cache MISS: 이미지 S3 저장 후 origin으로 전달 ────────
    print(f"[INFO] Cache MISS: {result_key}")
    s3.put_object(Bucket=S3_BUCKET, Key=image_hash, Body=img_bytes, ContentType='image/png')

    # X-Image-Data 헤더 제거 (origin Lambda는 S3에서 이미지를 읽음)
    headers.pop('x-image-data', None)
    request['headers'] = headers

    # /infer?hash=xxx 로 라우팅
    request['uri'] = '/infer'
    request['querystring'] = f'hash={image_hash}'

    return request
