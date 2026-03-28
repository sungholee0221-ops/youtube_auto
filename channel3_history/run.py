"""
채널 3 · 역사이야기 자동화
- 매주 1회 실행
- Supabase에서 카테고리 순환 선택 (한국사/세계사/인물/전쟁/문명)
- Claude API로 주제 선정 → 2시간 분량 스크립트 생성
- 병렬: Google TTS Long Audio + HuggingFace 이미지 + 배경음악
- FFmpeg으로 영상 + 음성 + 배경음 믹싱
- Claude API로 제목/설명/태그 생성
- 로컬 저장 (mp4 + txt)

⚠️ 채널 1, 2 완성 후 구현 예정 (현재 미완성 상태)
"""

import os
import sys
import tempfile
import logging
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.file_utils import setup_logging, save_output, cleanup_temp
from shared.supabase_client import get_next_category, update_category_used
from shared.claude_api import generate_topic, generate_script, generate_title_description
from shared.tts import synthesize_speech
from shared.image_gen import generate_images
from shared.ffmpeg_utils import images_to_video, mix_audio

logger = logging.getLogger(__name__)

OUTPUT_DIR = os.environ.get("OUTPUT_DIR_HISTORY", "/Users/sungho/.n8n-files/역사채널")
BGM_PATH = os.environ.get("BGM_PATH", "")
IMAGE_COUNT = int(os.environ.get("HISTORY_IMAGE_COUNT", "60"))


def main():
    setup_logging("channel3_history")
    logger.info("=== 채널 3 (역사이야기) 실행 시작 ===")

    # 1. 카테고리 순환 선택
    category = get_next_category("history_categories")
    if not category:
        logger.warning("사용 가능한 카테고리가 없습니다.")
        return

    cat_name = category["category_name"]
    cat_id = category["id"]
    logger.info(f"카테고리: {cat_name} (id={cat_id})")

    tmp_dir = tempfile.mkdtemp(prefix="history_")
    tmp_audio = os.path.join(tmp_dir, "narration.mp3")
    tmp_img_dir = os.path.join(tmp_dir, "images")
    tmp_video_raw = os.path.join(tmp_dir, "raw.mp4")
    tmp_video = os.path.join(tmp_dir, "output.mp4")

    try:
        # 2. Claude API로 주제 선정
        logger.info("주제 선정 중...")
        topic = generate_topic(
            f"'{cat_name}' 카테고리에서 유튜브 역사 다큐 영상으로 적합한 구체적 주제 1개를 선정해줘.\n"
            "주제명만 한 줄로 답해줘."
        ).strip()
        logger.info(f"선정된 주제: {topic}")

        # 3. Claude API로 2시간 분량 스크립트 생성
        logger.info("2시간 분량 스크립트 생성 중...")
        script = generate_script(
            f"'{topic}'에 대한 2시간 분량 유튜브 역사 다큐 나레이션 스크립트를 한국어로 작성해줘.\n"
            "수면 유도에 적합한 차분하고 낮은 톤으로 작성.\n"
            "순수 나레이션 텍스트만 출력해줘.",
            max_tokens=8192,
        )
        logger.info(f"스크립트 생성 완료: {len(script)}자")

        # 4. 병렬 처리: TTS + 이미지 생성
        logger.info("TTS + 이미지 병렬 생성 시작...")

        image_style = (
            f"{topic}, historical painting style, dramatic cinematic lighting, "
            "detailed illustration, 4K quality, epic historical scene"
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_tts = executor.submit(synthesize_speech, script, tmp_audio)
            future_img = executor.submit(
                generate_images, topic, tmp_img_dir,
                count=IMAGE_COUNT, style=image_style,
            )

            audio_path = future_tts.result()
            image_paths = future_img.result()

        logger.info(f"TTS 완료: {audio_path}")
        logger.info(f"이미지 {len(image_paths)}장 생성 완료")

        # 5. FFmpeg 이미지+음성 합성
        logger.info("영상 합성 시작...")
        images_to_video(image_paths, audio_path, tmp_video_raw, seconds_per_image=10)

        # 6. 배경음악 믹싱
        if BGM_PATH and os.path.exists(BGM_PATH):
            logger.info("배경음악 믹싱 시작...")
            mix_audio(tmp_video_raw, BGM_PATH, tmp_video, bgm_volume=0.15)
        else:
            logger.warning("배경음악 파일 없음, 음성만 사용")
            tmp_video = tmp_video_raw

        # 7. Claude API로 제목/설명 생성
        logger.info("제목/설명 생성 중...")
        meta = generate_title_description(
            f"'{topic}'에 대한 유튜브 역사 다큐 영상의 제목과 설명을 한국어로 만들어줘.\n"
            "수면 유도에 적합한 차분한 분위기를 반영해줘.\n"
            "태그도 5개 포함해줘.\n"
            'JSON 형식으로만 답해줘: {"title": "...", "description": "...", "tags": [...]}'
        )
        title = meta["title"]
        description = meta["description"]
        tags = meta.get("tags", [])
        if tags:
            description += "\n\n태그: " + ", ".join(f"#{t}" for t in tags)
        logger.info(f"생성된 제목: {title}")

        # 8. 로컬 저장
        result = save_output(
            video_path=tmp_video,
            title=title,
            description=description,
            output_dir=OUTPUT_DIR,
        )
        logger.info(f"저장 완료: {result}")

        # 9. Supabase 카테고리 업데이트
        update_category_used("history_categories", cat_id)

    except Exception as e:
        logger.error(f"채널 3 실행 실패: {e}", exc_info=True)
        raise
    finally:
        cleanup_temp(tmp_dir)

    logger.info("=== 채널 3 (역사이야기) 실행 완료 ===")


if __name__ == "__main__":
    main()
