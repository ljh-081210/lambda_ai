"""
Lambda@Edge - Viewer Request
역할:
  1. GET /images?image=<name>&rotate=<degrees> 요청 수신
  2. rotate 값 정규화 (% 360)
  3. origin Lambda에 image, rotate 파라미터 전달
"""


def parse_qs(qs):
    params = {}
    for kv in (qs or '').split('&'):
        if '=' in kv:
            k, v = kv.split('=', 1)
            params[k.strip()] = v.strip()
    return params


def lambda_handler(event, context):
    request = event['Records'][0]['cf']['request']

    if request['method'] != 'GET':
        return request

    params = parse_qs(request.get('querystring', ''))
    image_name = params.get('image')

    if not image_name:
        return request

    rotate = int(params.get('rotate', '0')) % 360
    request['uri'] = '/image'
    request['querystring'] = f'image={image_name}&rotate={rotate}'
    return request
