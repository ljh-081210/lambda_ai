#!/bin/bash
set -e

echo "=== Stub 라이브러리 생성 ==="

# ── libtiff stub ──────────────────────────────────────────
cat > libtiff_stub.c << 'EOF'
#include <stdlib.h>
#include <string.h>

typedef void TIFF;
typedef unsigned int uint32;
typedef unsigned short uint16;
typedef long tmsize_t;

const char* TIFFGetVersion(void) { return "4.0.0 stub"; }
void  TIFFCleanup(TIFF* t) {}
TIFF* TIFFClientOpen(const char* n, const char* m, void* h,
    void* r, void* w, void* s, void* c, void* u, void* p, void* q) { return NULL; }
void  TIFFClose(TIFF* t) {}
uint32 TIFFComputeStrip(TIFF* t, uint32 r, uint16 s) { return 0; }
void  TIFFError(const char* m, const char* f, ...) {}
TIFF* TIFFFdOpen(int fd, const char* n, const char* m) { return NULL; }
int   TIFFFlush(TIFF* t) { return 0; }
int   TIFFGetField(TIFF* t, uint32 tag, ...) { return 0; }
int   TIFFGetFieldDefaulted(TIFF* t, uint32 tag, ...) { return 0; }
int   TIFFIsTiled(TIFF* t) { return 0; }
int   TIFFMergeFieldInfo(TIFF* t, const void* info, uint32 n) { return 0; }
int   TIFFRGBAImageBegin(void* img, TIFF* t, int s, char* e) { return 0; }
void  TIFFRGBAImageEnd(void* img) {}
int   TIFFRGBAImageGet(void* img, uint32* raster, uint32 w, uint32 h) { return 0; }
int   TIFFRGBAImageOK(TIFF* t, char* e) { return 0; }
tmsize_t TIFFReadEncodedStrip(TIFF* t, uint32 strip, void* buf, tmsize_t size) { return -1; }
tmsize_t TIFFReadTile(TIFF* t, void* buf, uint32 x, uint32 y, uint32 z, uint16 s) { return -1; }
tmsize_t TIFFScanlineSize(TIFF* t) { return 0; }
int   TIFFSetField(TIFF* t, uint32 tag, ...) { return 0; }
int   TIFFSetSubDirectory(TIFF* t, uint32 diroff) { return 0; }
void* TIFFSetWarningHandler(void* h) { return NULL; }
void* TIFFSetWarningHandlerExt(void* h) { return NULL; }
uint32 TIFFStripSize(TIFF* t) { return 0; }
uint32 TIFFTileRowSize(TIFF* t) { return 0; }
uint32 TIFFTileSize(TIFF* t) { return 0; }
int   TIFFVSetField(TIFF* t, uint32 tag, void* ap) { return 0; }
tmsize_t TIFFWriteScanline(TIFF* t, void* buf, uint32 row, uint16 s) { return -1; }
void* _TIFFmemcpy(void* d, const void* s, tmsize_t n) { return memcpy(d, s, n); }
EOF

cat > libtiff.map << 'EOF'
LIBTIFF_4.0 {
    global:
        TIFFGetVersion; TIFFCleanup; TIFFClientOpen; TIFFClose;
        TIFFComputeStrip; TIFFError; TIFFFdOpen; TIFFFlush;
        TIFFGetField; TIFFGetFieldDefaulted; TIFFIsTiled;
        TIFFMergeFieldInfo; TIFFRGBAImageBegin; TIFFRGBAImageEnd;
        TIFFRGBAImageGet; TIFFRGBAImageOK; TIFFReadEncodedStrip;
        TIFFReadTile; TIFFScanlineSize; TIFFSetField; TIFFSetSubDirectory;
        TIFFSetWarningHandler; TIFFSetWarningHandlerExt; TIFFStripSize;
        TIFFTileRowSize; TIFFTileSize; TIFFVSetField; TIFFWriteScanline;
        _TIFFmemcpy;
    local: *;
};
EOF

gcc -shared -fPIC -O2 \
    -Wl,--version-script=libtiff.map \
    -o libtiff-13a02c81.so.6.1.0 libtiff_stub.c
strip --strip-all libtiff-13a02c81.so.6.1.0
echo "libtiff stub: $(wc -c < libtiff-13a02c81.so.6.1.0) bytes"

# ── libxcb stub ───────────────────────────────────────────
cat > libxcb_stub.c << 'EOF'
#include <stdlib.h>

typedef struct { int has_error; } xcb_connection_t;
typedef struct { int root; } xcb_screen_t;
typedef struct { xcb_screen_t* data; } xcb_screen_iterator_t;
typedef struct {} xcb_get_image_reply_t;
typedef int xcb_drawable_t;
typedef unsigned char uint8_t;
typedef unsigned short uint16_t;
typedef unsigned int uint32_t;

xcb_connection_t* xcb_connect(const char* d, int* s) { return NULL; }
int  xcb_connection_has_error(xcb_connection_t* c) { return 1; }
void xcb_disconnect(xcb_connection_t* c) {}
xcb_get_image_reply_t* xcb_get_image(void* c, uint8_t f,
    xcb_drawable_t d, int16_t x, int16_t y,
    uint16_t w, uint16_t h, uint32_t m) { return NULL; }
uint8_t* xcb_get_image_data(xcb_get_image_reply_t* r) { return NULL; }
int xcb_get_image_data_length(xcb_get_image_reply_t* r) { return 0; }
xcb_get_image_reply_t* xcb_get_image_reply(void* c, void* cookie, void** e) { return NULL; }
const void* xcb_get_setup(xcb_connection_t* c) { return NULL; }
void xcb_screen_next(xcb_screen_iterator_t* i) {}
EOF

gcc -shared -fPIC -O2 \
    -o libxcb-64009ff3.so.1.1.0 libxcb_stub.c
strip --strip-all libxcb-64009ff3.so.1.1.0
echo "libxcb stub: $(wc -c < libxcb-64009ff3.so.6.1.0) bytes" 2>/dev/null || \
echo "libxcb stub: $(wc -c < libxcb-64009ff3.so.1.1.0) bytes"

# ── libopenjp2 stub (빈 라이브러리) ──────────────────────
echo "" > libopenjp2_stub.c
gcc -shared -fPIC -O2 \
    -o libopenjp2-56811f71.so.2.5.3 libopenjp2_stub.c
strip --strip-all libopenjp2-56811f71.so.2.5.3
echo "libopenjp2 stub: $(wc -c < libopenjp2-56811f71.so.2.5.3) bytes"

# ── 패키지에 복사 ─────────────────────────────────────────
cp libtiff-13a02c81.so.6.1.0 package/pillow.libs/
cp libxcb-64009ff3.so.1.1.0 package/pillow.libs/
cp libopenjp2-56811f71.so.2.5.3 package/pillow.libs/

echo ""
echo "=== 최종 ZIP 크기 확인 ==="
rm -f edge_function.zip
cd package && zip -r ../edge_function.zip . -x "*.pyc" > /dev/null && cd ..
BYTES=$(wc -c < edge_function.zip)
echo "크기: ${BYTES} bytes ($(echo "scale=2; ${BYTES}/1024" | bc)KB)"

if [ ${BYTES} -lt 1048576 ]; then
    echo "✅ 1MB 이내 → 배포 가능!"
else
    echo "❌ 1MB 초과"
fi

# 정리
rm -f libtiff_stub.c libtiff.map libxcb_stub.c libopenjp2_stub.c
rm -f libtiff-13a02c81.so.6.1.0 libxcb-64009ff3.so.1.1.0 libopenjp2-56811f71.so.2.5.3
