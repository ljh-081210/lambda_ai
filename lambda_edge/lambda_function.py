"""
Lambda@Edge - Viewer Request
역할:
  1. POST 요청에서 X-Image-Hash 헤더 읽기
  2. POST → GET /infer?hash={pHash} 변환
  (pHash 계산은 클라이언트에서 수행)
"""


def lambda_handler(event, context):
    request = event['Records'][0]['cf']['request']

    # POST 요청만 처리
    if request['method'] != 'POST':
        return request

    # 클라이언트가 보낸 X-Image-Hash 헤더에서 hash 읽기
    headers = request.get('headers', {})
    hash_header = headers.get('x-image-hash', [{}])
    image_hash = hash_header[0].get('value', '') if hash_header else ''

    if not image_hash:
        # hash 없으면 그대로 통과
        return request

    # POST → GET /infer?hash={pHash} 변환
    request['method'] = 'GET'
    request['uri'] = '/infer'
    request['querystring'] = f'hash={image_hash}'
    request['body'] = {}

    return request
