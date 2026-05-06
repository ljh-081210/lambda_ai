"""
Lambda@Edge - Viewer Response
BMP 포맷 기반 rotation:
  - 32-bit BMP (BGRA, 4 bytes/pixel): 크기 = 54 + W*H*4
  - 회전해도 W*H = H*W → 파일 크기 동일 → content-length 변경 불필요
  - S3에서 원본 BMP 로드 → 픽셀 회전 → BMP 재인코딩 → body 교체
"""
import base64
import struct
import boto3
from botocore.exceptions import ClientError

S3_BUCKET = 'gj2026-cdn-bucket'
s3 = boto3.client('s3', region_name='us-east-1')


def decode_bmp(data):
    """24/32-bit BMP → (width, height, bpp, [(r,g,b), ...] top-to-bottom)"""
    pixel_offset = struct.unpack_from('<I', data, 10)[0]
    width = struct.unpack_from('<i', data, 18)[0]
    height = struct.unpack_from('<i', data, 22)[0]
    bpp = struct.unpack_from('<H', data, 28)[0]
    ch = bpp // 8
    row_stride = (width * ch + 3) & ~3
    bottom_up = height > 0
    abs_height = abs(height)
    rows = []
    for y in range(abs_height):
        row_start = pixel_offset + y * row_stride
        row = []
        for x in range(width):
            off = row_start + x * ch
            b, g, r = data[off], data[off+1], data[off+2]
            row.append((r, g, b))
        rows.append(row)
    if bottom_up:
        rows = list(reversed(rows))
    return width, abs_height, bpp, [p for row in rows for p in row]


def encode_bmp(pixels, width, height, bpp=32):
    """(r,g,b) list → BMP matching original bpp (24 or 32)"""
    ch = bpp // 8
    row_stride = (width * ch + 3) & ~3
    pixel_data_size = height * row_stride
    file_size = 54 + pixel_data_size
    file_header = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, 54)
    info_header = struct.pack('<IiiHHIIiiII',
        40, width, -height, 1, bpp, 0, pixel_data_size, 0, 0, 0, 0)
    pixel_bytes = bytearray()
    for i in range(height):
        row_data = bytearray()
        for r, g, b in pixels[i * width:(i + 1) * width]:
            if bpp == 32:
                row_data.extend([b, g, r, 255])
            else:
                row_data.extend([b, g, r])
        while len(row_data) < row_stride:
            row_data.append(0)
        pixel_bytes.extend(row_data)
    return file_header + info_header + bytes(pixel_bytes)


def rotate_pixels(pixels, w, h, degrees):
    degrees = int(degrees) % 360
    if degrees == 0:
        return pixels, w, h
    elif degrees == 90:
        new_w, new_h = h, w
        new = [pixels[(h-1-nx)*w+ny] for ny in range(new_h) for nx in range(new_w)]
        return new, new_w, new_h
    elif degrees == 180:
        return list(reversed(pixels)), w, h
    elif degrees == 270:
        new_w, new_h = h, w
        new = [pixels[nx*w+(w-1-ny)] for ny in range(new_h) for nx in range(new_w)]
        return new, new_w, new_h
    return pixels, w, h


def parse_qs(qs):
    params = {}
    for kv in (qs or '').split('&'):
        if '=' in kv:
            k, v = kv.split('=', 1)
            params[k.strip()] = v.strip()
    return params


def lambda_handler(event, context):
    cf = event['Records'][0]['cf']
    request = cf['request']
    response = cf['response']

    params = parse_qs(request.get('querystring', ''))
    rotate = int(params.get('rotate', '0')) % 360
    image_name = params.get('image', '')
    print(f"[INFO] image={image_name}, rotate={rotate}")

    if rotate == 0:
        return response

    s3_key = f'images/{image_name}.bmp'
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        bmp_bytes = obj['Body'].read()
    except ClientError as e:
        print(f"[ERROR] S3 fetch failed: {e}")
        return response

    w, h, bpp, pixels = decode_bmp(bmp_bytes)
    rotated, new_w, new_h = rotate_pixels(pixels, w, h, rotate)
    rotated_bmp = encode_bmp(rotated, new_w, new_h, bpp)
    print(f"[INFO] Rotated {rotate}° ({w}x{h}→{new_w}x{new_h}) bpp={bpp}, size={len(rotated_bmp)}")

    response['body'] = base64.b64encode(rotated_bmp).decode()
    response['bodyEncoding'] = 'base64'
    response['headers']['content-type'] = [{'key': 'Content-Type', 'value': 'image/bmp'}]
    response['headers']['content-length'] = [{'key': 'Content-Length', 'value': str(len(rotated_bmp))}]
    return response
