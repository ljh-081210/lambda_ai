#!/bin/bash
set -e

# Lambda@Edge는 반드시 us-east-1에 배포해야 함
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
FUNCTION_NAME="mobilenet-edge"
S3_BUCKET="mobilenet-images-${AWS_ACCOUNT_ID}"
ROLE_NAME="mobilenet-edge-role"

echo "=== 1. Lambda@Edge IAM 역할 생성 ==="
ROLE_ARN=$(aws iam create-role \
  --role-name ${ROLE_NAME} \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Service": ["lambda.amazonaws.com", "edgelambda.amazonaws.com"]
        },
        "Action": "sts:AssumeRole"
      }
    ]
  }' \
  --query 'Role.Arn' --output text 2>/dev/null || \
  aws iam get-role --role-name ${ROLE_NAME} --query 'Role.Arn' --output text)
echo "Role ARN: ${ROLE_ARN}"

echo "=== 2. IAM 정책 연결 ==="
aws iam attach-role-policy \
  --role-name ${ROLE_NAME} \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || true

aws iam put-role-policy \
  --role-name ${ROLE_NAME} \
  --policy-name s3-access \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Effect\": \"Allow\",
      \"Action\": [\"s3:PutObject\", \"s3:GetObject\"],
      \"Resource\": \"arn:aws:s3:::${S3_BUCKET}/*\"
    }]
  }"

echo "=== 3. 패키지 설치 ==="
pip3 install Pillow ImageHash --target ./package --quiet

echo "=== 4. 배포 패키지 생성 ==="
cp lambda_function.py ./package/
cd package && zip -r ../edge_function.zip . -x "*.pyc" > /dev/null && cd ..
echo "패키지 크기: $(du -sh edge_function.zip | cut -f1)"

echo "=== 5. Lambda@Edge 함수 생성 (us-east-1) ==="
sleep 10  # IAM 역할 전파 대기

FUNCTION_ARN=$(aws lambda create-function \
  --function-name ${FUNCTION_NAME} \
  --runtime python3.11 \
  --role ${ROLE_ARN} \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://edge_function.zip \
  --timeout 5 \
  --memory-size 128 \
  --environment "Variables={S3_BUCKET=${S3_BUCKET}}" \
  --region ${AWS_REGION} \
  --query 'FunctionArn' --output text 2>/dev/null || \
  aws lambda update-function-code \
    --function-name ${FUNCTION_NAME} \
    --zip-file fileb://edge_function.zip \
    --region ${AWS_REGION} \
    --query 'FunctionArn' --output text)
echo "Function ARN: ${FUNCTION_ARN}"

echo "=== 6. Lambda 버전 발행 (CloudFront 연결용) ==="
VERSION=$(aws lambda publish-version \
  --function-name ${FUNCTION_NAME} \
  --region ${AWS_REGION} \
  --query 'Version' --output text)
echo "Version: ${VERSION}"

VERSIONED_ARN="${FUNCTION_ARN}:${VERSION}"
echo ""
echo "✅ Lambda@Edge 배포 완료!"
echo "   버전 ARN: ${VERSIONED_ARN}"
echo ""
echo "※ CloudFront 설정 시 이 ARN을 Viewer Request에 연결하세요."
echo "   ${VERSIONED_ARN}"
