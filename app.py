import time
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

cold_start_begin = time.perf_counter()

import json
import base64
import numpy as np
import multiprocessing
import imagehash
from PIL import Image, ExifTags
import io
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input, decode_predictions
from tensorflow.keras.preprocessing import image as keras_image

model = MobileNetV2(weights='imagenet')

cold_start_end = time.perf_counter()
cold_start_time = cold_start_end - cold_start_begin

# ImageNet에서 고양이로 분류되는 label 목록
CAT_LABELS = {
    'tabby', 'tiger_cat', 'persian_cat', 'siamese_cat',
    'egyptian_cat', 'cougar', 'lynx', 'leopard', 'snow_leopard',
    'jaguar', 'lion', 'tiger', 'cheetah'
}

# 1단계: pHash 캐시 (시각적으로 동일한 이미지)
phash_cache = {}

# 2단계: label 캐시 (고양이면 무조건 HIT)
label_cache = {}


def fix_exif_rotation(img: Image.Image) -> Image.Image:
    try:
        exif = img._getexif()
        if exif is None:
            return img
        orientation_key = next(k for k, v in ExifTags.TAGS.items() if v == 'Orientation')
        orientation = exif.get(orientation_key)
        rotations = {3: 180, 6: 270, 8: 90}
        if orientation in rotations:
            img = img.rotate(rotations[orientation], expand=True)
    except Exception:
        pass
    return img


def compute_canonical_hash(img: Image.Image) -> str:
    hashes = [str(imagehash.phash(img.rotate(angle))) for angle in [0, 90, 180, 270]]
    return min(hashes)


def preprocess_for_inference(img: Image.Image) -> np.ndarray:
    img_resized = img.convert('RGB').resize((224, 224))
    arr = keras_image.img_to_array(img_resized)
    arr = np.expand_dims(arr, axis=0)
    return preprocess_input(arr)


def load_image_from_event(event: dict) -> Image.Image:
    body = event.get('body') or ''
    is_base64 = event.get('isBase64Encoded', False)

    if is_base64 and body:
        try:
            return Image.open(io.BytesIO(base64.b64decode(body)))
        except Exception:
            pass

    try:
        json_body = json.loads(body)
        return Image.open(io.BytesIO(base64.b64decode(json_body['image'])))
    except Exception:
        pass

    if body:
        try:
            return Image.open(io.BytesIO(base64.b64decode(body)))
        except Exception:
            pass

    raise ValueError("지원하지 않는 요청 형식입니다. image/jpeg 형식을 사용하세요.")


def build_response(status_code: int, body: dict) -> dict:
    return {'statusCode': status_code, 'body': json.dumps(body, ensure_ascii=False)}


def lambda_handler(event, context):
    execution_start = time.perf_counter()

    try:
        img = load_image_from_event(event)
    except ValueError as e:
        return build_response(400, {'error': str(e)})
    except Exception as e:
        return build_response(400, {'error': f'Image load failed: {e}'})

    try:
        img = fix_exif_rotation(img)
        image_hash = compute_canonical_hash(img)
    except Exception as e:
        return build_response(500, {'error': f'Hash computation failed: {e}'})

    # 1단계: pHash 캐시 확인 (AI 실행 없이 즉시 반환)
    if image_hash in phash_cache:
        cached_label = phash_cache[image_hash]
        return build_response(200, {
            **label_cache[cached_label],
            'cache': 'hit',
            'cache_level': 'pHash',
            'execution_time_s': round(time.perf_counter() - execution_start, 4),
        })

    # 2단계: MobileNetV2 추론
    try:
        data = preprocess_for_inference(img)
        inference_start = time.perf_counter()
        preds = model.predict(data, verbose=0)
        inference_end = time.perf_counter()
    except Exception as e:
        return build_response(500, {'error': f'Inference failed: {e}'})

    top5 = decode_predictions(preds, top=5)[0]
    top_label = top5[0][1]
    label = 'cat' if top_label in CAT_LABELS else 'not_cat'

    predictions = [
        {'rank': i + 1, 'class_id': cls_id, 'label': lbl, 'score': round(float(score), 6)}
        for i, (cls_id, lbl, score) in enumerate(top5)
    ]

    result = {
        'label': label,
        'predictions': predictions,
        'cold_start_time_s': round(cold_start_time, 4),
        'inference_time_s': round(inference_end - inference_start, 4),
    }

    # pHash → label 매핑 저장
    phash_cache[image_hash] = label

    # label 캐시 확인 (다른 고양이 사진 HIT)
    if label in label_cache:
        return build_response(200, {
            **label_cache[label],
            'cache': 'hit',
            'cache_level': 'label',
            'execution_time_s': round(time.perf_counter() - execution_start, 4),
        })

    # 완전 MISS → 결과 저장 후 반환
    label_cache[label] = result
    return build_response(200, {
        **result,
        'cache': 'miss',
        'execution_time_s': round(time.perf_counter() - execution_start, 4),
    })
