"""
채널 2 · 공룡이야기 자동화 (소스폴더 기반)

파이프라인:
1. Supabase weekly_schedule에서 다음 미사용 주차 조회
2. channel2_source/{folder}/script.json 읽기 → TTS 생성
3. 씬별 이미지(PNG) + 오프닝 영상 로드
4. FFmpeg: 오프닝(5초) + 이미지 슬라이드쇼 + TTS 합성
5. Claude API로 제목/설명/태그 생성
6. b4_upload/ 저장 + Supabase 업데이트
"""

import os
import re
import sys
import json
import tempfile
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.file_utils import setup_logging, save_output, cleanup_temp
from shared.supabase_client import get_next_week, mark_week_used
from shared.claude_api import generate_title_description
from shared.tts import synthesize_speech
from shared.ffmpeg_utils import create_channel_video, capture_thumbnail
from shared.thumbnail import add_thumbnail_overlay

logger = logging.getLogger(__name__)

SOURCE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "channel2_source")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR_DINO", "/Users/sungho/youtube_auto/b4_upload")


def _load_source(folder_path: str) -> tuple[str, list[str], list[int]]:
    """JSON 읽기 → (나레이션 텍스트, 이미지 경로 목록, 씬별 duration 목록)"""
    json_files = list(Path(folder_path).glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"JSON 파일 없음: {folder_path}")

    with open(json_files[0], "r", encoding="utf-8") as f:
        data = json.load(f)

    scenes = data["scenes"]

    # 나레이션 이어붙이기
    narration = "\n\n".join(s["narration_kr"] for s in scenes)

    # 이미지 파일 S번호 순 정렬
    png_files = list(Path(folder_path).glob("*.png"))

    def _scene_key(p: Path) -> int:
        m = re.search(r"_S(\d+)_", p.name, re.IGNORECASE)
        return int(m.group(1)) if m else 999

    image_paths = [str(p) for p in sorted(png_files, key=_scene_key)]

    # 씬별 duration (없으면 10초 기본값)
    durations = [int(s.get("duration_sec", 10)) for s in scenes]

    return narration, image_paths, durations


def main():
    setup_logging("channel2_dino")
    logger.info("=== 채널 2 (공룡이야기) 실행 시작 ===")

    # 1. Supabase에서 다음 주차 조회
    week = get_next_week("dino")
    if not week:
        logger.warning("사용 가능한 주차가 없습니다. (weekly_schedule 테이블 확인)")
        return

    week_num    = week["week_num"]
    folder_name = week["folder_name"]
    title_kr    = week["title_kr"]
    week_id     = week["id"]
    logger.info(f"{week_num}주차: {title_kr} (folder={folder_name})")

    # 2. 소스 경로 확인
    folder_path  = os.path.join(SOURCE_DIR, folder_name)
    opening_path = os.path.join(SOURCE_DIR, "dino_opening.mp4")

    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"소스 폴더 없음: {folder_path}")
    if not os.path.exists(opening_path):
        raise FileNotFoundError(f"오프닝 영상 없음: {opening_path}")

    tmp_dir   = tempfile.mkdtemp(prefix="dino_")
    tmp_audio = os.path.join(tmp_dir, "narration.mp3")
    tmp_video = os.path.join(tmp_dir, "output.mp4")
    tmp_thumb = os.path.join(tmp_dir, "thumb.jpg")

    try:
        # 3. 소스 JSON 로드
        logger.info("소스 JSON 로드 중...")
        narration, image_paths, durations = _load_source(folder_path)
        logger.info(f"나레이션: {len(narration)}자, 이미지: {len(image_paths)}장")

        if not image_paths:
            raise FileNotFoundError(f"PNG 이미지 없음: {folder_path}")

        # 4. TTS 생성
        logger.info("TTS 생성 중...")
        synthesize_speech(narration, tmp_audio, channel="dino")
        logger.info(f"TTS 완료: {tmp_audio}")

        # 5. FFmpeg: 오프닝 + 슬라이드쇼 + TTS
        logger.info("영상 합성 시작...")
        create_channel_video(
            opening_path=opening_path,
            image_list=image_paths,
            audio_path=tmp_audio,
            output_path=tmp_video,
            image_durations=durations,
        )

        # 6. 썸네일
        capture_thumbnail(tmp_video, tmp_thumb)
        add_thumbnail_overlay(tmp_thumb, tmp_thumb, channel="dino", top_text=title_kr)

        # 7. Claude: 제목/설명/태그
        logger.info("제목/설명 생성 중...")
        meta = generate_title_description(
            f"'{title_kr}'에 대한 유튜브 공룡 다큐멘터리 영상의 제목, 설명, SEO 태그를 한국어로 만들어줘.\n"
            "BBC 다큐멘터리 스타일로 어른과 아이 모두 흥미롭게 볼 수 있는 교육적인 분위기.\n"
            "태그는 검색 최적화를 위해 30개 생성해줘.\n"
            'JSON 형식으로만 답해줘: {"title": "...", "description": "...", "tags": ["태그1","태그2",...]}'
        )
        title       = meta["title"]
        description = meta["description"]
        tags        = meta.get("tags", [])
        logger.info(f"생성된 제목: {title}")

        # 8. 저장
        total_sec      = sum(durations)
        duration_label = f"{max(1, total_sec // 60)}min"

        result = save_output(
            video_path=tmp_video,
            title=title,
            description=description,
            output_dir=OUTPUT_DIR,
            channel="dino",
            topic=title_kr,
            duration_label=duration_label,
            tags=tags,
            thumbnail_path=tmp_thumb,
        )
        logger.info(f"저장 완료: {result}")

        # 9. Supabase 주차 업데이트
        mark_week_used(week_id)

    except Exception as e:
        logger.error(f"채널 2 실행 실패: {e}", exc_info=True)
        raise
    finally:
        cleanup_temp(tmp_dir)

    logger.info("=== 채널 2 (공룡이야기) 실행 완료 ===")


if __name__ == "__main__":
    main()
