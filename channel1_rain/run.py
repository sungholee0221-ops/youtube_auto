"""
채널 1 · 비소리/모닥불 자동화
- 매주 수요일 자정 실행
- Supabase에서 미사용 비소리 영상 1개 조회
- FFmpeg으로 3시간 루프 영상 생성
- 첫 프레임 썸네일 캡처
- Claude API로 제목/설명 생성
- 로컬 저장 (mp4 + txt)
- Supabase is_used 업데이트
"""

import os
import sys
import tempfile
import logging

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.file_utils import setup_logging, save_output, cleanup_temp
from shared.supabase_client import get_unused_item, mark_as_used
from shared.ffmpeg_utils import loop_video, capture_thumbnail
from shared.claude_api import generate_title_description

logger = logging.getLogger(__name__)

# 테스트 시 60초, 프로덕션 시 10800초 (3시간)
VIDEO_DURATION = int(os.environ.get("VIDEO_DURATION", "10800"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR_RAIN", "/Users/sungho/.n8n-files/비소리채널")


def main():
    setup_logging("channel1_rain")
    logger.info("=== 채널 1 (비소리) 실행 시작 ===")

    # 1. Supabase에서 미사용 파일 조회
    item = get_unused_item("generated_files", "file_type", "rain_video")
    if not item:
        logger.warning("사용 가능한 비소리 영상이 없습니다.")
        return

    source_path = item["file_path"]
    item_id = item["id"]
    logger.info(f"소스 영상: {source_path} (id={item_id})")

    # 임시 파일 경로
    tmp_dir = tempfile.mkdtemp(prefix="rain_")
    tmp_video = os.path.join(tmp_dir, "output.mp4")
    tmp_thumb = os.path.join(tmp_dir, "thumb.jpg")

    try:
        # 2. FFmpeg 루프 영상 생성
        logger.info(f"루프 영상 생성 시작 (duration={VIDEO_DURATION}s)")
        loop_video(source_path, tmp_video, duration=VIDEO_DURATION)

        # 3. 썸네일 캡처
        capture_thumbnail(tmp_video, tmp_thumb)

        # 4. Claude API로 제목/설명 생성
        logger.info("Claude API로 제목/설명 생성 중...")
        meta = generate_title_description(
            "비소리 수면 유도 유튜브 영상의 제목과 설명을 한국어로 만들어줘.\n"
            'JSON 형식으로만 답해줘: {"title": "...", "description": "..."}'
        )
        title = meta["title"]
        description = meta["description"]
        logger.info(f"생성된 제목: {title}")

        # 5. 로컬 저장
        result = save_output(
            video_path=tmp_video,
            title=title,
            description=description,
            output_dir=OUTPUT_DIR,
            thumbnail_path=tmp_thumb,
        )
        logger.info(f"저장 완료: {result}")

        # 6. Supabase 업데이트
        mark_as_used("generated_files", item_id)

    except Exception as e:
        logger.error(f"채널 1 실행 실패: {e}", exc_info=True)
        raise
    finally:
        # 7. 임시 파일 정리
        cleanup_temp(tmp_dir)

    logger.info("=== 채널 1 (비소리) 실행 완료 ===")


if __name__ == "__main__":
    main()
