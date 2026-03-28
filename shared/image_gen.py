import os
import io
import logging
import time
import requests
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

HF_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
HF_API_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}"


def generate_images(
    subject: str,
    output_dir: str,
    count: int = 30,
    style: str = "photorealistic BBC nature documentary style, dense jungle forest background, lush green tropical vegetation, dramatic cinematic lighting, ultra detailed scales and texture, 4K wildlife photography",
) -> list[str]:
    """HuggingFace API로 이미지를 생성한다."""
    token = os.environ["HF_API_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    image_paths = []
    for i in range(count):
        prompt = f"{subject}, {style}"
        logger.info(f"이미지 생성 {i + 1}/{count}: {subject}")

        for attempt in range(2):
            try:
                response = requests.post(
                    HF_API_URL,
                    headers=headers,
                    json={"inputs": prompt},
                    timeout=120,
                )
                if response.status_code == 503:
                    # 모델 로딩 중 — 대기 후 재시도
                    wait = response.json().get("estimated_time", 30)
                    logger.info(f"모델 로딩 중, {wait}초 대기...")
                    time.sleep(min(wait, 60))
                    continue
                response.raise_for_status()

                img = Image.open(io.BytesIO(response.content))
                img_path = os.path.join(output_dir, f"img_{i:03d}.png")
                img.save(img_path)
                image_paths.append(img_path)
                logger.info(f"이미지 저장: {img_path}")
                break
            except Exception as e:
                logger.warning(f"이미지 생성 실패 (시도 {attempt + 1}): {e}")
                if attempt == 1:
                    logger.error(f"이미지 {i + 1} 생성 최종 실패, 건너뜀")
                time.sleep(5)

        # API 부하 방지
        time.sleep(2)

    if not image_paths:
        raise RuntimeError("이미지를 하나도 생성하지 못했습니다.")

    logger.info(f"총 {len(image_paths)}장 이미지 생성 완료")
    return image_paths
