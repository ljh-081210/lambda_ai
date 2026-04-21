#!/bin/bash
set -e

echo "=== Lambda@Edge 패키지 크기 확인 ==="

rm -rf package edge_function.zip
mkdir -p package

echo "--- 1. Pillow 최소 설치 ---"
pip3 install Pillow --target ./package --quiet --no-deps

echo "--- 2. 불필요한 파일 제거 ---"
find ./package -name "*.pyc" -delete
find ./package -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find ./package -name "tests" -exec rm -rf {} + 2>/dev/null || true
find ./package -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true

# _imaging.cpython 하나만 남기고 나머지 .so 전부 제거
cd package/PIL
ls *.so 2>/dev/null | grep -v "^_imaging\.cpython" | xargs rm -f 2>/dev/null || true

# JPEG 외 PIL 플러그인 제거
# .py 파일은 용량이 작으므로 전부 유지
cd ../..

echo "--- 3. pillow.libs에서 필요한 라이브러리만 남기고 제거 ---"
cd package/pillow.libs
# _imaging.so 실제 의존성: libjpeg, libtiff, libopenjp2, libxcb
ls | grep -v -E "^(libjpeg|libtiff|libopenjp2|libxcb)" | xargs rm -f 2>/dev/null || true
echo "  남은 파일: $(ls)"
cd ../..

echo "--- 4. 모든 .so 파일 strip + UPX 압축 ---"
find ./package -name "*.so*" | while read f; do
    BEFORE=$(wc -c < "$f")
    strip --strip-all "$f" 2>/dev/null || true
    upx --best --force "$f" 2>/dev/null || true
    AFTER=$(wc -c < "$f")
    echo "  $f: ${BEFORE} → ${AFTER} bytes"
done

echo "--- 6. 함수 코드 복사 ---"
cp lambda_function.py ./package/

echo "--- 7. ZIP 생성 ---"
cd package && zip -r ../edge_function.zip . -x "*.pyc" > /dev/null && cd ..

echo ""
echo "=== 결과 ==="
UNZIPPED=$(du -sh package | cut -f1)
ZIPPED=$(du -sh edge_function.zip | cut -f1)
ZIPPED_BYTES=$(wc -c < edge_function.zip)

echo "압축 전: ${UNZIPPED}"
echo "압축 후: ${ZIPPED} (${ZIPPED_BYTES} bytes)"
echo ""

if [ ${ZIPPED_BYTES} -lt 1048576 ]; then
    echo "✅ 1MB 이내 → Lambda@Edge Viewer Request 배포 가능!"
else
    echo "❌ 1MB 초과 ($(echo "scale=2; ${ZIPPED_BYTES}/1048576" | bc)MB) → 불가"
fi
