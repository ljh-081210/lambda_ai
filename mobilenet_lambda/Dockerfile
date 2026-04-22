FROM public.ecr.aws/lambda/python:3.10

COPY requirements.txt ./
# --prefer-binary: 소스 컴파일 대신 미리 빌드된 wheel 사용 (h5py 컴파일 오류 방지)
RUN pip3 install --no-cache-dir --prefer-binary -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# PYTHONPATH 설정 후 빌드 시점에 ImageNet 가중치 다운로드 (cold start 제거)
RUN PYTHONPATH="${LAMBDA_TASK_ROOT}" python3 -c "\
import os; os.environ['TF_CPP_MIN_LOG_LEVEL']='3'; \
from tensorflow.keras.applications import MobileNetV2; \
MobileNetV2(weights='imagenet'); \
print('MobileNetV2 weights downloaded successfully')"

COPY app.py ${LAMBDA_TASK_ROOT}

CMD [ "app.lambda_handler" ]
