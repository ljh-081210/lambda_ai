#!/bin/bash
set -e

# Lambda@Edge는 반드시 us-east-1에 배포해야 함
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
S3_BUCKET="gj2026-cdn-bucket"

VIEWER_REQUEST_NAME="cdn-edge-viewer-request"
VIEWER_RESPONSE_NAME="cdn-edge-viewer-response"
ROLE_NAME="cdn-edge-role"

echo "=== 1. Lambda@Edge IAM 역할 생성 (이미 있으면 무시) ==="
ROLE_ARN=$(aws iam get-role \
  --role-name ${ROLE_NAME} \
  --query 'Role.Arn' --output text 2>/dev/null || \
  aws iam create-role \
    --role-name ${ROLE_NAME} \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {
          "Service": ["lambda.amazonaws.com", "edgelambda.amazonaws.com"]
        },
        "Action": "sts:AssumeRole"
      }]
    }' --query 'Role.Arn' --output text)
echo "Role ARN: ${ROLE_ARN}"

echo "=== 2. IAM 정책 연결 ==="
aws iam attach-role-policy \
  --role-name ${ROLE_NAME} \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || true

# Viewer Request는 S3에서 이미지를 읽어 pHash 계산에 사용
aws iam put-role-policy \
  --role-name ${ROLE_NAME} \
  --policy-name s3-read-images \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Effect\": \"Allow\",
      \"Action\": [\"s3:GetObject\"],
      \"Resource\": \"arn:aws:s3:::${S3_BUCKET}/images/*\"
    }]
  }" 2>/dev/null || true

sleep 10  # IAM 역할 전파 대기

# ── Viewer Request 배포 ──────────────────────────────────
echo ""
echo "=== 3. [Viewer Request] 패키지 생성 ==="
rm -rf pkg_request viewer_request.zip
mkdir -p pkg_request
cp lambda_function.py pkg_request/
cd pkg_request && zip -r ../viewer_request.zip . && cd ..
echo "패키지 크기: $(wc -c < viewer_request.zip) bytes"

echo "=== 4. [Viewer Request] Lambda 함수 배포 ==="
VR_ARN=$(aws lambda create-function \
  --function-name ${VIEWER_REQUEST_NAME} \
  --runtime python3.11 \
  --role ${ROLE_ARN} \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://viewer_request.zip \
  --timeout 5 \
  --memory-size 128 \
  --region ${AWS_REGION} \
  --query 'FunctionArn' --output text 2>/dev/null || \
  aws lambda update-function-code \
    --function-name ${VIEWER_REQUEST_NAME} \
    --zip-file fileb://viewer_request.zip \
    --region ${AWS_REGION} \
    --query 'FunctionArn' --output text)
echo "Viewer Request ARN: ${VR_ARN}"

echo "=== 5. [Viewer Request] 버전 발행 ==="
aws lambda wait function-updated \
  --function-name ${VIEWER_REQUEST_NAME} \
  --region ${AWS_REGION}

VR_VERSION=$(aws lambda publish-version \
  --function-name ${VIEWER_REQUEST_NAME} \
  --region ${AWS_REGION} \
  --query 'Version' --output text)
VR_VERSIONED_ARN="${VR_ARN}:${VR_VERSION}"
echo "Viewer Request Versioned ARN: ${VR_VERSIONED_ARN}"

# ── Viewer Response 배포 ─────────────────────────────────
echo ""
echo "=== 6. [Viewer Response] 패키지 생성 ==="
rm -rf pkg_response viewer_response.zip
mkdir -p pkg_response
cp viewer_response.py pkg_response/lambda_function.py
cd pkg_response && zip -r ../viewer_response.zip . && cd ..
echo "패키지 크기: $(wc -c < viewer_response.zip) bytes"

echo "=== 7. [Viewer Response] Lambda 함수 배포 ==="
VRES_ARN=$(aws lambda create-function \
  --function-name ${VIEWER_RESPONSE_NAME} \
  --runtime python3.11 \
  --role ${ROLE_ARN} \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://viewer_response.zip \
  --timeout 5 \
  --memory-size 128 \
  --region ${AWS_REGION} \
  --query 'FunctionArn' --output text 2>/dev/null || \
  aws lambda update-function-code \
    --function-name ${VIEWER_RESPONSE_NAME} \
    --zip-file fileb://viewer_response.zip \
    --region ${AWS_REGION} \
    --query 'FunctionArn' --output text)
echo "Viewer Response ARN: ${VRES_ARN}"

echo "=== 8. [Viewer Response] 버전 발행 ==="
aws lambda wait function-updated \
  --function-name ${VIEWER_RESPONSE_NAME} \
  --region ${AWS_REGION}

VRES_VERSION=$(aws lambda publish-version \
  --function-name ${VIEWER_RESPONSE_NAME} \
  --region ${AWS_REGION} \
  --query 'Version' --output text)
VRES_VERSIONED_ARN="${VRES_ARN}:${VRES_VERSION}"
echo "Viewer Response Versioned ARN: ${VRES_VERSIONED_ARN}"

echo ""
echo "✅ Lambda@Edge 배포 완료!"
echo "   Viewer Request  ARN: ${VR_VERSIONED_ARN}"
echo "   Viewer Response ARN: ${VRES_VERSIONED_ARN}"
echo ""
echo "다음 단계: setup_cloudfront.sh 실행"
echo "  export VIEWER_REQUEST_ARN=${VR_VERSIONED_ARN}"
echo "  export VIEWER_RESPONSE_ARN=${VRES_VERSIONED_ARN}"

# 정리
rm -rf pkg_request pkg_response
