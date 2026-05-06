#!/bin/bash
set -e

AWS_REGION="ap-northeast-2"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
LAMBDA_FUNCTION_NAME="cdn-image-server"
S3_BUCKET="gj2026-cdn-bucket"

# ── 1. Origin Lambda Function URL 조회 ──────────────────
echo "=== 1. Origin Function URL 조회 ==="
FUNCTION_URL=$(aws lambda get-function-url-config \
  --function-name ${LAMBDA_FUNCTION_NAME} \
  --region ${AWS_REGION} \
  --query 'FunctionUrl' --output text | sed 's|https://||' | sed 's|/||')
echo "Origin: ${FUNCTION_URL}"

# ── 2. Lambda@Edge 버전 ARN 조회 ────────────────────────
echo "=== 2. Lambda@Edge ARN 조회 ==="
VIEWER_REQUEST_ARN=$(aws lambda list-versions-by-function \
  --function-name cdn-edge-viewer-request \
  --region us-east-1 \
  --query 'Versions[-1].FunctionArn' --output text)

VIEWER_RESPONSE_ARN=$(aws lambda list-versions-by-function \
  --function-name cdn-edge-viewer-response \
  --region us-east-1 \
  --query 'Versions[-1].FunctionArn' --output text)

echo "Viewer Request ARN : ${VIEWER_REQUEST_ARN}"
echo "Viewer Response ARN: ${VIEWER_RESPONSE_ARN}"

# ── 3. CloudFront 캐시 정책 생성 ────────────────────────
echo "=== 3. CloudFront 캐시 정책 생성 (hash 쿼리스트링 기준) ==="
CACHE_POLICY_ID=$(aws cloudfront create-cache-policy \
  --cache-policy-config "{
    \"Name\": \"cdn-edge-rotate-hash-policy\",
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
  --query 'CachePolicy.Id' --output text 2>/dev/null || \
  aws cloudfront list-cache-policies \
    --query "CachePolicyList.Items[?CachePolicy.CachePolicyConfig.Name=='cdn-edge-rotate-hash-policy'].CachePolicy.Id" \
    --output text)
echo "Cache Policy ID: ${CACHE_POLICY_ID}"

# ── 4. 오리진 요청 정책: hash + image + rotate 전달 ──────
echo "=== 4. Origin Request 정책 생성 (image, rotate 쿼리스트링 포함) ==="
ORIGIN_REQUEST_POLICY_ID=$(aws cloudfront create-origin-request-policy \
  --origin-request-policy-config "{
    \"Name\": \"cdn-edge-rotate-origin-policy\",
    \"HeadersConfig\": {\"HeaderBehavior\": \"none\"},
    \"CookiesConfig\": {\"CookieBehavior\": \"none\"},
    \"QueryStringsConfig\": {
      \"QueryStringBehavior\": \"whitelist\",
      \"QueryStrings\": {\"Quantity\": 3, \"Items\": [\"hash\", \"image\", \"rotate\"]}
    }
  }" \
  --query 'OriginRequestPolicy.Id' --output text 2>/dev/null || \
  aws cloudfront list-origin-request-policies \
    --query "OriginRequestPolicyList.Items[?OriginRequestPolicy.OriginRequestPolicyConfig.Name=='cdn-edge-rotate-origin-policy'].OriginRequestPolicy.Id" \
    --output text)
echo "Origin Request Policy ID: ${ORIGIN_REQUEST_POLICY_ID}"

# ── 5. CloudFront Distribution 생성 ─────────────────────
echo "=== 5. CloudFront Distribution 생성 ==="
DISTRIBUTION=$(aws cloudfront create-distribution \
  --distribution-config "{
    \"CallerReference\": \"cdn-edge-rotate-$(date +%s)\",
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
      \"OriginRequestPolicyId\": \"${ORIGIN_REQUEST_POLICY_ID}\",
      \"AllowedMethods\": {
        \"Quantity\": 2,
        \"Items\": [\"GET\", \"HEAD\"],
        \"CachedMethods\": {\"Quantity\": 2, \"Items\": [\"GET\", \"HEAD\"]}
      },
      \"LambdaFunctionAssociations\": {
        \"Quantity\": 2,
        \"Items\": [
          {
            \"LambdaFunctionARN\": \"${VIEWER_REQUEST_ARN}\",
            \"EventType\": \"viewer-request\",
            \"IncludeBody\": false
          },
          {
            \"LambdaFunctionARN\": \"${VIEWER_RESPONSE_ARN}\",
            \"EventType\": \"viewer-response\",
            \"IncludeBody\": true
          }
        ]
      }
    },
    \"Comment\": \"CDN Edge Rotate - origin returns raw image, edge applies rotation\",
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
echo "export DISTRIBUTION_ID=${DISTRIBUTION_ID}"
echo ""
echo "=== 테스트 예시 ==="
echo "# 원본 이미지 요청"
echo "curl 'https://${CLOUDFRONT_DOMAIN}/image?image=dog&rotate=0' -o dog_0.png"
echo "# 90도 회전 요청 (Edge에서 회전 처리)"
echo "curl 'https://${CLOUDFRONT_DOMAIN}/image?image=dog&rotate=90' -o dog_90.png"
echo "# 동일 이미지 재요청 → Cache HIT"
echo "curl -v 'https://${CLOUDFRONT_DOMAIN}/image?image=dog&rotate=90' 2>&1 | grep x-cache"
