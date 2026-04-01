"""
채널 2 · 공룡이야기 자동화 (소스폴더 기반)

영상 구조: 오프닝(원본음성) + 이미지 슬라이드쇼 + TTS
- 이미지 표시 시간은 JSON의 duration_sec을 그대로 사용 (씬 싱크 보장)
- TTS가 씬 합계보다 길면 마지막 이미지 표시 시간을 자동 연장
- TTS가 짧으면 해당 씬 이미지가 더 오래 표시됨 (자연스러운 여백)
- 목표 길이: 10분 (JSON 스크립트 기준 1300~1500자 권장)

환경변수:
  DINO_TARGET_DURATION  슬라이드쇼 최소 길이(초), 기본 600 (10분)
"""

import os
import re
import sys
import math
import tempfile
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.file_utils import setup_logging, save_output, cleanup_temp, load_source_json
from shared.supabase_client import get_next_week, mark_week_used
from shared.claude_api import generate_title_description
from shared.tts import synthesize_speech
from shared.ffmpeg_utils import create_channel_video, capture_thumbnail, probe_duration
from shared.thumbnail import add_thumbnail_overlay

logger = logging.getLogger(__name__)

SOURCE_DIR      = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "channel2_source")
OUTPUT_DIR      = os.environ.get("OUTPUT_DIR_DINO", "/Users/sungho/youtube_auto/b4_upload")
TARGET_DURATION = int(os.environ.get("DINO_TARGET_DURATION", "600"))   # 10분


def _load_source(folder_path: str) -> tuple[str, list[str], list[int]]:
    """JSON 읽기 → (나레이션, 이미지 경로 목록, 씬별 duration_sec)"""
    json_files = list(Path(folder_path).glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"JSON 파일 없음: {folder_path}")

    data   = load_source_json(str(json_files[0]))
    scenes = data["scenes"]

    narration = "\n\n".join(s["narration_kr"] for s in scenes)
    # JSON에 명시된 duration_sec 사용 (씬 싱크 기준값)
    durations = [int(s.get("duration_sec", 10)) for s in scenes]

    png_files = list(Path(folder_path).glob("*.png"))

    def _scene_key(p: Path) -> int:
        m = re.search(r"_S(\d+)[_.]", p.name, re.IGNORECASE)
        return int(m.group(1)) if m else 999

    image_paths = [str(p) for p in sorted(png_files, key=_scene_key)]
    return narration, image_paths, durations


def main():
    setup_logging("channel2_dino")
    logger.info("=== 채널 2 (공룡이야기) 실행 시작 ===")

    week = get_next_week("dino")
    if not week:
        logger.warning("사용 가능한 주차가 없습니다. (weekly_schedule 테이블 확인)")
        return

    week_num    = week["week_num"]
    folder_name = week["folder_name"]
    title_kr    = week["title_kr"]
    week_id     = week["id"]
    logger.info(f"{week_num}주차: {title_kr} (folder={folder_name})")

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
        logger.info("소스 JSON 로드 중...")
        narration, image_paths, durations = _load_source(folder_path)
        logger.info(f"나레이션: {len(narration)}자, 이미지: {len(image_paths)}장, "
                    f"씬 duration 합: {sum(durations)}s")

        if not image_paths:
            raise FileNotFoundError(f"PNG 이미지 없음: {folder_path}")

        # 이미지 수와 씬 수가 다를 때 durations 맞춤
        n = len(image_paths)
        if len(durations) > n:
            # 씬이 이미지보다 많으면 초과 duration을 마지막 이미지에 누적
            durations = durations[:n]
            for extra in durations[n:]:
                durations[-1] += extra
        elif len(durations) < n:
            # 이미지가 씬보다 많으면 부족분을 기본값 10으로 채움
            durations += [10] * (n - len(durations))

        logger.info("TTS 생성 중...")
        synthesize_speech(narration, tmp_audio, channel="dino")

        # TTS 실제 길이 측정
        tts_dur = probe_duration(tmp_audio)
        sum_dur = sum(durations)
        logger.info(f"TTS: {tts_dur:.1f}s / 씬 합계: {sum_dur}s / 목표: {TARGET_DURATION}s")

        # TTS가 씬 합계보다 길면 마지막 이미지 연장
        if tts_dur > sum_dur:
            extra = math.ceil(tts_dur - sum_dur) + 2   # 여유 2초
            durations[-1] += extra
            logger.info(f"마지막 씬 +{extra}s 연장 → 새 합계: {sum(durations)}s")

        # 목표 길이 미달이면 마지막 이미지 추가 연장
        total_dur = sum(durations)
        if total_dur < TARGET_DURATION:
            pad = TARGET_DURATION - total_dur
            durations[-1] += pad
            logger.info(f"목표 미달로 마지막 씬 +{pad}s 추가 연장 → {sum(durations)}s")

        total_dur = sum(durations)
        logger.info(f"최종 슬라이드쇼 길이: {total_dur}s, 이미지 표시 시간: {durations}")

        logger.info("영상 합성 시작...")
        create_channel_video(
            opening_path=opening_path,
            image_list=image_paths,
            audio_path=tmp_audio,
            output_path=tmp_video,
            image_durations=durations,
            fadeout_sec=0,
            black_screen_sec=0,
        )

        capture_thumbnail(tmp_video, tmp_thumb)
        add_thumbnail_overlay(tmp_thumb, tmp_thumb, channel="dino", top_text=title_kr)

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

        duration_label = f"{max(1, total_dur // 60)}min"
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

        mark_week_used(week_id)

    except Exception as e:
        logger.error(f"채널 2 실행 실패: {e}", exc_info=True)
        raise
    finally:
        cleanup_temp(tmp_dir)

    logger.info("=== 채널 2 (공룡이야기) 실행 완료 ===")


if __name__ == "__main__":
    main()
