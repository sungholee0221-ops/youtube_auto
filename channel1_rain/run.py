"""
채널 1 · 비소리 자동화
- 매주 수요일 자정 실행
- Supabase generated_files에서 rain_video(영상) + rain_audio(오디오) 각각 조회
- 앞 15분: Pexels 영상 / 나머지: 검은 화면 / 전체: 빗소리 MP3 루프
- 첫 프레임 썸네일 캡처
- Claude API로 제목/설명 생성
- 로컬 저장 (mp4 + txt + thumb)
- Supabase is_used 업데이트 (영상/오디오 독립 순환, 다 쓰면 자동 리셋)
"""

import os
import sys
import tempfile
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.file_utils import setup_logging, save_output, cleanup_temp
from shared.supabase_client import get_unused_item, mark_as_used, reset_used_items
from shared.ffmpeg_utils import create_rain_video, extract_audio, has_audio_track, capture_thumbnail
from shared.claude_api import generate_title_description
from shared.thumbnail import add_thumbnail_overlay

logger = logging.getLogger(__name__)

VIDEO_DURATION  = int(os.environ.get("VIDEO_DURATION", "10800"))   # 전체 길이 (초)
VISUAL_DURATION = int(os.environ.get("VISUAL_DURATION", "900"))    # Pexels 영상 사용 구간 (초, 기본 15분)
OUTPUT_DIR      = os.environ.get("OUTPUT_DIR_RAIN", "/Users/sungho/youtube_auto/b4_upload")


def _fetch_with_reset(file_type: str) -> dict | None:
    """미사용 항목 조회 → 없으면 리셋 후 재조회."""
    item = get_unused_item("generated_files", "file_type", file_type)
    if not item:
        logger.info(f"미사용 {file_type} 없음 → 전체 리셋 후 재순환")
        reset_used_items("generated_files", "file_type", file_type)
        item = get_unused_item("generated_files", "file_type", file_type)
    return item


def main():
    setup_logging("channel1_rain")
    logger.info("=== 채널 1 (비소리) 실행 시작 ===")

    # 1. Supabase에서 영상 조회
    video_item = _fetch_with_reset("rain_video")
    if not video_item:
        logger.error("rain_video가 Supabase에 등록되지 않았습니다.")
        return

    visual_path = video_item["file_path"]
    video_has_audio = has_audio_track(visual_path)
    logger.info(f"영상 소스: {os.path.basename(visual_path)} (오디오내장={video_has_audio})")

    # 오디오 내장 여부에 따라 rain_audio 조회 여부 결정
    audio_item = None
    if not video_has_audio:
        audio_item = _fetch_with_reset("rain_audio")
        if not audio_item:
            logger.error("rain_audio가 Supabase에 등록되지 않았습니다.")
            return
        logger.info(f"오디오 소스: {os.path.basename(audio_item['file_path'])}")

    tmp_dir   = tempfile.mkdtemp(prefix="rain_")
    tmp_video = os.path.join(tmp_dir, "output.mp4")
    tmp_thumb = os.path.join(tmp_dir, "thumb.jpg")

    try:
        # 2. 영상 합성 (공통: 15분 루프 + 검은화면 / 오디오만 소스 다름)
        if video_has_audio:
            # Firefly: 내장 오디오 추출 → 3시간 루프 / 영상은 15분만
            logger.info("오디오 내장 영상 — 오디오 추출 후 공통 합성")
            extracted_audio = os.path.join(tmp_dir, "extracted_audio.m4a")
            extract_audio(visual_path, extracted_audio)
            audio_path = extracted_audio
        else:
            audio_path = audio_item["file_path"]

        logger.info(f"영상 합성 시작 (영상={VISUAL_DURATION}s / 전체={VIDEO_DURATION}s)")
        create_rain_video(visual_path, audio_path, tmp_video, VISUAL_DURATION, VIDEO_DURATION)

        # 3. 썸네일 캡처 + 오버레이
        capture_thumbnail(tmp_video, tmp_thumb)
        hours   = VIDEO_DURATION // 3600
        minutes = (VIDEO_DURATION % 3600) // 60
        duration_str = f"{hours}시간" if hours > 0 else f"{minutes}분"
        add_thumbnail_overlay(tmp_thumb, tmp_thumb, channel="rain", top_text=duration_str)

        # 4. Claude API로 제목/설명 생성
        logger.info("Claude API로 제목/설명 생성 중...")
        meta = generate_title_description(
            f"비소리 수면 유도 유튜브 영상의 제목, 설명, SEO 태그를 한국어로 만들어줘.\n"
            f"영상 길이는 정확히 {duration_str}이야. 제목에 반드시 '{duration_str}'을 포함해줘.\n"
            "태그는 검색 최적화를 위해 30개 생성해줘. (예: 빗소리,수면,명상,자연음,수면유도,명상음악,깊은수면,ASMR,백색소음,힐링,...)\n"
            'JSON 형식으로만 답해줘: {"title": "...", "description": "...", "tags": ["태그1","태그2",...]}'
        )
        title       = meta["title"]
        description = meta["description"]
        tags        = meta.get("tags", [])
        logger.info(f"생성된 제목: {title}")

        # 5. 로컬 저장
        duration_label = f"{hours}h" if hours > 0 else f"{minutes}min"

        result = save_output(
            video_path=tmp_video,
            title=title,
            description=description,
            output_dir=OUTPUT_DIR,
            channel="rain",
            duration_label=duration_label,
            tags=tags,
            thumbnail_path=tmp_thumb,
        )
        logger.info(f"저장 완료: {result}")

        # 6. Supabase 업데이트
        mark_as_used("generated_files", video_item["id"])
        if audio_item:
            mark_as_used("generated_files", audio_item["id"])

    except Exception as e:
        logger.error(f"채널 1 실행 실패: {e}", exc_info=True)
        raise
    finally:
        cleanup_temp(tmp_dir)

    logger.info("=== 채널 1 (비소리) 실행 완료 ===")


if __name__ == "__main__":
    main()
