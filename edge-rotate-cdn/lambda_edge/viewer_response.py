import base64
import struct
import boto3
from botocore.exceptions import ClientError

S3_BUCKET = 'gj2026-cdn-bucket'
s3 = boto3.client('s3', region_name='us-east-1')


def decode_bmp_rgba(data):
    pixel_offset = struct.unpack_from('<I', data, 10)[0]
    width = struct.unpack_from('<i', data, 18)[0]
    height = struct.unpack_from('<i', data, 22)[0]
    bpp = struct.unpack_from('<H', data, 28)[0]
    ch = bpp // 8
    row_stride = (width * ch + 3) & ~3
    bottom_up = height > 0
    abs_height = abs(height)
    pixels = []
    for y in range(abs_height):
        row_start = pixel_offset + y * row_stride
        for x in range(width):
            off = row_start + x * ch
            b, g, r = data[off], data[off+1], data[off+2]
            a = data[off+3] if ch == 4 else 255
            pixels.append((r, g, b, a))
    if bottom_up:
        rows = [pixels[y*width:(y+1)*width] for y in range(abs_height)]
        rows.reverse()
        pixels = [p for row in rows for p in row]
    return width, abs_height, pixels


def encode_bmp_rgba(pixels, width, height):
    pixel_data_size = width * height * 4
    file_size = 54 + pixel_data_size
    file_header = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, 54)
    info_header = struct.pack('<IiiHHIIiiII',
        40, width, -height, 1, 32, 0, pixel_data_size, 0, 0, 0, 0)
    pixel_bytes = bytearray()
    for r, g, b, a in pixels:
        pixel_bytes.extend([b, g, r, a])
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

    # 현재 response 상태 로깅
    print(f"[INFO] image={image_name}, rotate={rotate}")
    print(f"[INFO] response status={response['status']}")
    print(f"[INFO] response header keys={list(response['headers'].keys())}")
    for k, v in response['headers'].items():
        print(f"[INFO]   {k}: {v}")

    if rotate == 0:
        return response

    s3_key = f'images/{image_name}.bmp'
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        bmp_bytes = obj['Body'].read()
    except ClientError as e:
        print(f"[ERROR] S3 fetch failed: {e}")
        return response

    w, h, pixels = decode_bmp_rgba(bmp_bytes)
    rotated, new_w, new_h = rotate_pixels(pixels, w, h, rotate)
    rotated_bmp = encode_bmp_rgba(rotated, new_w, new_h)
    print(f"[INFO] Rotated {rotate}° ({w}x{h}→{new_w}x{new_h}), size={len(rotated_bmp)}")

    # 원본 response object에 body만 추가 (headers 건드리지 않음)
    response['body'] = base64.b64encode(rotated_bmp).decode()
    response['bodyEncoding'] = 'base64'
    return response
