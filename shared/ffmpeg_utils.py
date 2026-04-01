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
            "-pix_fmt", "yuv420p",   # QuickTime/iOS 호환
            "-r", "24",              # 24fps 고정 (이미지 슬라이드쇼)
            "-acodec", "aac",
            "-shortest",
            "-y", output_path,
        ], desc="images_to_video")
    finally:
        os.unlink(list_file.name)

    _check_output(output_path, "images_to_video")
    return output_path


def create_rain_video(
    visual_path: str,
    audio_path: str,
    output_path: str,
    visual_duration: int = 900,
    total_duration: int = 10800,
) -> str:
    """비소리 채널 영상 생성.

    앞 visual_duration초: Pexels 영상 (1920x1080, 무음)
    나머지: 검은 화면
    전체 audio_path MP3를 total_duration초 루프하여 합성
    """
    import tempfile
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    black_duration = total_duration - visual_duration

    with tempfile.TemporaryDirectory(prefix="rain_build_") as tmp:
        visual_clip = os.path.join(tmp, "visual.mp4")
        black_clip   = os.path.join(tmp, "black.mp4")
        concat_txt   = os.path.join(tmp, "concat.txt")
        combined     = os.path.join(tmp, "combined.mp4")
        looped_audio = os.path.join(tmp, "audio.m4a")

        # 1. Pexels 영상 → visual_duration초, 1920x1080, 24fps, 무음, 끝 5초 페이드아웃
        fade_duration = 5
        fade_start = visual_duration - fade_duration
        _run_ffmpeg([
            "-stream_loop", "-1", "-i", visual_path,
            "-t", str(visual_duration),
            "-vf", (
                "scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
                f"fps=24,"
                f"fade=t=out:st={fade_start}:d={fade_duration}"
            ),
            "-vcodec", "libx264", "-crf", "23", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-an",
            "-y", visual_clip,
        ], desc="rain_visual")

        # 2. 검은 화면 생성 (ultrafast + CRF51, 동일 스펙: 24fps, yuv420p)
        _run_ffmpeg([
            "-f", "lavfi", "-i", "color=c=black:size=1920x1080:rate=24",
            "-t", str(black_duration),
            "-vcodec", "libx264", "-crf", "51", "-preset", "ultrafast",
            "-tune", "stillimage", "-pix_fmt", "yuv420p", "-an",
            "-y", black_clip,
        ], desc="rain_black")

        # 3. 두 영상 이어붙이기
        with open(concat_txt, "w") as f:
            f.write(f"file '{visual_clip}'\n")
            f.write(f"file '{black_clip}'\n")
        _run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", concat_txt,
            "-c", "copy", "-y", combined,
        ], desc="rain_concat")

        # 4. 오디오 루프
        _run_ffmpeg([
            "-stream_loop", "-1", "-i", audio_path,
            "-t", str(total_duration),
            "-acodec", "aac", "-ab", "192k",
            "-y", looped_audio,
        ], desc="rain_audio_loop")

        # 5. 영상 + 오디오 합성
        _run_ffmpeg([
            "-i", combined, "-i", looped_audio,
            "-vcodec", "copy", "-acodec", "copy", "-shortest",
            "-y", output_path,
        ], desc="rain_merge")

    _check_output(output_path, "create_rain_video")
    return output_path


def create_history_video(
    image_list: list[str],
    audio_path: str,
    output_path: str,
    visual_duration: int = 180,   # 3분간 이미지 슬라이드쇼
) -> str:
    """역사 채널 영상 생성.

    앞 visual_duration초: 이미지 슬라이드쇼
    나머지: 검은 화면
    전체: TTS 음성
    """
    import tempfile
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if not image_list:
        raise ValueError("이미지 목록이 비어 있습니다.")

    with tempfile.TemporaryDirectory(prefix="history_build_") as tmp:
        list_file   = os.path.join(tmp, "list.txt")
        visual_clip = os.path.join(tmp, "visual.mp4")
        black_clip  = os.path.join(tmp, "black.mp4")
        concat_txt  = os.path.join(tmp, "concat.txt")
        combined    = os.path.join(tmp, "combined.mp4")

        # 1. 이미지 슬라이드쇼 → visual_duration초 (이미지 균등 배분)
        spi = max(1, visual_duration // len(image_list))
        with open(list_file, "w") as f:
            for img in image_list:
                f.write(f"file '{img}'\n")
                f.write(f"duration {spi}\n")
            f.write(f"file '{image_list[-1]}'\n")

        _run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", list_file,
            "-vf", (
                "scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
                f"fade=t=out:st={visual_duration - 3}:d=3"
            ),
            "-vcodec", "libx264", "-crf", "23", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-r", "24", "-an",
            "-t", str(visual_duration),
            "-y", visual_clip,
        ], desc="history_visual")

        # 2. 오디오 전체 길이 측정
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True,
        )
        total_duration = max(visual_duration + 1, int(float(probe.stdout.strip() or 0)))
        black_duration = total_duration - visual_duration
        logger.info(f"오디오 길이: {total_duration}s → 검은화면: {black_duration}s")

        # 3. 검은 화면 (ultrafast + CRF51: 순색이라 품질 손실 없이 빠름)
        _run_ffmpeg([
            "-f", "lavfi", "-i", "color=c=black:size=1920x1080:rate=24",
            "-t", str(black_duration),
            "-vcodec", "libx264", "-crf", "51", "-preset", "ultrafast",
            "-tune", "stillimage", "-pix_fmt", "yuv420p", "-an",
            "-y", black_clip,
        ], desc="history_black")

        # 4. visual + black 이어붙이기
        with open(concat_txt, "w") as f:
            f.write(f"file '{visual_clip}'\n")
            f.write(f"file '{black_clip}'\n")
        _run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", concat_txt,
            "-c", "copy", "-y", combined,
        ], desc="history_concat")

        # 5. 영상 + 음성 합성
        _run_ffmpeg([
            "-i", combined, "-i", audio_path,
            "-vcodec", "copy", "-acodec", "aac", "-ab", "192k",
            "-shortest", "-y", output_path,
        ], desc="history_merge")

    _check_output(output_path, "create_history_video")
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
