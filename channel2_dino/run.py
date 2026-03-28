"""
채널 2 · 공룡이야기 자동화
- 매주 금요일 실행
- Supabase에서 미사용 공룡 주제 1개 조회
- Claude API로 10분 나레이션 스크립트 생성
- 병렬: Google TTS 음성 + HuggingFace 이미지 생성
- FFmpeg으로 이미지+음성 합성 (10분 영상)
- Claude API로 제목/설명 생성
- 로컬 저장 (mp4 + txt)
"""

import os
import sys
import tempfile
import logging
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.file_utils import setup_logging, save_output, cleanup_temp
from shared.supabase_client import get_unused_item, mark_as_used
from shared.claude_api import generate_script, generate_title_description
from shared.tts import synthesize_speech
from shared.image_gen import generate_images
from shared.ffmpeg_utils import images_to_video

logger = logging.getLogger(__name__)

OUTPUT_DIR = os.environ.get("OUTPUT_DIR_DINO", "/Users/sungho/.n8n-files/공룡채널")
IMAGE_COUNT = int(os.environ.get("DINO_IMAGE_COUNT", "30"))


def main():
    setup_logging("channel2_dino")
    logger.info("=== 채널 2 (공룡이야기) 실행 시작 ===")

    # 1. Supabase에서 미사용 공룡 주제 조회
    item = get_unused_item("dinosaur_topics")
    if not item:
        logger.warning("사용 가능한 공룡 주제가 없습니다.")
        return

    topic = item["name"]
    item_id = item["id"]
    logger.info(f"공룡 주제: {topic} (id={item_id})")

    tmp_dir = tempfile.mkdtemp(prefix="dino_")
    tmp_audio = os.path.join(tmp_dir, "narration.mp3")
    tmp_img_dir = os.path.join(tmp_dir, "images")
    tmp_video = os.path.join(tmp_dir, "output.mp4")

    try:
        # 2. Claude API로 스크립트 생성
        logger.info("나레이션 스크립트 생성 중...")
        script = generate_script(
            f"{topic}에 대한 10분 분량 유튜브 나레이션 스크립트를 한국어로 작성해줘.\n"
            "수면 유도에 적합한 차분하고 낮은 톤으로 작성.\n"
            "순수 나레이션 텍스트만 출력해줘 (제목, 안내문 제외)."
        )
        logger.info(f"스크립트 생성 완료: {len(script)}자")

        # 3. 병렬 처리: TTS + 이미지 생성
        logger.info("TTS 음성 + 이미지 병렬 생성 시작...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_tts = executor.submit(synthesize_speech, script, tmp_audio)
            future_img = executor.submit(
                generate_images, topic, tmp_img_dir, count=IMAGE_COUNT
            )

            audio_path = future_tts.result()
            image_paths = future_img.result()

        logger.info(f"TTS 완료: {audio_path}")
        logger.info(f"이미지 {len(image_paths)}장 생성 완료")

        # 4. FFmpeg 이미지+음성 합성
        logger.info("영상 합성 시작...")
        images_to_video(image_paths, audio_path, tmp_video, seconds_per_image=10)

        # 5. Claude API로 제목/설명 생성
        logger.info("제목/설명 생성 중...")
        meta = generate_title_description(
            f"'{topic}'에 대한 유튜브 공룡 다큐멘터리 영상의 제목과 설명을 한국어로 만들어줘.\n"
            "수면 유도에 적합한 차분한 분위기를 반영해줘.\n"
            'JSON 형식으로만 답해줘: {"title": "...", "description": "..."}'
        )
        title = meta["title"]
        description = meta["description"]
        logger.info(f"생성된 제목: {title}")

        # 6. 로컬 저장
        result = save_output(
            video_path=tmp_video,
            title=title,
            description=description,
            output_dir=OUTPUT_DIR,
        )
        logger.info(f"저장 완료: {result}")

        # 7. Supabase 업데이트
        mark_as_used("dinosaur_topics", item_id)

    except Exception as e:
        logger.error(f"채널 2 실행 실패: {e}", exc_info=True)
        raise
    finally:
        cleanup_temp(tmp_dir)

    logger.info("=== 채널 2 (공룡이야기) 실행 완료 ===")


if __name__ == "__main__":
    main()
