FROM public.ecr.aws/lambda/python:3.10

# h5py 빌드에 필요한 시스템 패키지 설치
RUN yum install -y gcc python3-devel hdf5-devel pkg-config && yum clean all

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# PYTHONPATH 설정 후 빌드 시점에 ImageNet 가중치 다운로드 (cold start 제거)
RUN PYTHONPATH="${LAMBDA_TASK_ROOT}" python3 -c "\
import os; os.environ['TF_CPP_MIN_LOG_LEVEL']='3'; \
from tensorflow.keras.applications import MobileNetV2; \
MobileNetV2(weights='imagenet'); \
print('MobileNetV2 weights downloaded successfully')"

COPY app.py ${LAMBDA_TASK_ROOT}

CMD [ "app.lambda_handler" ]
