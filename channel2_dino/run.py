"""
채널 2 · 공룡이야기 자동화 (소스폴더 기반)

영상 구조: 오프닝(원본음성) + 이미지 슬라이드쇼 + 검은화면(10분 채우기)
오디오 구조: 오프닝 음성 → 씬1 TTS → 무음(3s) → 씬2 TTS → 무음(3s) → ...
             (각 TTS 내부: 문장 끝마다 1초 pause 자동 삽입)

이미지 표시 시간 = 해당 씬 TTS 실측 길이 + scene_pause → 완벽한 싱크
나레이션 끝난 뒤 나머지는 검은화면으로 채워 목표 10분 달성.

환경변수:
  DINO_TARGET_DURATION    총 영상 목표 길이(초), 기본 600 (10분)
  DINO_SCENE_PAUSE        씬 사이 무음(초), 기본 3
  DINO_SENTENCE_PAUSE_MS  문장 끝 pause(ms), 기본 1000
"""

import os
import re
import sys
import tempfile
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.file_utils import setup_logging, save_output, cleanup_temp, load_source_json
from shared.supabase_client import get_next_week, mark_week_used
from shared.claude_api import generate_title_description
from shared.tts import synthesize_scenes
from shared.ffmpeg_utils import create_channel_video, capture_thumbnail, build_scene_audio
from shared.thumbnail import add_thumbnail_overlay

logger = logging.getLogger(__name__)

SOURCE_DIR         = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "channel2_source")
OUTPUT_DIR         = os.environ.get("OUTPUT_DIR_DINO", "/Users/sungho/youtube_auto/b4_upload")
TARGET_DURATION    = int(os.environ.get("DINO_TARGET_DURATION", "600"))       # 10분
SCENE_PAUSE        = float(os.environ.get("DINO_SCENE_PAUSE", "3"))           # 씬 사이 무음
SENTENCE_PAUSE_MS  = int(os.environ.get("DINO_SENTENCE_PAUSE_MS", "1000"))    # 문장 끝 pause


def _load_source(folder_path: str) -> tuple[list[str], list[str]]:
    """JSON 읽기 → (씬별 나레이션 목록, 이미지 경로 목록)"""
    json_files = list(Path(folder_path).glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"JSON 파일 없음: {folder_path}")

    data        = load_source_json(str(json_files[0]))
    scene_texts = [s["narration_kr"] for s in data["scenes"]]

    png_files = list(Path(folder_path).glob("*.png"))

    def _scene_key(p: Path) -> int:
        m = re.search(r"_S(\d+)[_.]", p.name, re.IGNORECASE)
        return int(m.group(1)) if m else 999

    image_paths = [str(p) for p in sorted(png_files, key=_scene_key)]
    return scene_texts, image_paths


def main():
    setup_logging("channel2_dino")
    logger.info("=== 채널 2 (공룡이야기) 실행 시작 ===")

    week = get_next_week("dino")
    if not week:
        logger.warning("사용 가능한 주차가 없습니다.")
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

    tmp_dir       = tempfile.mkdtemp(prefix="dino_")
    tmp_scene_dir = os.path.join(tmp_dir, "scenes")
    tmp_audio     = os.path.join(tmp_dir, "narration.m4a")
    tmp_video     = os.path.join(tmp_dir, "output.mp4")
    tmp_thumb     = os.path.join(tmp_dir, "thumb.jpg")

    try:
        logger.info("소스 JSON 로드 중...")
        scene_texts, image_paths = _load_source(folder_path)
        logger.info(f"씬 수: {len(scene_texts)}, 이미지: {len(image_paths)}장")

        if not image_paths:
            raise FileNotFoundError(f"PNG 이미지 없음: {folder_path}")

        # 이미지가 씬보다 적으면 마지막 이미지 재사용
        if len(image_paths) < len(scene_texts):
            logger.warning(f"이미지({len(image_paths)}) < 씬({len(scene_texts)}), 마지막 이미지 재사용")
            image_paths += [image_paths[-1]] * (len(scene_texts) - len(image_paths))

        # 씬별 TTS (문장 끝 1초 pause 포함)
        logger.info(f"씬별 TTS 생성 중 (scene_pause={SCENE_PAUSE}s, sentence_pause={SENTENCE_PAUSE_MS}ms)...")
        scene_results = synthesize_scenes(
            scene_texts, tmp_scene_dir,
            channel="dino",
            sentence_pause_ms=SENTENCE_PAUSE_MS,
        )

        scene_audio_paths = [r[0] for r in scene_results]
        scene_durations   = [r[1] for r in scene_results]

        # 이미지 표시 시간 = 씬 TTS 실측 + scene_pause
        image_durations = [round(d + SCENE_PAUSE) for d in scene_durations]
        image_durations[0] += 1  # 첫 씬: 오디오 1초 여유에 맞춰 표시 시간 연장
        slideshow_dur   = sum(image_durations)

        # 나레이션 후 남은 시간 → 검은화면
        black_screen_sec = max(0, TARGET_DURATION - slideshow_dur)

        tts_total = sum(scene_durations) + SCENE_PAUSE * len(scene_durations)
        logger.info(f"TTS 합계: {tts_total:.1f}s / 슬라이드쇼: {slideshow_dur}s / 검은화면: {black_screen_sec}s")
        logger.info(f"이미지 표시 시간: {image_durations}")

        # 씬 오디오 이어붙이기
        logger.info("씬 오디오 이어붙이기...")
        build_scene_audio(scene_audio_paths, SCENE_PAUSE, tmp_audio, intro_pause_sec=1)

        logger.info("영상 합성 시작...")
        create_channel_video(
            opening_path=opening_path,
            image_list=image_paths,
            audio_path=tmp_audio,
            output_path=tmp_video,
            image_durations=image_durations,
            fadeout_sec=0,
            black_screen_sec=black_screen_sec,
            transition_sec=2,
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

        total_dur      = slideshow_dur + black_screen_sec
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
