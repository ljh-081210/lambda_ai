#!/bin/bash
set -e

AWS_REGION="ap-northeast-2"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
LAMBDA_FUNCTION_NAME="mobilenet-classifier"
EDGE_FUNCTION_NAME="mobilenet-edge"
S3_BUCKET="mobilenet-images-${AWS_ACCOUNT_ID}"

# Lambda Function URL (origin)
FUNCTION_URL=$(aws lambda get-function-url-config \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --region ${AWS_REGION} \
  --query 'FunctionUrl' --output text | sed 's|https://||' | sed 's|/||')

# Lambda@Edge 버전 ARN
EDGE_ARN=$(aws lambda list-versions-by-function \
  --function-name ${EDGE_FUNCTION_NAME} \
  --region us-east-1 \
  --query 'Versions[-1].FunctionArn' --output text)

echo "Origin: ${FUNCTION_URL}"
echo "Edge ARN: ${EDGE_ARN}"

echo "=== 1. CloudFront 캐시 정책 생성 (hash 쿼리스트링 포함) ==="
CACHE_POLICY_ID=$(aws cloudfront create-cache-policy \
  --cache-policy-config "{
    \"Name\": \"mobilenet-hash-policy\",
    \"DefaultTTL\": 86400,
    \"MaxTTL\": 31536000,
    \"MinTTL\": 0,
    \"ParametersInCacheKeyAndForwardedToOrigin\": {
      \"EnableAcceptEncodingGzip\": true,
      \"EnableAcceptEncodingBrotli\": true,
      \"HeadersConfig\": {\"HeaderBehavior\": \"none\"},
      \"CookiesConfig\": {\"CookieBehavior\": \"none\"},
      \"QueryStringsConfig\": {
        \"QueryStringBehavior\": \"whitelist\",
        \"QueryStrings\": {\"Quantity\": 1, \"Items\": [\"hash\"]}
      }
    }
  }" \
  --query 'CachePolicy.Id' --output text)
echo "Cache Policy ID: ${CACHE_POLICY_ID}"

echo "=== 2. CloudFront Distribution 생성 ==="
DISTRIBUTION=$(aws cloudfront create-distribution \
  --distribution-config "{
    \"CallerReference\": \"mobilenet-$(date +%s)\",
    \"Origins\": {
      \"Quantity\": 1,
      \"Items\": [{
        \"Id\": \"lambda-origin\",
        \"DomainName\": \"${FUNCTION_URL}\",
        \"CustomOriginConfig\": {
          \"HTTPSPort\": 443,
          \"OriginProtocolPolicy\": \"https-only\"
        }
      }]
    },
    \"DefaultCacheBehavior\": {
      \"TargetOriginId\": \"lambda-origin\",
      \"ViewerProtocolPolicy\": \"redirect-to-https\",
      \"CachePolicyId\": \"${CACHE_POLICY_ID}\",
      \"AllowedMethods\": {
        \"Quantity\": 7,
        \"Items\": [\"GET\",\"HEAD\",\"OPTIONS\",\"PUT\",\"POST\",\"PATCH\",\"DELETE\"],
        \"CachedMethods\": {\"Quantity\": 2, \"Items\": [\"GET\",\"HEAD\"]}
      },
      \"LambdaFunctionAssociations\": {
        \"Quantity\": 1,
        \"Items\": [{
          \"LambdaFunctionARN\": \"${EDGE_ARN}\",
          \"EventType\": \"viewer-request\",
          \"IncludeBody\": false
        }]
      }
    },
    \"Comment\": \"MobileNet CloudFront\",
    \"Enabled\": true
  }")

DISTRIBUTION_ID=$(echo ${DISTRIBUTION} | python3 -c "import sys,json; print(json.load(sys.stdin)['Distribution']['Id'])")
CLOUDFRONT_DOMAIN=$(echo ${DISTRIBUTION} | python3 -c "import sys,json; print(json.load(sys.stdin)['Distribution']['DomainName'])")

echo ""
echo "✅ CloudFront 배포 완료!"
echo "   Distribution ID : ${DISTRIBUTION_ID}"
echo "   CloudFront URL  : https://${CLOUDFRONT_DOMAIN}"
echo ""
echo "=== 환경변수 설정 ==="
echo "export CLOUDFRONT_URL=https://${CLOUDFRONT_DOMAIN}"
echo "export S3_BUCKET=${S3_BUCKET}"
