"""
Lambda@Edge - Viewer Request
역할:
  1. GET /image?image=<name>&rotate=<degrees> 요청 수신
  2. S3 images/<name>.png 에서 이미지 로드
  3. 회전 불변 pHash 계산 (0/90/180/270도 중 최솟값)
  4. rotate=0: hash_0 캐시 키로 origin 전달 (CloudFront 캐시 활용)
  5. rotate≠0: viewer-request에서 직접 회전 후 반환 (synthetic response)
"""
import base64
import json
import math
import struct
import zlib
import boto3
from botocore.exceptions import ClientError

S3_BUCKET = 'gj2026-cdn-bucket'
s3 = boto3.client('s3', region_name='us-east-1')

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
        if ft == 1:
            for x in range(ch, stride):
                row[x] = (row[x] + row[x - ch]) & 0xFF
        elif ft == 2:
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 0xFF
        elif ft == 3:
            for x in range(stride):
                a = row[x - ch] if x >= ch else 0
                row[x] = (row[x] + (a + prev[x]) // 2) & 0xFF
        elif ft == 4:
            for x in range(stride):
                a = row[x - ch] if x >= ch else 0
                b, c = prev[x], (prev[x - ch] if x >= ch else 0)
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                p = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                row[x] = (row[x] + p) & 0xFF
        prev = row

        for x in range(width):
            if color_type in (2, 6):
                r, g, b = row[x * ch], row[x * ch + 1], row[x * ch + 2]
                pixels.append((77 * r + 150 * g + 29 * b) >> 8)
            else:
                pixels.append(row[x * ch])

    return width, actual_rows, pixels


def resize_nn(pixels, sw, sh, dw=_N, dh=_N):
    return [pixels[(y * sh // dh) * sw + (x * sw // dw)]
            for y in range(dh) for x in range(dw)]


def rotate90(pixels, w, h):
    return ([pixels[(h - 1 - nx) * w + ny]
             for ny in range(w) for nx in range(h)],
            h, w)


# ── pHash ───────────────────────────────────────────────
def dct1d(x):
    return [sum(x[n] * _COS[k][n] for n in range(_N)) for k in range(_N)]


def phash(pixels_flat, hash_size=8):
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


# ── PNG RGB 디코더 / 인코더 / 회전 ─────────────────────
def decode_png_rgb(data):
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
    d = zlib.decompressobj()
    try:
        raw = d.decompress(idat) + d.flush()
    except zlib.error:
        raw = d.decompress(idat)
    ch = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type, 3)
    stride = width * ch
    prev = bytearray(stride)
    pixels = []
    actual_rows = len(raw) // (stride + 1)
    for y in range(min(height, actual_rows)):
        off = y * (stride + 1)
        ft = raw[off]
        row = bytearray(raw[off + 1:off + 1 + stride])
        if ft == 1:
            for x in range(ch, stride): row[x] = (row[x] + row[x - ch]) & 0xFF
        elif ft == 2:
            for x in range(stride): row[x] = (row[x] + prev[x]) & 0xFF
        elif ft == 3:
            for x in range(stride):
                a = row[x - ch] if x >= ch else 0
                row[x] = (row[x] + (a + prev[x]) // 2) & 0xFF
        elif ft == 4:
            for x in range(stride):
                a = row[x - ch] if x >= ch else 0
                b, c = prev[x], (prev[x - ch] if x >= ch else 0)
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                p = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                row[x] = (row[x] + p) & 0xFF
        prev = row
        for x in range(width):
            if color_type == 2:   pixels.append((row[x*3], row[x*3+1], row[x*3+2]))
            elif color_type == 6: pixels.append((row[x*4], row[x*4+1], row[x*4+2]))
            elif color_type == 0: g = row[x]; pixels.append((g, g, g))
            elif color_type == 4: g = row[x*2]; pixels.append((g, g, g))
            else:                 pixels.append((row[x*ch], row[x*ch], row[x*ch]))
    return width, actual_rows, pixels


def encode_png_rgb(pixels, width, height):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            r, g, b = pixels[y * width + x]
            raw.extend([r, g, b])
    compressed = zlib.compress(bytes(raw), 6)
    def make_chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + make_chunk(b'IHDR', ihdr) +
            make_chunk(b'IDAT', compressed) + make_chunk(b'IEND', b''))


def rotate_image(img_bytes, degrees):
    degrees = degrees % 360
    if degrees == 0:
        return img_bytes
    w, h, pixels = decode_png_rgb(img_bytes)
    if degrees == 90:
        new_w, new_h = h, w
        new = [pixels[(h - 1 - nx) * w + ny] for ny in range(new_h) for nx in range(new_w)]
    elif degrees == 180:
        new, new_w, new_h = list(reversed(pixels)), w, h
    elif degrees == 270:
        new_w, new_h = h, w
        new = [pixels[nx * w + (w - 1 - ny)] for ny in range(new_h) for nx in range(new_w)]
    else:
        return img_bytes
    return encode_png_rgb(new, new_w, new_h)


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

    if not image_name:
        return request

    s3_key = f'images/{image_name}.png'
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

    image_hash = canonical_hash(img_bytes)
    rotate = int(params.get('rotate', '0')) % 360
    print(f"[INFO] image={image_name}, rotate={rotate}, hash={image_hash}")

    # rotate=0이면 캐시 활용 (origin으로 전달)
    if rotate == 0:
        cache_key = f'{image_hash}_0'
        request['uri'] = '/image'
        request['querystring'] = f'hash={cache_key}&image={image_name}&rotate=0'
        return request

    # rotate≠0이면 viewer-request에서 직접 회전 후 반환
    # (viewer-response content-length 제약 우회)
    rotated_png = rotate_image(img_bytes, rotate)
    print(f"[INFO] Rotated {rotate}° in viewer-request, size={len(rotated_png)} bytes")

    return {
        'status': '200',
        'statusDescription': 'OK',
        'headers': {
            'content-type': [{'key': 'Content-Type', 'value': 'image/png'}],
            'content-length': [{'key': 'Content-Length', 'value': str(len(rotated_png))}],
            'cache-control': [{'key': 'Cache-Control', 'value': 'max-age=86400, public'}],
        },
        'body': base64.b64encode(rotated_png).decode(),
        'bodyEncoding': 'base64',
    }
