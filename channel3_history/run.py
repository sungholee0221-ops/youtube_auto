"""
채널 3 · 역사이야기 자동화 (소스폴더 기반)

영상 구조:
  오프닝(원본음성, ~5초)
  + 이미지 슬라이드쇼(15분, 끝 3초 페이드아웃)
  + 검은화면(50분)
  = 총 65분

오디오 구조:
  오프닝 원본음성
  → 씬1 TTS → 무음(5s) → 씬2 TTS → 무음(5s) → ...
  → 무음 패딩 (슬라이드쇼+검은화면 총 길이까지)

이미지 표시 시간 = 씬 TTS 실측 길이 + pause_sec → 완벽한 싱크

환경변수:
  HISTORY_SLIDESHOW_DURATION  슬라이드쇼 최소 길이(초), 기본 900 (15분)
  HISTORY_BLACK_DURATION      검은화면 길이(초), 기본 3000 (50분)
  HISTORY_FADEOUT_SEC         슬라이드쇼 끝 페이드아웃(초), 기본 3
  HISTORY_SCENE_PAUSE         씬 사이 무음(초), 기본 3
  HISTORY_SENTENCE_PAUSE_MS  문장 끝 pause(ms), 기본 1000
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

SOURCE_DIR    = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "channel3_source")
OUTPUT_DIR    = os.environ.get("OUTPUT_DIR_HISTORY", "/Users/sungho/youtube_auto/b4_upload")
SLIDESHOW_DUR      = int(os.environ.get("HISTORY_SLIDESHOW_DURATION", "900"))   # 15분
BLACK_DUR          = int(os.environ.get("HISTORY_BLACK_DURATION", "3000"))      # 50분
FADEOUT_SEC        = int(os.environ.get("HISTORY_FADEOUT_SEC", "3"))
SCENE_PAUSE        = float(os.environ.get("HISTORY_SCENE_PAUSE", "3"))           # 씬 사이 무음
SENTENCE_PAUSE_MS  = int(os.environ.get("HISTORY_SENTENCE_PAUSE_MS", "1000"))    # 문장 끝 pause


def _load_source(folder_path: str) -> tuple[list[str], list[str]]:
    """JSON 읽기 → (씬별 나레이션 목록, 이미지 경로 목록)"""
    json_files = list(Path(folder_path).glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"JSON 파일 없음: {folder_path}")

    data   = load_source_json(str(json_files[0]))
    scenes = data["scenes"]

    scene_texts = [s["narration_kr"] for s in scenes]

    png_files = list(Path(folder_path).glob("*.png"))

    def _scene_key(p: Path) -> int:
        m = re.search(r"_S(\d+)[_.]", p.name, re.IGNORECASE)
        return int(m.group(1)) if m else 999

    image_paths = [str(p) for p in sorted(png_files, key=_scene_key)]
    return scene_texts, image_paths


def main():
    setup_logging("channel3_history")
    logger.info("=== 채널 3 (역사이야기) 실행 시작 ===")
    logger.info(f"구조: 오프닝 + 슬라이드쇼 {SLIDESHOW_DUR}s + 검은화면 {BLACK_DUR}s")

    week = get_next_week("history")
    if not week:
        logger.warning("사용 가능한 주차가 없습니다.")
        return

    week_num    = week["week_num"]
    folder_name = week["folder_name"]
    title_kr    = week["title_kr"]
    week_id     = week["id"]
    logger.info(f"{week_num}주차: {title_kr} (folder={folder_name})")

    folder_path  = os.path.join(SOURCE_DIR, folder_name)
    opening_path = os.path.join(SOURCE_DIR, "history_opening.mp4")

    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"소스 폴더 없음: {folder_path}")
    if not os.path.exists(opening_path):
        raise FileNotFoundError(f"오프닝 영상 없음: {opening_path}")

    tmp_dir       = tempfile.mkdtemp(prefix="history_")
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
        n_img = len(image_paths)
        if n_img < len(scene_texts):
            logger.warning(f"이미지({n_img}) < 씬({len(scene_texts)}), 마지막 이미지 재사용")
            image_paths = image_paths + [image_paths[-1]] * (len(scene_texts) - n_img)

        # 씬별 TTS 개별 생성
        logger.info(f"씬별 TTS 생성 중 (scene_pause={SCENE_PAUSE}s, sentence_pause={SENTENCE_PAUSE_MS}ms)...")
        scene_results = synthesize_scenes(
            scene_texts, tmp_scene_dir,
            channel="history",
            sentence_pause_ms=SENTENCE_PAUSE_MS,
        )

        scene_audio_paths = [r[0] for r in scene_results]
        scene_durations   = [r[1] for r in scene_results]

        # 이미지 표시 시간 = 씬 TTS 길이 + pause
        image_durations = [round(d + SCENE_PAUSE) for d in scene_durations]

        tts_total = sum(scene_durations) + SCENE_PAUSE * len(scene_durations)
        logger.info(f"TTS 합계: {sum(scene_durations):.1f}s + pause = {tts_total:.1f}s")

        # 슬라이드쇼 길이 = max(TTS 합계, 목표 15분)
        slideshow_dur = max(round(tts_total), SLIDESHOW_DUR)

        # TTS 합계가 목표보다 짧으면 마지막 이미지 연장
        total_img = sum(image_durations)
        if total_img < slideshow_dur:
            pad = slideshow_dur - total_img
            image_durations[-1] += pad
            logger.info(f"목표 미달로 마지막 씬 +{pad}s 연장 → {sum(image_durations)}s")

        logger.info(f"슬라이드쇼: {sum(image_durations)}s, 이미지 표시 시간: {image_durations}")

        # 씬 오디오 이어붙이기 (씬 사이 무음 포함)
        logger.info("씬 오디오 이어붙이기...")
        build_scene_audio(scene_audio_paths, SCENE_PAUSE, tmp_audio)

        logger.info("영상 합성 시작...")
        create_channel_video(
            opening_path=opening_path,
            image_list=image_paths,
            audio_path=tmp_audio,
            output_path=tmp_video,
            image_durations=image_durations,
            fadeout_sec=FADEOUT_SEC,
            black_screen_sec=BLACK_DUR,
            transition_sec=2,
        )

        capture_thumbnail(tmp_video, tmp_thumb)
        add_thumbnail_overlay(tmp_thumb, tmp_thumb, channel="history", top_text=title_kr)

        logger.info("제목/설명 생성 중...")
        meta = generate_title_description(
            f"'{title_kr}'에 대한 유튜브 역사 다큐 영상의 제목, 설명, SEO 태그를 한국어로 만들어줘.\n"
            "수면 유도에 적합한 차분하고 교육적인 BBC 다큐멘터리 분위기.\n"
            "태그는 검색 최적화를 위해 30개 생성해줘.\n"
            'JSON 형식으로만 답해줘: {"title": "...", "description": "...", "tags": ["태그1","태그2",...]}'
        )
        title       = meta["title"]
        description = meta["description"]
        tags        = meta.get("tags", [])
        logger.info(f"생성된 제목: {title}")

        total_dur      = sum(image_durations) + BLACK_DUR
        duration_label = f"{max(1, total_dur // 60)}min"
        result = save_output(
            video_path=tmp_video,
            title=title,
            description=description,
            output_dir=OUTPUT_DIR,
            channel="history",
            topic=title_kr,
            duration_label=duration_label,
            tags=tags,
            thumbnail_path=tmp_thumb,
        )
        logger.info(f"저장 완료: {result}")

        mark_week_used(week_id)

    except Exception as e:
        logger.error(f"채널 3 실행 실패: {e}", exc_info=True)
        raise
    finally:
        cleanup_temp(tmp_dir)

    logger.info("=== 채널 3 (역사이야기) 실행 완료 ===")


if __name__ == "__main__":
    main()
