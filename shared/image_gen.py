import os
import io
import logging
import time
import requests
import random
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

HF_MODEL = "black-forest-labs/FLUX.1-schnell"
HF_API_URL = f"https://router.huggingface.co/hf-inference/models/{HF_MODEL}"

PEXELS_API_URL = "https://api.pexels.com/v1/search"

# 공룡 채널용 다양한 씬 타입 (과학적 정확도 기반)
_DINO_SCENE_TEMPLATES = [
    "{subject} dinosaur, full body lateral view, {env}, paleontologically accurate reconstruction",
    "{subject} dinosaur, close-up head portrait, {env}, accurate scale texture, museum quality",
    "{subject} dinosaur, walking through habitat, {env}, BBC Earth wildlife documentary style",
    "{subject} dinosaur, grazing or foraging, {env}, golden hour sunlight, National Geographic",
    "{subject} dinosaur, herd group behavior, wide landscape shot, {env}, cinematic aerial view",
    "{subject} dinosaur, resting near water, {env}, misty atmosphere, nature documentary",
    "{subject} dinosaur, low angle shot showing full scale, {env}, dramatic sky, epic scene",
    "{subject} dinosaur, realistic fossil skeleton museum exhibit, dramatic lighting, educational",
    "{subject} dinosaur, mother protecting nest, {env}, warm natural light, documentary",
    "{subject} dinosaur, accurate size comparison with prehistoric trees, {env}, cinematic",
]

_DINO_ENVIRONMENTS = [
    "Late Cretaceous floodplain, cycad palms, ancient flowering plants, dense fern undergrowth",
    "Jurassic conifer forest, giant sequoias, ginkgo trees, fern ground cover",
    "Cretaceous coastal wetland, mangrove-like trees, shallow river delta, morning mist",
    "Late Cretaceous open plains, scattered conifers, storm clouds on horizon",
    "Jurassic riverbank, dense tropical vegetation, warm amber sunlight",
    "Cretaceous highland forest, moss-covered rocks, shafts of light through canopy",
]

_DINO_NEGATIVE_PROMPT = (
    "fantasy, alien, cartoon, anime, unrealistic proportions, science fiction, "
    "monster, scary horror, dragon wings unless accurate, feathers only if scientifically proven, "
    "neon colors, glowing eyes, oversized teeth beyond anatomy, human clothing"
)

_HISTORY_NEGATIVE_PROMPT = (
    "people, person, human face, portrait, close-up face, soldier portrait, king portrait, "
    "crowd, modern people, contemporary, cartoon, anime, fantasy, "
    "text overlay, watermark, logo"
)


def _build_dino_prompt(subject: str, scene_index: int) -> str:
    """공룡 채널용 씬별 과학적 정확도 기반 프롬프트 생성."""
    template = _DINO_SCENE_TEMPLATES[scene_index % len(_DINO_SCENE_TEMPLATES)]
    env = random.choice(_DINO_ENVIRONMENTS)
    prompt = template.format(subject=subject, env=env)
    return f"{prompt}, scientifically accurate, photorealistic, ultra detailed, 4K"


def _fetch_pexels_history(
    query: str,
    output_dir: str,
    count: int = 5,
) -> list[str]:
    """역사 채널용 Pexels 이미지 수집 (인물/얼굴 없는 유적·유물·지도·건축 위주)."""
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key or api_key == "your_pexels_api_key":
        logger.warning("PEXELS_API_KEY 미설정 — Pexels 이미지 건너뜀")
        return []

    headers = {"Authorization": api_key}
    # 인물·얼굴이 나오지 않도록 유적·유물·지도·건축·문서 키워드만 사용
    search_queries = [
        f"{query} ancient ruins architecture",
        f"{query} historical artifact museum",
        "ancient ruins stone architecture landscape",
        "historical map document parchment",
        "ancient temple ruins archaeology",
        "medieval castle fortress architecture",
        "ancient artifact pottery sculpture museum",
    ]

    image_paths = []
    used_ids = set()

    for sq in search_queries:
        if len(image_paths) >= count:
            break
        try:
            resp = requests.get(
                PEXELS_API_URL,
                headers=headers,
                params={"query": sq, "per_page": 5, "orientation": "landscape"},
                timeout=15,
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
            for photo in photos:
                if len(image_paths) >= count:
                    break
                if photo["id"] in used_ids:
                    continue
                used_ids.add(photo["id"])
                img_url = photo["src"]["landscape"]
                img_resp = requests.get(img_url, timeout=30)
                img_resp.raise_for_status()
                img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
                img = img.resize((1920, 1080), Image.LANCZOS)
                img_path = os.path.join(output_dir, f"pexels_{photo['id']}.png")
                img.save(img_path, "PNG")
                image_paths.append(img_path)
                logger.info(f"Pexels 역사 이미지 저장: {img_path}")
        except Exception as e:
            logger.warning(f"Pexels 역사 검색 실패 ({sq}): {e}")

    logger.info(f"Pexels 역사 이미지 {len(image_paths)}장 수집 완료")
    return image_paths


def _fetch_pexels_images(
    query: str,
    output_dir: str,
    count: int = 5,
) -> list[str]:
    """Pexels에서 공룡 관련 실사 이미지를 검색·다운로드한다."""
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key or api_key == "your_pexels_api_key":
        logger.warning("PEXELS_API_KEY 미설정 — Pexels 이미지 건너뜀")
        return []

    headers = {"Authorization": api_key}
    # 실제 공룡 관련 콘텐츠만 검색 (화석·박물관·발굴)
    search_queries = [
        f"{query} dinosaur fossil museum",
        f"{query} dinosaur skeleton exhibit",
        "dinosaur fossil skeleton natural history museum",
        "dinosaur bones paleontology museum exhibit",
        "prehistoric dinosaur fossil excavation",
    ]

    image_paths = []
    used_ids = set()

    for sq in search_queries:
        if len(image_paths) >= count:
            break
        try:
            resp = requests.get(
                PEXELS_API_URL,
                headers=headers,
                params={"query": sq, "per_page": 5, "orientation": "landscape"},
                timeout=15,
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
            for photo in photos:
                if len(image_paths) >= count:
                    break
                if photo["id"] in used_ids:
                    continue
                used_ids.add(photo["id"])
                img_url = photo["src"]["landscape"]
                img_resp = requests.get(img_url, timeout=30)
                img_resp.raise_for_status()

                # 1920×1080으로 리사이즈
                img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
                img = img.resize((1920, 1080), Image.LANCZOS)

                img_path = os.path.join(output_dir, f"pexels_{photo['id']}.png")
                img.save(img_path, "PNG")
                image_paths.append(img_path)
                logger.info(f"Pexels 이미지 저장: {img_path}")
        except Exception as e:
            logger.warning(f"Pexels 검색 실패 ({sq}): {e}")

    logger.info(f"Pexels 이미지 {len(image_paths)}장 수집 완료")
    return image_paths


def _interleave(ai_paths: list[str], pexels_paths: list[str]) -> list[str]:
    """AI 이미지 사이에 Pexels 이미지를 균등 간격으로 삽입한다."""
    if not pexels_paths:
        return ai_paths
    result = list(ai_paths)
    # AI 이미지 N장당 Pexels 1장 균등 삽입
    interval = max(1, len(result) // len(pexels_paths))
    for i, p in enumerate(pexels_paths):
        insert_at = min(interval * (i + 1), len(result))
        result.insert(insert_at, p)
    return result


def generate_images(
    subject: str,
    output_dir: str,
    count: int = 30,
    style: str = "",
    channel: str = "",
    pexels_count: int = 5,
) -> list[str]:
    """HuggingFace API로 이미지를 생성하고, dino 채널은 Pexels 실사 이미지를 혼합한다."""
    token = os.environ["HF_API_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    is_dino = (channel == "dino")
    is_history = (channel == "history")

    # Pexels 이미지 먼저 수집 (dino·history 채널)
    pexels_paths: list[str] = []
    if is_dino or is_history:
        pexels_queries = None
        if is_history:
            pexels_paths = _fetch_pexels_history(subject, output_dir, count=pexels_count)
        else:
            pexels_paths = _fetch_pexels_images(subject, output_dir, count=pexels_count)

    # AI 이미지 생성
    ai_count = count - len(pexels_paths)
    image_paths = []
    hf_consecutive_failures = 0

    for i in range(ai_count):
        if is_dino:
            prompt = _build_dino_prompt(subject, i)
        else:
            base_style = style or (
                "photorealistic BBC nature documentary style, "
                "dramatic cinematic lighting, ultra detailed, 4K"
            )
            prompt = f"{subject}, {base_style}"

        logger.info(f"이미지 생성 {i + 1}/{ai_count}: {prompt[:80]}...")

        success = False
        for attempt in range(2):
            try:
                payload: dict = {"inputs": prompt}
                if is_dino:
                    payload["parameters"] = {"negative_prompt": _DINO_NEGATIVE_PROMPT}
                elif is_history:
                    payload["parameters"] = {"negative_prompt": _HISTORY_NEGATIVE_PROMPT}
                response = requests.post(
                    HF_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                if response.status_code == 503:
                    wait = response.json().get("estimated_time", 30)
                    logger.info(f"모델 로딩 중, {wait}초 대기...")
                    time.sleep(min(wait, 60))
                    continue
                # 429: 한도 초과 → 즉시 폴백
                if response.status_code == 429:
                    logger.warning("HuggingFace API 한도 초과 (429) — Pexels only 폴백")
                    hf_consecutive_failures = 999
                    break
                response.raise_for_status()

                img = Image.open(io.BytesIO(response.content))
                img_path = os.path.join(output_dir, f"img_{i:03d}.png")
                img.save(img_path)
                image_paths.append(img_path)
                logger.info(f"이미지 저장: {img_path}")
                hf_consecutive_failures = 0
                success = True
                break
            except Exception as e:
                logger.warning(f"이미지 생성 실패 (시도 {attempt + 1}): {e}")
                if attempt == 1:
                    hf_consecutive_failures += 1
                    logger.error(f"이미지 {i + 1} 생성 최종 실패, 건너뜀")
                time.sleep(5)

        # 연속 3회 실패 시 HF API 포기 → Pexels only 폴백
        if not success and hf_consecutive_failures >= 3:
            logger.warning("HuggingFace 연속 3회 실패 — Pexels only 폴백 전환")
            break

        if success:
            time.sleep(2)

    # Pexels only 폴백: AI 이미지 부족분을 Pexels로 채움
    total_needed = count
    total_have = len(image_paths) + len(pexels_paths)
    if total_have < total_needed and (is_dino or is_history):
        shortage = total_needed - total_have
        logger.info(f"Pexels 추가 수집 ({shortage}장 부족)...")
        fetch_fn = _fetch_pexels_history if is_history else _fetch_pexels_images
        extra = fetch_fn(subject, output_dir, count=shortage + 5)
        # 이미 받은 것과 중복 제거
        existing = set(pexels_paths)
        extra = [p for p in extra if p not in existing]
        pexels_paths.extend(extra[:shortage])

    # 그래도 부족하면 Pexels 이미지 반복 사용
    all_available = image_paths + pexels_paths
    if len(all_available) < total_needed and all_available:
        logger.warning(f"이미지 부족 ({len(all_available)}/{total_needed}) — 반복 사용")
        while len(all_available) < total_needed:
            all_available.extend(all_available[:total_needed - len(all_available)])

    if not all_available:
        raise RuntimeError("이미지를 하나도 생성하지 못했습니다.")

    # Pexels 이미지를 AI 이미지 사이에 균등 삽입
    final_paths = _interleave(image_paths, pexels_paths)
    logger.info(f"총 {len(final_paths)}장 (AI: {len(image_paths)}, Pexels: {len(pexels_paths)})")
    return final_paths
