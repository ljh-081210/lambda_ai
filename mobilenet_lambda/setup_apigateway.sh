#!/bin/bash
set -e

AWS_REGION="ap-northeast-2"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
LAMBDA_FUNCTION_NAME="mobilenet-classifier"
API_NAME="mobilenet-api"

echo "=== 1. API Gateway 생성 ==="
API_ID=$(aws apigateway create-rest-api \
  --name ${API_NAME} \
  --binary-media-types "image/jpeg" "image/png" "image/jpg" "*/*" \
  --region ${AWS_REGION} \
  --query 'id' --output text)
echo "API ID: ${API_ID}"

echo "=== 2. 루트 리소스 ID 조회 ==="
ROOT_ID=$(aws apigateway get-resources \
  --rest-api-id ${API_ID} \
  --region ${AWS_REGION} \
  --query 'items[0].id' --output text)

echo "=== 3. /infer 리소스 생성 ==="
RESOURCE_ID=$(aws apigateway create-resource \
  --rest-api-id ${API_ID} \
  --parent-id ${ROOT_ID} \
  --path-part "infer" \
  --region ${AWS_REGION} \
  --query 'id' --output text)
echo "Resource ID: ${RESOURCE_ID}"

echo "=== 4. POST 메서드 생성 ==="
aws apigateway put-method \
  --rest-api-id ${API_ID} \
  --resource-id ${RESOURCE_ID} \
  --http-method POST \
  --authorization-type NONE \
  --region ${AWS_REGION}

echo "=== 5. Lambda 통합 설정 ==="
LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${LAMBDA_FUNCTION_NAME}"
aws apigateway put-integration \
  --rest-api-id ${API_ID} \
  --resource-id ${RESOURCE_ID} \
  --http-method POST \
  --type AWS_PROXY \
  --integration-http-method POST \
  --uri "arn:aws:apigateway:${AWS_REGION}:lambda:path/2015-03-31/functions/${LAMBDA_ARN}/invocations" \
  --content-handling CONVERT_TO_BINARY \
  --region ${AWS_REGION}

echo "=== 6. Lambda 호출 권한 부여 ==="
aws lambda add-permission \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --statement-id apigateway-invoke \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:${AWS_REGION}:${AWS_ACCOUNT_ID}:${API_ID}/*/POST/infer" \
  --region ${AWS_REGION}

echo "=== 7. API 배포 ==="
aws apigateway create-deployment \
  --rest-api-id ${API_ID} \
  --stage-name prod \
  --region ${AWS_REGION}

API_URL="https://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com/prod/infer"
echo ""
echo "✅ API Gateway 배포 완료!"
echo "   엔드포인트: ${API_URL}"
echo ""
echo "=== 테스트 명령어 ==="
echo "curl -X POST '${API_URL}' \\"
echo "  -H 'Content-Type: image/jpeg' \\"
echo "  --data-binary @cat.jpeg"
