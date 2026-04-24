import time
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ.setdefault('KERAS_HOME', '/var/task/.keras')

cold_start_begin = time.perf_counter()

import json
import numpy as np
import boto3
from PIL import Image
from io import BytesIO
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input, decode_predictions
from tensorflow.keras.preprocessing import image as keras_image

model = MobileNetV2(weights='imagenet')

cold_start_end = time.perf_counter()
cold_start_time = cold_start_end - cold_start_begin

S3_BUCKET = os.environ.get('S3_BUCKET', '')

s3_client = boto3.client('s3')


def preprocess_for_inference(img: Image.Image) -> np.ndarray:
    img_resized = img.convert('RGB').resize((224, 224))
    arr = keras_image.img_to_array(img_resized)
    arr = np.expand_dims(arr, axis=0)
    return preprocess_input(arr)


def build_response(status_code: int, body: dict, cache: bool = False) -> dict:
    headers = {'Content-Type': 'application/json'}
    if cache:
        headers['Cache-Control'] = 'max-age=86400, public'
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps(body, ensure_ascii=False)
    }


def lambda_handler(event, context):
    execution_start = time.perf_counter()

    params = event.get('queryStringParameters') or {}
    image_hash = params.get('hash')
    image_name = params.get('image', '')

    if not image_hash:
        return build_response(400, {'error': 'hash parameter required'})

    # ── S3에서 이미지 로드 ────────────────────────────────
    s3_key = f'images/{image_name}.png'
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
        img = Image.open(BytesIO(obj['Body'].read()))
    except Exception as e:
        return build_response(404, {'error': f'Image not found in S3: {e}'})

    # ── AI 추론 ───────────────────────────────────────────
    try:
        data = preprocess_for_inference(img)
        inference_start = time.perf_counter()
        preds = model.predict(data, verbose=0)
        inference_end = time.perf_counter()
    except Exception as e:
        return build_response(500, {'error': f'Inference failed: {e}'})

    top5 = decode_predictions(preds, top=5)[0]
    predictions = [
        {'class': lbl, 'probability': round(float(score), 6)}
        for _, lbl, score in top5
    ]

    result = {
        'hash': image_hash,
        'image': f'{image_name}.png',
        'predictions': predictions,
        'cold_start_time_s': round(cold_start_time, 4),
        'inference_time_s': round(inference_end - inference_start, 4),
        'execution_time_s': round(time.perf_counter() - execution_start, 4),
    }

    return build_response(200, result, cache=True)
