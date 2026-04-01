"""
채널 3 · 역사이야기 자동화 (소스폴더 기반)

파이프라인:
1. Supabase weekly_schedule에서 다음 미사용 주차 조회
2. channel3_source/{folder}/script.json 읽기 → TTS 생성
3. 씬별 이미지(PNG) + 오프닝 영상 로드
4. TTS 실제 길이 측정 → 목표 길이(15분)와 비교하여 이미지 표시 시간 계산
5. FFmpeg: 오프닝(5초) + 이미지 슬라이드쇼 + TTS 합성 (부족분은 무음 패딩)
6. Claude API로 제목/설명/태그 생성
7. b4_upload/ 저장 + Supabase 업데이트

환경변수:
  HISTORY_TARGET_DURATION  슬라이드쇼 목표 길이(초), 기본 900 (15분)
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
from shared.tts import synthesize_speech
from shared.ffmpeg_utils import create_channel_video, capture_thumbnail, probe_duration
from shared.thumbnail import add_thumbnail_overlay

logger = logging.getLogger(__name__)

SOURCE_DIR      = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "channel3_source")
OUTPUT_DIR      = os.environ.get("OUTPUT_DIR_HISTORY", "/Users/sungho/youtube_auto/b4_upload")
TARGET_DURATION = int(os.environ.get("HISTORY_TARGET_DURATION", "900"))  # 15분


def _load_source(folder_path: str) -> tuple[str, list[str], list[int]]:
    """JSON 읽기 → (나레이션 텍스트, 이미지 경로 목록, 씬별 나레이션 글자수)

    JSON에 포함된 Perplexity 인용 링크는 load_source_json()이 자동 제거한다.
    """
    json_files = list(Path(folder_path).glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"JSON 파일 없음: {folder_path}")

    data   = load_source_json(str(json_files[0]))
    scenes = data["scenes"]

    narration   = "\n\n".join(s["narration_kr"] for s in scenes)
    char_counts = [max(1, len(s["narration_kr"])) for s in scenes]

    # 이미지 파일 S번호 순 정렬
    png_files = list(Path(folder_path).glob("*.png"))

    def _scene_key(p: Path) -> int:
        m = re.search(r"_S(\d+)[_.]", p.name, re.IGNORECASE)
        return int(m.group(1)) if m else 999

    image_paths = [str(p) for p in sorted(png_files, key=_scene_key)]

    return narration, image_paths, char_counts


def _compute_durations(char_counts: list[int], n_images: int, total_sec: int) -> list[int]:
    """씬별 글자수 비율로 이미지 표시 시간(초)을 계산한다."""
    if n_images >= len(char_counts):
        weights = char_counts + [0] * (n_images - len(char_counts))
    else:
        weights = list(char_counts[:n_images])
        for c in char_counts[n_images:]:
            weights[-1] += c

    total_chars = sum(weights) or 1
    durations = [max(1, round(total_sec * w / total_chars)) for w in weights]

    diff = total_sec - sum(durations)
    durations[-1] = max(1, durations[-1] + diff)

    return durations


def main():
    setup_logging("channel3_history")
    logger.info("=== 채널 3 (역사이야기) 실행 시작 ===")

    # 1. Supabase에서 다음 주차 조회
    week = get_next_week("history")
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
    opening_path = os.path.join(SOURCE_DIR, "history_opening.mp4")

    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"소스 폴더 없음: {folder_path}")
    if not os.path.exists(opening_path):
        raise FileNotFoundError(f"오프닝 영상 없음: {opening_path}")

    tmp_dir   = tempfile.mkdtemp(prefix="history_")
    tmp_audio = os.path.join(tmp_dir, "narration.mp3")
    tmp_video = os.path.join(tmp_dir, "output.mp4")
    tmp_thumb = os.path.join(tmp_dir, "thumb.jpg")

    try:
        # 3. 소스 JSON 로드
        logger.info("소스 JSON 로드 중...")
        narration, image_paths, char_counts = _load_source(folder_path)
        logger.info(f"나레이션: {len(narration)}자, 이미지: {len(image_paths)}장")

        if not image_paths:
            raise FileNotFoundError(f"PNG 이미지 없음: {folder_path}")

        # 4. TTS 생성 (history 채널 목소리: Wavenet-D, 느리고 낮은 톤)
        logger.info("TTS 생성 중...")
        synthesize_speech(narration, tmp_audio, channel="history")

        # 5. TTS 실제 길이 측정 → 목표 길이와 비교
        tts_dur   = probe_duration(tmp_audio)
        total_dur = max(round(tts_dur), TARGET_DURATION)
        logger.info(f"TTS: {tts_dur:.1f}s / 목표: {TARGET_DURATION}s → 슬라이드쇼: {total_dur}s")

        # 6. 이미지별 표시 시간 계산 (씬 글자수 비율 배분)
        durations = _compute_durations(char_counts, len(image_paths), total_dur)
        logger.info(f"이미지 표시 시간(초): {durations}")

        # 7. FFmpeg: 오프닝 + 슬라이드쇼 + TTS (부족분은 무음 패딩)
        logger.info("영상 합성 시작...")
        create_channel_video(
            opening_path=opening_path,
            image_list=image_paths,
            audio_path=tmp_audio,
            output_path=tmp_video,
            image_durations=durations,
        )

        # 8. 썸네일
        capture_thumbnail(tmp_video, tmp_thumb)
        add_thumbnail_overlay(tmp_thumb, tmp_thumb, channel="history", top_text=title_kr)

        # 9. Claude: 제목/설명/태그
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

        # 10. 저장
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

        # 11. Supabase 주차 업데이트
        mark_week_used(week_id)

    except Exception as e:
        logger.error(f"채널 3 실행 실패: {e}", exc_info=True)
        raise
    finally:
        cleanup_temp(tmp_dir)

    logger.info("=== 채널 3 (역사이야기) 실행 완료 ===")


if __name__ == "__main__":
    main()
