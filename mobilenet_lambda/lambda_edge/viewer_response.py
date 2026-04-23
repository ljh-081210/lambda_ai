"""
Lambda@Edge - Viewer Response
역할:
  1. 캐시된 응답 JSON에서 image_base64 추출
  2. 요청의 X-Rotate 헤더로 회전 각도 확인
  3. 순수 Python으로 이미지 회전
  4. 회전된 이미지를 응답에 포함하여 반환

흐름:
  ?image=dog         → hit → Viewer Response: rotate=0  → 원본 이미지
  ?image=dog&rotate=90 → hit → Viewer Response: rotate=90 → 90도 회전 이미지
  (추론 결과는 동일, 이미지만 회전)
"""
import base64
import json
import struct
import zlib


# ── PNG 디코더 (RGB) ─────────────────────────────────────
def decode_png_rgb(data):
    """PNG bytes → (width, height, [(r,g,b), ...])"""
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
            if color_type == 0:    # Grayscale
                g = row[x]
                pixels.append((g, g, g))
            elif color_type == 2:  # RGB
                pixels.append((row[x*3], row[x*3+1], row[x*3+2]))
            elif color_type == 4:  # Grayscale+Alpha
                pixels.append((row[x*2], row[x*2], row[x*2]))
            elif color_type == 6:  # RGBA
                pixels.append((row[x*4], row[x*4+1], row[x*4+2]))
            else:
                pixels.append((row[x*ch], row[x*ch], row[x*ch]))

    return width, actual_rows, pixels


# ── PNG 인코더 (RGB) ─────────────────────────────────────
def encode_png_rgb(pixels, width, height):
    """[(r,g,b), ...] → PNG bytes"""
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: None
        for x in range(width):
            r, g, b = pixels[y * width + x]
            raw.extend([r, g, b])

    compressed = zlib.compress(bytes(raw), 6)

    def make_chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)  # 8-bit RGB

    return (b'\x89PNG\r\n\x1a\n' +
            make_chunk(b'IHDR', ihdr) +
            make_chunk(b'IDAT', compressed) +
            make_chunk(b'IEND', b''))


# ── 이미지 회전 (시계방향, 90도 단위) ───────────────────
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


# ── Lambda 핸들러 ────────────────────────────────────────
def lambda_handler(event, context):
    cf = event['Records'][0]['cf']
    request = cf['request']
    response = cf['response']

    # X-Rotate 헤더에서 회전 각도 추출
    req_headers = request.get('headers', {})
    rotate_header = req_headers.get('x-rotate', [])
    rotate = int(rotate_header[0]['value']) if rotate_header else 0

    if rotate == 0:
        return response

    # 응답 body 파싱
    body = response.get('body', '')
    if not body:
        return response

    try:
        data = json.loads(body)
        image_b64 = data.get('image_base64', '')
        if not image_b64:
            return response

        # base64 → PNG → 픽셀 → 회전 → PNG → base64
        img_bytes = base64.b64decode(image_b64)
        w, h, pixels = decode_png_rgb(img_bytes)
        rotated, new_w, new_h = rotate_pixels(pixels, w, h, rotate)
        rotated_png = encode_png_rgb(rotated, new_w, new_h)

        data['image_base64'] = base64.b64encode(rotated_png).decode()
        data['rotate'] = rotate

        response['body'] = json.dumps(data, ensure_ascii=False)
        print(f"[INFO] Rotated {rotate}° ({w}x{h} → {new_w}x{new_h})")

    except Exception as e:
        print(f"[WARN] Rotation failed: {e}")

    return response
