"""
Google Cloud TTS 모듈
- 표준 API: 5000바이트 이하 (API 키 사용, REST 호출)
- Long Audio API: 5000바이트 초과 (서비스 계정 + GCS 필요, 채널3 단계에서 구현)

표준 API는 API 키만으로 동작하므로 서비스 계정 JSON이 필요 없다.
"""

import os
import base64
import logging
import math
import tempfile
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BYTE_LIMIT = 5000  # Google TTS 표준 API 1회 바이트 한도


def _get_api_key() -> str:
    """Supabase 또는 환경변수에서 Google TTS API 키를 가져온다."""
    try:
        from shared.supabase_client import get_api_key
        return get_api_key("google-tts")
    except Exception:
        key = os.environ.get("GOOGLE_TTS_API_KEY", "")
        if not key:
            raise RuntimeError("Google TTS API 키가 없습니다 (Supabase/환경변수 모두 실패)")
        return key


def synthesize_speech(text: str, output_path: str) -> str:
    """텍스트를 음성으로 변환한다. 5000바이트 초과 시 청크 분할 + 이어붙이기."""
    text_bytes = len(text.encode("utf-8"))
    logger.info(f"TTS 입력: {text_bytes} bytes")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if text_bytes <= BYTE_LIMIT:
        _synthesize_chunk(text, output_path)
    else:
        _synthesize_chunked(text, output_path)

    file_size = os.path.getsize(output_path)
    if file_size == 0:
        raise RuntimeError(f"TTS 출력 파일이 0바이트: {output_path}")
    logger.info(f"TTS 완료: {output_path} ({file_size:,} bytes)")
    return output_path


def _synthesize_chunk(text: str, output_path: str) -> None:
    """단일 청크 TTS (5000바이트 이하)."""
    api_key = _get_api_key()
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
    body = {
        "input": {"text": text},
        "voice": {
            "languageCode": "ko-KR",
            "name": "ko-KR-Wavenet-C",
            "ssmlGender": "MALE",
        },
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": 0.85,
            "pitch": -2.0,
        },
    }
    resp = requests.post(url, json=body, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"Google TTS API 실패: {resp.status_code} {resp.text[:300]}")

    audio = base64.b64decode(resp.json()["audioContent"])
    with open(output_path, "wb") as f:
        f.write(audio)


def _split_text(text: str, limit: int = BYTE_LIMIT) -> list[str]:
    """텍스트를 바이트 한도 내 문장 단위로 분할한다."""
    sentences = []
    for line in text.split("\n"):
        for s in line.replace(". ", ".\n").split("\n"):
            s = s.strip()
            if s:
                sentences.append(s)

    chunks = []
    current = ""
    for s in sentences:
        candidate = (current + " " + s).strip() if current else s
        if len(candidate.encode("utf-8")) > limit:
            if current:
                chunks.append(current)
            # 문장 자체가 한도 초과면 강제 분할
            if len(s.encode("utf-8")) > limit:
                while s:
                    cut = limit
                    while len(s[:cut].encode("utf-8")) > limit:
                        cut -= 1
                    chunks.append(s[:cut])
                    s = s[cut:]
                current = ""
            else:
                current = s
        else:
            current = candidate
    if current:
        chunks.append(current)

    return chunks


def _synthesize_chunked(text: str, output_path: str) -> None:
    """텍스트를 청크로 나눠 TTS 후 MP3를 이어붙인다."""
    chunks = _split_text(text)
    logger.info(f"TTS 청크 분할: {len(chunks)}개")

    tmp_dir = tempfile.mkdtemp(prefix="tts_chunks_")
    chunk_files = []

    try:
        for i, chunk in enumerate(chunks):
            chunk_path = os.path.join(tmp_dir, f"chunk_{i:04d}.mp3")
            logger.info(f"TTS 청크 {i+1}/{len(chunks)} ({len(chunk.encode('utf-8'))} bytes)")
            _synthesize_chunk(chunk, chunk_path)
            chunk_files.append(chunk_path)

        # MP3 파일 단순 이어붙이기 (MP3 프레임 구조상 concat 가능)
        with open(output_path, "wb") as out:
            for cf in chunk_files:
                with open(cf, "rb") as inp:
                    out.write(inp.read())

        logger.info(f"TTS 청크 합치기 완료: {len(chunk_files)}개 -> {output_path}")
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
