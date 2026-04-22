"""
Lambda@Edge - Viewer Request
역할:
  1. POST body에서 PNG 이미지 읽기 (순수 Python, Pillow 없음)
  2. pHash 계산 (순수 Python DCT)
  3. S3에 이미지 저장 (hash를 키로)
  4. POST → GET /infer?hash={pHash} 변환
"""
import base64
import math
import struct
import zlib
import boto3

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

    raw = zlib.decompress(idat)
    ch = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type, 3)
    stride = width * ch
    prev = bytearray(stride)
    pixels = []

    for y in range(height):
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
    med = (sv[31] + sv[32]) / 2  # 64개 값의 중앙값 (imagehash 방식)
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

    if request['method'] != 'POST':
        return request

    body_obj = request.get('body', {})
    if not body_obj or not body_obj.get('data'):
        return request

    raw = body_obj['data']
    img_bytes = base64.b64decode(raw) if body_obj.get('encoding') == 'base64' \
        else (raw.encode('latin-1') if isinstance(raw, str) else raw)

    image_hash = canonical_hash(img_bytes)
    print(f"[INFO] hash={image_hash}, size={len(img_bytes)}")

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=image_hash,
        Body=img_bytes,
        ContentType='image/png'
    )

    request['method'] = 'GET'
    request['uri'] = '/infer'
    request['querystring'] = f'hash={image_hash}'
    request.pop('body', None)

    return request
