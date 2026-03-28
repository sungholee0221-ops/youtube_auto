import os
import glob
import shutil
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def save_output(
    video_path: str,
    title: str,
    description: str,
    output_dir: str,
    thumbnail_path: str | None = None,
) -> dict:
    """완성된 영상과 메타데이터 txt를 출력 디렉토리에 저장한다."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_title = _sanitize_filename(title)
    base_name = f"{date_str}_{safe_title}"

    # mp4 복사
    dst_video = os.path.join(output_dir, f"{base_name}.mp4")
    shutil.copy2(video_path, dst_video)
    logger.info(f"영상 저장: {dst_video}")

    # txt 저장 (제목 + 설명)
    dst_txt = os.path.join(output_dir, f"{base_name}.txt")
    with open(dst_txt, "w", encoding="utf-8") as f:
        f.write(f"제목: {title}\n\n")
        f.write(f"설명:\n{description}\n")
    logger.info(f"메타데이터 저장: {dst_txt}")

    # 썸네일 복사
    dst_thumb = None
    if thumbnail_path and os.path.exists(thumbnail_path):
        dst_thumb = os.path.join(output_dir, f"{base_name}_thumb.jpg")
        shutil.copy2(thumbnail_path, dst_thumb)
        logger.info(f"썸네일 저장: {dst_thumb}")

    return {"video": dst_video, "txt": dst_txt, "thumbnail": dst_thumb}


def cleanup_temp(*paths: str) -> None:
    """임시 파일/디렉토리를 삭제한다."""
    for p in paths:
        if not p:
            continue
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
                logger.info(f"임시 디렉토리 삭제: {p}")
            elif os.path.isfile(p):
                os.remove(p)
                logger.info(f"임시 파일 삭제: {p}")
        except Exception as e:
            logger.warning(f"임시 파일 삭제 실패 ({p}): {e}")


def setup_logging(channel_name: str, log_dir: str = "logs") -> None:
    """채널별 로그 파일을 설정한다."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"{channel_name}_{date_str}.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logger.info(f"로깅 시작: {log_file}")


def _sanitize_filename(name: str, max_len: int = 50) -> str:
    """파일명에 사용할 수 없는 문자를 제거한다."""
    # 파일명 불가 문자 제거
    for ch in r'\/:*?"<>|':
        name = name.replace(ch, "")
    name = name.strip()
    if len(name) > max_len:
        name = name[:max_len]
    return name
