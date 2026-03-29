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
from shared.ffmpeg_utils import images_to_video, capture_thumbnail
from shared.thumbnail import add_thumbnail_overlay

logger = logging.getLogger(__name__)

OUTPUT_DIR = os.environ.get("OUTPUT_DIR_DINO", "/Users/sungho/youtube_auto/b4_upload")
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
    tmp_thumb = os.path.join(tmp_dir, "thumb.jpg")

    try:
        # 2. Claude API로 스크립트 생성
        logger.info("나레이션 스크립트 생성 중...")
        script = generate_script(
            f"{topic}에 대한 10분 분량 유튜브 나레이션 스크립트를 한국어로 작성해줘.\n"
            "BBC 자연 다큐멘터리 스타일로, 어른과 아이 모두 흥미롭게 들을 수 있도록 생동감 있고 교육적으로 작성해줘.\n"
            "공룡의 생태, 행동, 특징, 발견 역사 등 흥미로운 정보를 풍부하게 담아줘.\n"
            "순수 나레이션 텍스트만 출력해줘 (제목, 안내문 제외)."
        )
        logger.info(f"스크립트 생성 완료: {len(script)}자")

        # 3. 병렬 처리: TTS + 이미지 생성
        logger.info("TTS 음성 + 이미지 병렬 생성 시작...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_tts = executor.submit(synthesize_speech, script, tmp_audio)
            future_img = executor.submit(
                generate_images, topic, tmp_img_dir,
                count=IMAGE_COUNT, channel="dino",
            )

            audio_path = future_tts.result()
            image_paths = future_img.result()

        logger.info(f"TTS 완료: {audio_path}")
        logger.info(f"이미지 {len(image_paths)}장 생성 완료")

        # 4. FFmpeg 이미지+음성 합성
        logger.info("영상 합성 시작...")
        images_to_video(image_paths, audio_path, tmp_video, seconds_per_image=10)

        # 4-1. 썸네일 캡처 + 오버레이
        capture_thumbnail(tmp_video, tmp_thumb)
        add_thumbnail_overlay(tmp_thumb, tmp_thumb, channel="dino", top_text=topic)

        # 5. Claude API로 제목/설명 생성
        logger.info("제목/설명 생성 중...")
        meta = generate_title_description(
            f"'{topic}'에 대한 유튜브 공룡 다큐멘터리 영상의 제목, 설명, SEO 태그를 한국어로 만들어줘.\n"
            "BBC 다큐멘터리 스타일로 어른과 아이 모두 흥미롭게 볼 수 있는 교육적인 분위기로 작성해줘.\n"
            "태그는 검색 최적화를 위해 30개 생성해줘. (예: 공룡,다큐멘터리,교육,BBC스타일,선사시대,백악기,쥐라기,공룡정보,어린이교육,자연다큐,...)\n"
            'JSON 형식으로만 답해줘: {"title": "...", "description": "...", "tags": ["태그1","태그2",...]}'
        )
        title       = meta["title"]
        description = meta["description"]
        tags        = meta.get("tags", [])
        logger.info(f"생성된 제목: {title}")

        # 6. 로컬 저장
        estimated_min = max(1, (IMAGE_COUNT * 10) // 60)
        duration_label = f"{estimated_min}min"

        result = save_output(
            video_path=tmp_video,
            title=title,
            description=description,
            output_dir=OUTPUT_DIR,
            channel="dino",
            topic=topic,
            duration_label=duration_label,
            tags=tags,
            thumbnail_path=tmp_thumb,
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
