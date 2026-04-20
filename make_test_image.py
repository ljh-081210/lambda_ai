"""테스트용 더미 이미지 생성 (224x224 랜덤 RGB)"""
from PIL import Image
import random

img = Image.new('RGB', (224, 224), color=(
    random.randint(0, 255),
    random.randint(0, 255),
    random.randint(0, 255)
))
img.save('test.jpg')
print("test.jpg 생성 완료")
