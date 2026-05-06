#!/bin/bash
set -e

# ── 설정값 ──────────────────────────────────────────────
AWS_REGION="ap-northeast-2"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
LAMBDA_FUNCTION_NAME="cdn-image-server"
LAMBDA_ROLE_NAME="cdn-image-server-role"
S3_BUCKET="gj2026-cdn-bucket"
# ────────────────────────────────────────────────────────

echo "=== 1. IAM 역할 생성 (이미 있으면 무시) ==="
ROLE_ARN=$(aws iam get-role \
  --role-name ${LAMBDA_ROLE_NAME} \
  --query 'Role.Arn' --output text 2>/dev/null || \
  aws iam create-role \
    --role-name ${LAMBDA_ROLE_NAME} \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "lambda.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }' --query 'Role.Arn' --output text)
echo "Role ARN: ${ROLE_ARN}"

echo "=== 2. IAM 정책 연결 ==="
aws iam attach-role-policy \
  --role-name ${LAMBDA_ROLE_NAME} \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || true

# S3 읽기 권한 (인라인 정책)
aws iam put-role-policy \
  --role-name ${LAMBDA_ROLE_NAME} \
  --policy-name s3-read-images \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Effect\": \"Allow\",
      \"Action\": [\"s3:GetObject\"],
      \"Resource\": \"arn:aws:s3:::${S3_BUCKET}/images/*\"
    }]
  }" 2>/dev/null || true

echo "=== 3. 배포 패키지 생성 ==="
rm -f function.zip
zip function.zip lambda_function.py
echo "패키지 크기: $(wc -c < function.zip) bytes"

echo "=== 4. Lambda 함수 생성 또는 업데이트 ==="
if aws lambda get-function --function-name ${LAMBDA_FUNCTION_NAME} --region ${AWS_REGION} 2>/dev/null; then
    echo "기존 함수 업데이트..."
    aws lambda update-function-code \
      --function-name ${LAMBDA_FUNCTION_NAME} \
      --zip-file fileb://function.zip \
      --region ${AWS_REGION}
    aws lambda wait function-updated \
      --function-name ${LAMBDA_FUNCTION_NAME} \
      --region ${AWS_REGION}
    aws lambda update-function-configuration \
      --function-name ${LAMBDA_FUNCTION_NAME} \
      --environment "Variables={S3_BUCKET=${S3_BUCKET}}" \
      --region ${AWS_REGION}
else
    echo "새 함수 생성..."
    sleep 10  # IAM 역할 전파 대기
    aws lambda create-function \
      --function-name ${LAMBDA_FUNCTION_NAME} \
      --runtime python3.11 \
      --role ${ROLE_ARN} \
      --handler lambda_function.lambda_handler \
      --zip-file fileb://function.zip \
      --environment "Variables={S3_BUCKET=${S3_BUCKET}}" \
      --memory-size 256 \
      --timeout 30 \
      --region ${AWS_REGION}
fi

echo "=== 5. Function URL 생성 (이미 있으면 무시) ==="
FUNCTION_URL=$(aws lambda get-function-url-config \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --region ${AWS_REGION} \
  --query 'FunctionUrl' --output text 2>/dev/null || \
  aws lambda create-function-url-config \
    --function-name ${LAMBDA_FUNCTION_NAME} \
    --auth-type NONE \
    --region ${AWS_REGION} \
    --query 'FunctionUrl' --output text)

# CloudFront에서 호출 허용
aws lambda add-permission \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --statement-id allow-cloudfront \
  --action lambda:InvokeFunctionUrl \
  --principal "*" \
  --function-url-auth-type NONE \
  --region ${AWS_REGION} 2>/dev/null || true

echo ""
echo "✅ Origin Lambda 배포 완료!"
echo "   Function Name : ${LAMBDA_FUNCTION_NAME}"
echo "   Function URL  : ${FUNCTION_URL}"
echo "   S3 Bucket     : ${S3_BUCKET}"
