#!/bin/bash
set -e

echo "=== Stub 라이브러리 생성 ==="

# 실제 파일명 동적 탐지
LIBJPEG_FILE=$(ls package/pillow.libs/libjpeg-*.so.* 2>/dev/null | head -1)
LIBTIFF_FILE=$(ls package/pillow.libs/libtiff-*.so.* 2>/dev/null | head -1)
LIBXCB_FILE=$(ls package/pillow.libs/libxcb-*.so.* 2>/dev/null | head -1)
LIBOPENJP2_FILE=$(ls package/pillow.libs/libopenjp2-*.so.* 2>/dev/null | head -1)

echo "대체 대상:"
echo "  libjpeg  : ${LIBJPEG_FILE:-없음}"
echo "  libtiff  : ${LIBTIFF_FILE:-없음}"
echo "  libxcb   : ${LIBXCB_FILE:-없음}"
echo "  libopenjp2: ${LIBOPENJP2_FILE:-없음}"

# ── libjpeg stub ──────────────────────────────────────────
cat > libjpeg_stub.c << 'EOF'
#include <stdlib.h>
#include <string.h>

struct jpeg_error_mgr {
    void* error_exit; void* emit_message; void* output_message;
    void* format_message; void* reset_error_mgr;
    int msg_code;
    union { int i[8]; char s[80]; double d; } msg_parm;
    int trace_level; long num_warnings;
    const char* const* jpeg_message_table; int last_jpeg_message;
    const char* const* addon_message_table;
    int first_addon_message; int last_addon_message;
};

typedef void* j_common_ptr;
typedef void* j_compress_ptr;
typedef void* j_decompress_ptr;

struct jpeg_error_mgr* jpeg_std_error(struct jpeg_error_mgr* err) {
    memset(err, 0, sizeof(*err)); return err;
}
void jpeg_CreateDecompress(j_decompress_ptr c, int v, size_t s) {}
void jpeg_CreateCompress(j_compress_ptr c, int v, size_t s) {}
int  jpeg_add_quant_table(j_compress_ptr c, int w, const unsigned int* b, int s, int f) { return 0; }
void jpeg_destroy_compress(j_compress_ptr c) {}
void jpeg_destroy_decompress(j_decompress_ptr c) {}
int  jpeg_finish_compress(j_compress_ptr c) { return 0; }
int  jpeg_finish_decompress(j_decompress_ptr c) { return 0; }
int  jpeg_quality_scaling(int q) { return q; }
int  jpeg_read_header(j_decompress_ptr c, int r) { return 0; }
unsigned int jpeg_read_scanlines(j_decompress_ptr c, unsigned char** s, unsigned int m) { return 0; }
int  jpeg_resync_to_restart(j_decompress_ptr c, int d) { return 0; }
void jpeg_set_colorspace(j_compress_ptr c, int cs) {}
void jpeg_set_defaults(j_compress_ptr c) {}
void jpeg_set_quality(j_compress_ptr c, int q, int f) {}
void jpeg_simple_progression(j_compress_ptr c) {}
int  jpeg_start_compress(j_compress_ptr c, int w) { return 0; }
int  jpeg_start_decompress(j_decompress_ptr c) { return 0; }
void jpeg_suppress_tables(j_compress_ptr c, int s) {}
void jpeg_write_marker(j_compress_ptr c, int m, const unsigned char* d, unsigned int l) {}
unsigned int jpeg_write_scanlines(j_compress_ptr c, unsigned char** s, unsigned int n) { return 0; }
void jpeg_write_tables(j_compress_ptr c) {}
EOF

cat > libjpeg.map << 'EOF'
LIBJPEG_6.2 {
    global:
        jpeg_std_error; jpeg_CreateCompress; jpeg_CreateDecompress;
        jpeg_add_quant_table; jpeg_destroy_compress; jpeg_destroy_decompress;
        jpeg_finish_compress; jpeg_finish_decompress; jpeg_quality_scaling;
        jpeg_read_header; jpeg_read_scanlines; jpeg_resync_to_restart;
        jpeg_set_colorspace; jpeg_set_defaults; jpeg_set_quality;
        jpeg_simple_progression; jpeg_start_compress; jpeg_start_decompress;
        jpeg_suppress_tables; jpeg_write_marker; jpeg_write_scanlines;
        jpeg_write_tables;
    local: *;
};
EOF

gcc -shared -fPIC -O2 \
    -Wl,--version-script=libjpeg.map \
    -o libjpeg_stub.so libjpeg_stub.c
strip --strip-all libjpeg_stub.so
echo "libjpeg stub: $(wc -c < libjpeg_stub.so) bytes"

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
    -o libtiff_stub.so libtiff_stub.c
strip --strip-all libtiff_stub.so
echo "libtiff stub: $(wc -c < libtiff_stub.so) bytes"

# ── libxcb stub ───────────────────────────────────────────
cat > libxcb_stub.c << 'EOF'
#include <stdlib.h>

typedef struct { int has_error; } xcb_connection_t;
typedef struct { int root; } xcb_screen_t;
typedef struct { xcb_screen_t* data; } xcb_screen_iterator_t;
typedef struct { int pad; } xcb_get_image_reply_t;
typedef int xcb_drawable_t;
typedef unsigned char uint8_t;
typedef unsigned short uint16_t;
typedef unsigned int uint32_t;

xcb_connection_t* xcb_connect(const char* d, int* s) { return NULL; }
int  xcb_connection_has_error(xcb_connection_t* c) { return 1; }
void xcb_disconnect(xcb_connection_t* c) {}
xcb_get_image_reply_t* xcb_get_image(void* c, uint8_t f,
    xcb_drawable_t d, short x, short y,
    uint16_t w, uint16_t h, uint32_t m) { return NULL; }
uint8_t* xcb_get_image_data(xcb_get_image_reply_t* r) { return NULL; }
int xcb_get_image_data_length(xcb_get_image_reply_t* r) { return 0; }
xcb_get_image_reply_t* xcb_get_image_reply(void* c, void* cookie, void** e) { return NULL; }
const void* xcb_get_setup(xcb_connection_t* c) { return NULL; }
void xcb_screen_next(xcb_screen_iterator_t* i) {}
xcb_screen_iterator_t xcb_setup_roots_iterator(const void* s) {
    xcb_screen_iterator_t i = {NULL}; return i;
}
EOF

gcc -shared -fPIC -O2 -o libxcb_stub.so libxcb_stub.c
strip --strip-all libxcb_stub.so
echo "libxcb stub: $(wc -c < libxcb_stub.so) bytes"

# ── libopenjp2 stub ───────────────────────────────────────
cat > libopenjp2_stub.c << 'EOF'
#include <stdlib.h>

typedef void opj_codec_t;
typedef void opj_image_t;
typedef void opj_stream_t;
typedef struct { int x0,y0,x1,y1; int numresolutions; } opj_dparameters_t;
typedef struct { int numresolution; } opj_cparameters_t;

opj_codec_t* opj_create_compress(int fmt) { return NULL; }
opj_codec_t* opj_create_decompress(int fmt) { return NULL; }
int  opj_decode_tile_data(opj_codec_t* c, unsigned int idx, unsigned char* d, unsigned long long len, opj_stream_t* s) { return 0; }
void opj_destroy_codec(opj_codec_t* c) {}
int  opj_encoder_set_extra_options(opj_codec_t* c, const char** opts) { return 1; }
int  opj_end_compress(opj_codec_t* c, opj_stream_t* s) { return 0; }
int  opj_end_decompress(opj_codec_t* c, opj_stream_t* s) { return 0; }
opj_image_t* opj_image_create(unsigned int n, void* cmptparms, int clrspc) { return NULL; }
void opj_image_destroy(opj_image_t* img) {}
int  opj_read_header(opj_stream_t* s, opj_codec_t* c, opj_image_t** img) { return 0; }
int  opj_read_tile_header(opj_codec_t* c, unsigned int* tidx, unsigned long long* dlen,
    int* tx0, int* ty0, int* tx1, int* ty1,
    unsigned int* ncomps, int* go_on, opj_stream_t* s) { return 0; }
void opj_set_default_decoder_parameters(opj_dparameters_t* p) {}
void opj_set_default_encoder_parameters(opj_cparameters_t* p) {}
int  opj_set_error_handler(opj_codec_t* c, void* h, void* d) { return 1; }
int  opj_set_info_handler(opj_codec_t* c, void* h, void* d) { return 1; }
int  opj_set_warning_handler(opj_codec_t* c, void* h, void* d) { return 1; }
int  opj_setup_decoder(opj_codec_t* c, opj_dparameters_t* p) { return 0; }
int  opj_setup_encoder(opj_codec_t* c, opj_cparameters_t* p, opj_image_t* img) { return 0; }
int  opj_start_compress(opj_codec_t* c, opj_image_t* img, opj_stream_t* s) { return 0; }
opj_stream_t* opj_stream_create(unsigned long long bsize, int is_input) { return NULL; }
void opj_stream_destroy(opj_stream_t* s) {}
void opj_stream_set_read_function(opj_stream_t* s, void* fn) {}
void opj_stream_set_seek_function(opj_stream_t* s, void* fn) {}
void opj_stream_set_skip_function(opj_stream_t* s, void* fn) {}
void opj_stream_set_user_data(opj_stream_t* s, void* d, void* fn) {}
void opj_stream_set_user_data_length(opj_stream_t* s, unsigned long long len) {}
void opj_stream_set_write_function(opj_stream_t* s, void* fn) {}
const char* opj_version(void) { return "2.5.4 stub"; }
int  opj_write_tile(opj_codec_t* c, unsigned int tidx, unsigned char* d, unsigned int dlen, opj_stream_t* s) { return 0; }
EOF

gcc -shared -fPIC -O2 -o libopenjp2_stub.so libopenjp2_stub.c
strip --strip-all libopenjp2_stub.so
echo "libopenjp2 stub: $(wc -c < libopenjp2_stub.so) bytes"

# ── 패키지에 복사 (동적 파일명으로 원본 덮어쓰기) ────────
echo ""
echo "--- 원본 .so 파일을 stub으로 교체 ---"

if [ -n "$LIBJPEG_FILE" ]; then
    cp libjpeg_stub.so "$LIBJPEG_FILE"
    echo "  ✅ libjpeg  교체: $LIBJPEG_FILE ($(wc -c < "$LIBJPEG_FILE") bytes)"
fi
if [ -n "$LIBTIFF_FILE" ]; then
    cp libtiff_stub.so "$LIBTIFF_FILE"
    echo "  ✅ libtiff  교체: $LIBTIFF_FILE ($(wc -c < "$LIBTIFF_FILE") bytes)"
fi
if [ -n "$LIBXCB_FILE" ]; then
    cp libxcb_stub.so "$LIBXCB_FILE"
    echo "  ✅ libxcb   교체: $LIBXCB_FILE ($(wc -c < "$LIBXCB_FILE") bytes)"
fi
if [ -n "$LIBOPENJP2_FILE" ]; then
    cp libopenjp2_stub.so "$LIBOPENJP2_FILE"
    echo "  ✅ libopenjp2 교체: $LIBOPENJP2_FILE ($(wc -c < "$LIBOPENJP2_FILE") bytes)"
fi

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
rm -f libjpeg_stub.c libjpeg.map libjpeg_stub.so
rm -f libtiff_stub.c libtiff.map libtiff_stub.so
rm -f libxcb_stub.c libxcb_stub.so
rm -f libopenjp2_stub.c libopenjp2_stub.so
