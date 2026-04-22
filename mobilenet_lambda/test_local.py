"""
Lambda 배포 전 로컬 테스트 스크립트
사용법: python test_local.py <이미지파일경로>
예시:  python test_local.py dog.jpg
"""
import sys
import json
import base64


def make_event(image_path: str) -> dict:
    with open(image_path, 'rb') as f:
        encoded = base64.b64encode(f.read()).decode('utf-8')
    return {'body': json.dumps({'image': encoded})}


def main():
    if len(sys.argv) < 2:
        print("사용법: python test_local.py <이미지파일경로>")
        sys.exit(1)

    image_path = sys.argv[1]
    print(f"이미지 로드: {image_path}")

    event = make_event(image_path)

    from app import lambda_handler
    response = lambda_handler(event, None)

    print(f"\n상태 코드: {response['statusCode']}")
    body = json.loads(response['body'])

    if response['statusCode'] == 200:
        print(f"Cold Start 시간: {body['cold_start_time_s']}s")
        print(f"추론 시간: {body['inference_time_s']}s")
        print(f"전체 실행 시간: {body['execution_time_s']}s")
        print(f"\n예측 결과 Top-5:")
        for pred in body['predictions']:
            print(f"  {pred['rank']}. {pred['label']:30s} {pred['score']:.4f}")
    else:
        print(f"에러: {body.get('error')}")


if __name__ == '__main__':
    main()
