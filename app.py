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


def fix_exif_rotation(img: Image.Image) -> Image.Image:
    """EXIF 회전 정보가 있으면 보정"""
    try:
        exif = img._getexif()
        if exif is None:
            return img
        orientation_key = next(
            k for k, v in ExifTags.TAGS.items() if v == 'Orientation'
        )
        orientation = exif.get(orientation_key)
        rotations = {3: 180, 6: 270, 8: 90}
        if orientation in rotations:
            img = img.rotate(rotations[orientation], expand=True)
    except Exception:
        pass
    return img


def compute_canonical_hash(img: Image.Image) -> str:
    """
    0°, 90°, 180°, 270° 회전 중 가장 작은 pHash를 정규 해시로 사용.
    같은 이미지를 어떤 각도로 돌려도 동일한 해시가 나옴.
    """
    hashes = [
        str(imagehash.phash(img.rotate(angle)))
        for angle in [0, 90, 180, 270]
    ]
    return min(hashes)


def preprocess_for_inference(img: Image.Image) -> np.ndarray:
    img_resized = img.convert('RGB').resize((224, 224))
    arr = keras_image.img_to_array(img_resized)
    arr = np.expand_dims(arr, axis=0)
    return preprocess_input(arr)


def lambda_handler(event, context):
    execution_start = time.perf_counter()

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError) as e:
        return {'statusCode': 400, 'body': json.dumps({'error': f'Invalid JSON: {e}'})}

    if 'image' not in body:
        return {'statusCode': 400, 'body': json.dumps({'error': "'image' field (base64) is required"})}

    try:
        image_bytes = base64.b64decode(body['image'])
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        return {'statusCode': 400, 'body': json.dumps({'error': f'Image load failed: {e}'})}

    # EXIF 보정 후 정규 해시 계산
    try:
        img = fix_exif_rotation(img)
        image_hash = compute_canonical_hash(img)
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': f'Hash computation failed: {e}'})}

    # MobileNetV2 추론
    try:
        data = preprocess_for_inference(img)
        inference_start = time.perf_counter()
        preds = model.predict(data, verbose=0)
        inference_end = time.perf_counter()
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': f'Inference failed: {e}'})}

    top5 = decode_predictions(preds, top=5)[0]
    results = [
        {'rank': i + 1, 'class_id': cls_id, 'label': label, 'score': round(float(score), 6)}
        for i, (cls_id, label, score) in enumerate(top5)
    ]

    execution_end = time.perf_counter()

    return {
        'statusCode': 200,
        'body': json.dumps({
            'image_hash': image_hash,        # CloudFront 캐시 키로 사용될 값
            'predictions': results,
            'cold_start_time_s': round(cold_start_time, 4),
            'inference_time_s': round(inference_end - inference_start, 4),
            'execution_time_s': round(execution_end - execution_start, 4),
            'num_cores': multiprocessing.cpu_count(),
        })
    }
