#!/bin/bash
set -e

AWS_REGION="us-east-1"

REQUEST_NAME="gj2026-cdn-request"
RESPONSE_NAME="gj2026-cdn-response"

# ── Viewer Request 배포 ──────────────────────────────────
echo "=== [Viewer Request] 패키지 생성 ==="
rm -rf /tmp/pkg_request /tmp/viewer_request.zip
mkdir -p /tmp/pkg_request
cp viewer_request/lambda_function.py /tmp/pkg_request/
cd /tmp/pkg_request && zip -r /tmp/viewer_request.zip . && cd -
echo "패키지 크기: $(wc -c < /tmp/viewer_request.zip) bytes"

echo "=== [Viewer Request] Lambda 배포 ==="
aws lambda update-function-code \
  --function-name ${REQUEST_NAME} \
  --zip-file fileb:///tmp/viewer_request.zip \
  --region ${AWS_REGION}

aws lambda wait function-updated \
  --function-name ${REQUEST_NAME} \
  --region ${AWS_REGION}

REQUEST_ARN=$(aws lambda publish-version \
  --function-name ${REQUEST_NAME} \
  --region ${AWS_REGION} \
  --query 'FunctionArn' --output text)
echo "Viewer Request ARN: ${REQUEST_ARN}"

# ── Origin Response 배포 (Pillow 포함) ───────────────────
echo ""
echo "=== [Origin Response] Pillow 패키지 설치 ==="
rm -rf /tmp/pkg_response /tmp/origin_response.zip
mkdir -p /tmp/pkg_response

pip install Pillow \
  --platform manylinux2014_x86_64 \
  --target /tmp/pkg_response \
  --only-binary=:all: \
  --python-version 3.14

cp origin_response/lambda_function.py /tmp/pkg_response/
echo "패키지 크기 (압축 전): $(du -sh /tmp/pkg_response | cut -f1)"

cd /tmp/pkg_response && zip -r9 /tmp/origin_response.zip . && cd -
echo "패키지 크기: $(wc -c < /tmp/origin_response.zip) bytes"

echo "=== [Origin Response] Lambda 배포 ==="
aws lambda update-function-code \
  --function-name ${RESPONSE_NAME} \
  --zip-file fileb:///tmp/origin_response.zip \
  --region ${AWS_REGION}

aws lambda wait function-updated \
  --function-name ${RESPONSE_NAME} \
  --region ${AWS_REGION}

RESPONSE_ARN=$(aws lambda publish-version \
  --function-name ${RESPONSE_NAME} \
  --region ${AWS_REGION} \
  --query 'FunctionArn' --output text)
echo "Origin Response ARN: ${RESPONSE_ARN}"

# ── 캐시 무효화 ──────────────────────────────────────────
echo ""
echo "=== CloudFront 캐시 무효화 ==="
DIST_ID=$(aws cloudfront list-distributions \
  --query 'DistributionList.Items[0].Id' --output text)
aws cloudfront create-invalidation \
  --distribution-id ${DIST_ID} \
  --paths '/images*'

# 정리
rm -rf /tmp/pkg_request /tmp/pkg_response

echo ""
echo "✅ Lambda@Edge 배포 완료!"
echo "   Viewer Request  ARN: ${REQUEST_ARN}"
echo "   Origin Response ARN: ${RESPONSE_ARN}"
echo ""
echo "⚠️  CloudFront Behavior에서 ARN을 최신 버전으로 업데이트하세요."
