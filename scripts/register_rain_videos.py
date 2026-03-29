"""
Pexels 영상 또는 Freesound 오디오를 Supabase generated_files 테이블에 일괄 등록한다.

파일 확장자로 타입 자동 판별:
  .mp4 / .mov              → rain_video  (Pexels 무음 영상)
  .mp3                     → rain_audio  (그대로 등록)
  .wav / .flac / .m4a / .aac → rain_audio  (MP3로 자동 변환 후 등록)

소스 파일 보관 위치 (파일을 여기에 넣고 등록):
    channel1_source/rain_video/   ← Pexels 영상 (rain_01.mp4, rain_02.mp4 ...)
    channel1_source/rain_audio/   ← Freesound 오디오 (rain_audio_01.mp3 ...)

사용법:
    # 기본 경로(channel1_source) 전체 등록 — 인수 없이 실행
    python scripts/register_rain_videos.py

    # 특정 폴더 또는 파일 지정
    python scripts/register_rain_videos.py channel1_source/rain_video/
    python scripts/register_rain_videos.py ~/Downloads/rain.wav

    # 현재 등록 현황 확인
    python scripts/register_rain_videos.py --list
"""

import os
import sys
import glob
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from shared.supabase_client import get_client

PROJECT_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_ROOT   = os.path.join(PROJECT_ROOT, "channel1_source")
DEFAULT_DIRS  = [
    os.path.join(SOURCE_ROOT, "rain_video"),
    os.path.join(SOURCE_ROOT, "rain_audio"),
]

VIDEO_EXTS        = {".mp4", ".mov"}
AUDIO_EXTS_DIRECT = {".mp3"}
AUDIO_EXTS_CONV   = {".wav", ".flac", ".m4a", ".aac"}
FFMPEG            = os.environ.get("FFMPEG_PATH", "/usr/local/bin/ffmpeg")


def detect_file_type(path: str) -> str | None:
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        return "rain_video"
    if ext in AUDIO_EXTS_DIRECT | AUDIO_EXTS_CONV:
        return "rain_audio"
    return None


def convert_to_mp3(src: str) -> str:
    """WAV/FLAC/M4A 파일을 같은 경로에 MP3로 변환한다. 변환된 MP3 경로 반환."""
    dst = os.path.splitext(src)[0] + ".mp3"
    if os.path.exists(dst):
        print(f"  [변환 스킵] 이미 MP3 존재: {dst}")
        return dst
    print(f"  [변환중]  {os.path.basename(src)} → MP3 ...")
    result = subprocess.run([
        FFMPEG, "-y", "-i", src,
        "-acodec", "libmp3lame", "-ab", "192k", "-ar", "44100",
        dst
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"MP3 변환 실패: {result.stderr[:300]}")
    print(f"  [변환완료] {dst}")
    return dst


def list_registered() -> None:
    client = get_client()
    for file_type in ("rain_video", "rain_audio"):
        rows = client.table("generated_files").select("id,file_path,is_used").eq("file_type", file_type).order("id").execute()
        data = rows.data or []
        print(f"\n[{file_type}] {len(data)}건")
        for row in data:
            status = "사용됨" if row["is_used"] else "대기중"
            print(f"  id={row['id']}  [{status}]  {row['file_path']}")


def register_files(paths: list[str]) -> None:
    client = get_client()

    existing = client.table("generated_files").select("file_path").in_("file_type", ["rain_video", "rain_audio"]).execute()
    existing_paths = {row["file_path"] for row in (existing.data or [])}

    added = skipped = unknown = 0
    for path in paths:
        abs_path = os.path.abspath(path)
        file_type = detect_file_type(abs_path)

        if file_type is None:
            print(f"  [SKIP] 지원하지 않는 확장자: {abs_path}")
            unknown += 1
            continue
        if not os.path.isfile(abs_path):
            print(f"  [SKIP] 파일 없음: {abs_path}")
            skipped += 1
            continue

        # WAV/FLAC/M4A → MP3 자동 변환
        ext = os.path.splitext(abs_path)[1].lower()
        if file_type == "rain_audio" and ext in AUDIO_EXTS_CONV:
            try:
                abs_path = convert_to_mp3(abs_path)
            except RuntimeError as e:
                print(f"  [ERROR] {e}")
                skipped += 1
                continue

        if abs_path in existing_paths:
            print(f"  [SKIP] 이미 등록됨: {abs_path}")
            skipped += 1
            continue

        client.table("generated_files").insert({
            "file_type": file_type,
            "file_path": abs_path,
            "is_used": False,
        }).execute()
        print(f"  [OK]   {file_type} 등록: {abs_path}")
        added += 1

    print(f"\n완료 — 등록: {added}건 / 스킵: {skipped}건 / 미지원: {unknown}건")


def collect_paths(args: list[str]) -> list[str]:
    paths = []
    for arg in args:
        if os.path.isdir(arg):
            for ext in ("*.mp4", "*.mov", "*.mp3", "*.wav", "*.flac", "*.m4a", "*.aac"):
                paths.extend(sorted(glob.glob(os.path.join(arg, ext))))
        else:
            paths.append(arg)
    return paths


if __name__ == "__main__":
    args = sys.argv[1:]

    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    if args and args[0] == "--list":
        list_registered()
        sys.exit(0)

    # 인수 없으면 channel1_source 기본 경로 사용
    targets = args if args else DEFAULT_DIRS

    paths = collect_paths(targets)
    if not paths:
        if not args:
            print(f"channel1_source 폴더에 파일이 없습니다.\n경로: {SOURCE_ROOT}")
        else:
            print("등록할 파일이 없습니다.")
        sys.exit(1)

    print(f"등록 대상: {len(paths)}개 파일")
    register_files(paths)
