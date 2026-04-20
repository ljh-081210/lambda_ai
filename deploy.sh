#!/bin/bash
set -e

# ── 설정값 (본인 환경에 맞게 수정) ──────────────────────────
AWS_REGION="ap-northeast-2"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="mobilenet-lambda"
IMAGE_TAG="latest"
LAMBDA_FUNCTION_NAME="mobilenet-classifier"
LAMBDA_ROLE_NAME="mobilenet-lambda-role"
# ────────────────────────────────────────────────────────────

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}"

echo "=== 1. ECR 로그인 ==="
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin \
    ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

echo "=== 2. ECR 레포지토리 생성 (이미 있으면 무시) ==="
aws ecr describe-repositories --repository-names ${ECR_REPO} --region ${AWS_REGION} 2>/dev/null || \
    aws ecr create-repository --repository-name ${ECR_REPO} --region ${AWS_REGION}

echo "=== 3. Docker 이미지 빌드 (linux/amd64 강제) ==="
docker build --platform linux/amd64 -t ${ECR_REPO}:${IMAGE_TAG} .

echo "=== 4. ECR 푸시 ==="
docker tag ${ECR_REPO}:${IMAGE_TAG} ${ECR_URI}
docker push ${ECR_URI}

echo "=== 5. IAM 역할 생성 (이미 있으면 무시) ==="
ROLE_ARN=$(aws iam get-role --role-name ${LAMBDA_ROLE_NAME} --query Role.Arn --output text 2>/dev/null || \
    aws iam create-role \
        --role-name ${LAMBDA_ROLE_NAME} \
        --assume-role-policy-document '{
            "Version":"2012-10-17",
            "Statement":[{
                "Effect":"Allow",
                "Principal":{"Service":"lambda.amazonaws.com"},
                "Action":"sts:AssumeRole"
            }]
        }' --query Role.Arn --output text)

aws iam attach-role-policy \
    --role-name ${LAMBDA_ROLE_NAME} \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || true

echo "=== 6. Lambda 함수 생성 또는 업데이트 ==="
if aws lambda get-function --function-name ${LAMBDA_FUNCTION_NAME} --region ${AWS_REGION} 2>/dev/null; then
    echo "기존 함수 업데이트..."
    aws lambda update-function-code \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --image-uri ${ECR_URI} \
        --region ${AWS_REGION}
else
    echo "새 함수 생성..."
    sleep 10  # IAM 역할 전파 대기
    aws lambda create-function \
        --function-name ${LAMBDA_FUNCTION_NAME} \
        --package-type Image \
        --code ImageUri=${ECR_URI} \
        --role ${ROLE_ARN} \
        --memory-size 3008 \
        --timeout 120 \
        --region ${AWS_REGION}
fi

echo ""
echo "✅ 배포 완료: ${LAMBDA_FUNCTION_NAME}"
echo "   이미지: ${ECR_URI}"
