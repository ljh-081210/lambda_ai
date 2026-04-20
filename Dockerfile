FROM public.ecr.aws/lambda/python:3.10

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# 빌드 시점에 ImageNet 가중치 다운로드하여 이미지에 포함 (cold start 시 다운로드 제거)
RUN python3 -c "\
import os; os.environ['TF_CPP_MIN_LOG_LEVEL']='3'; \
from tensorflow.keras.applications import MobileNetV2; \
MobileNetV2(weights='imagenet'); \
print('MobileNetV2 weights downloaded successfully')"

COPY app.py ${LAMBDA_TASK_ROOT}

CMD [ "app.lambda_handler" ]
