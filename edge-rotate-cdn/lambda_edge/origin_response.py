import base64
import struct
import zlib
import boto3
from botocore.exceptions import ClientError

S3_BUCKET = 'gj2026-cdn-bucket'
s3 = boto3.client('s3', region_name='us-east-1')


def decode_png_rgb(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError("Not a PNG")

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
            if color_type == 0:
                g = row[x]
                pixels.append((g, g, g))
            elif color_type == 2:
                pixels.append((row[x*3], row[x*3+1], row[x*3+2]))
            elif color_type == 4:
                pixels.append((row[x*2], row[x*2], row[x*2]))
            elif color_type == 6:
                pixels.append((row[x*4], row[x*4+1], row[x*4+2]))
            else:
                pixels.append((row[x*ch], row[x*ch], row[x*ch]))

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

    return (b'\x89PNG\r\n\x1a\n' +
            make_chunk(b'IHDR', ihdr) +
            make_chunk(b'IDAT', compressed) +
            make_chunk(b'IEND', b''))


def rotate_pixels(pixels, w, h, degrees):
    degrees = int(degrees) % 360
    if degrees == 0:
        return pixels, w, h
    elif degrees == 90:
        new_w, new_h = h, w
        new = [pixels[(h - 1 - nx) * w + ny]
               for ny in range(new_h) for nx in range(new_w)]
        return new, new_w, new_h
    elif degrees == 180:
        return list(reversed(pixels)), w, h
    elif degrees == 270:
        new_w, new_h = h, w
        new = [pixels[nx * w + (w - 1 - ny)]
               for ny in range(new_h) for nx in range(new_w)]
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

    s3_key = f'images/{image_name}.png'
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        png_bytes = obj['Body'].read()
    except ClientError as e:
        print(f"[ERROR] S3 fetch failed: {e}")
        return response

    w, h, pixels = decode_png_rgb(png_bytes)
    rotated, new_w, new_h = rotate_pixels(pixels, w, h, rotate)
    rotated_png = encode_png_rgb(rotated, new_w, new_h)
    print(f"[INFO] Rotated {rotate}deg ({w}x{h} -> {new_w}x{new_h}), size={len(rotated_png)}")

    response['body'] = base64.b64encode(rotated_png).decode()
    response['bodyEncoding'] = 'base64'
    response['headers']['content-type'] = [{'key': 'Content-Type', 'value': 'image/png'}]
    response['headers'].pop('content-length', None)
    return response
