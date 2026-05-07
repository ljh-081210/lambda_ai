def lambda_handler(event, context):
    cf = event['Records'][0]['cf']
    response = cf['response']

    removed = response['headers'].pop('content-length', None)
    print(f"[INFO] origin-response: removed content-length={removed}")

    return response
