import os
import subprocess
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

FFMPEG = os.environ.get("FFMPEG_PATH", "/usr/local/bin/ffmpeg")


def _run_ffmpeg(args: list[str], desc: str = "") -> None:
    """FFmpeg 명령을 실행하고 결과를 검증한다."""
    cmd = [FFMPEG] + args
    logger.info(f"FFmpeg 실행 ({desc}): {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"FFmpeg 실패:\n{result.stderr}")
        raise RuntimeError(f"FFmpeg 실패 ({desc}): {result.stderr[:500]}")


def _check_output(path: str, desc: str = "") -> None:
    """출력 파일이 0바이트인지 검사한다."""
    if not os.path.exists(path):
        raise RuntimeError(f"FFmpeg 출력 파일 없음 ({desc}): {path}")
    if os.path.getsize(path) == 0:
        os.remove(path)
        raise RuntimeError(f"FFmpeg 출력 파일 0바이트 ({desc}): {path}")
    logger.info(f"FFmpeg 출력 확인 ({desc}): {path} ({os.path.getsize(path)} bytes)")


def loop_video(input_path: str, output_path: str, duration: int = 10800) -> str:
    """영상을 루프하여 지정 시간(초) 길이의 영상을 생성한다."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg([
        "-stream_loop", "-1",
        "-i", input_path,
        "-t", str(duration),
        "-vcodec", "libx264",
        "-crf", "23",
        "-preset", "fast",
        "-y", output_path,
    ], desc="loop_video")
    _check_output(output_path, "loop_video")
    return output_path


def capture_thumbnail(video_path: str, output_path: str | None = None) -> str:
    """영상의 첫 프레임을 썸네일로 캡처한다."""
    if output_path is None:
        output_path = str(Path(video_path).with_suffix(".jpg"))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg([
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        "-y", output_path,
    ], desc="capture_thumbnail")
    _check_output(output_path, "capture_thumbnail")
    return output_path


def images_to_video(
    image_list: list[str],
    audio_path: str,
    output_path: str,
    seconds_per_image: int = 10,
) -> str:
    """이미지 슬라이드쇼 + 음성을 합성하여 영상을 만든다."""
    import tempfile
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 이미지 리스트 파일 생성
    list_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="ffmpeg_list_"
    )
    try:
        for img in image_list:
            list_file.write(f"file '{img}'\n")
            list_file.write(f"duration {seconds_per_image}\n")
        # 마지막 이미지 한 번 더 (FFmpeg concat demuxer 요구사항)
        if image_list:
            list_file.write(f"file '{image_list[-1]}'\n")
        list_file.close()

        _run_ffmpeg([
            "-f", "concat",
            "-safe", "0",
            "-i", list_file.name,
            "-i", audio_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
            "-vcodec", "libx264",
            "-crf", "23",
            "-preset", "fast",
            "-acodec", "aac",
            "-shortest",
            "-y", output_path,
        ], desc="images_to_video")
    finally:
        os.unlink(list_file.name)

    _check_output(output_path, "images_to_video")
    return output_path


def mix_audio(
    video_path: str,
    bgm_path: str,
    output_path: str,
    bgm_volume: float = 0.15,
) -> str:
    """영상에 배경음악을 볼륨 조절하여 믹싱한다."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg([
        "-i", video_path,
        "-stream_loop", "-1",
        "-i", bgm_path,
        "-filter_complex",
        f"[1:a]volume={bgm_volume}[bg];[0:a][bg]amix=inputs=2:duration=first",
        "-vcodec", "copy",
        "-acodec", "aac",
        "-y", output_path,
    ], desc="mix_audio")
    _check_output(output_path, "mix_audio")
    return output_path
