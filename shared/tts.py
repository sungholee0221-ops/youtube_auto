import os
import logging
import time
from pathlib import Path
from google.cloud import texttospeech
from google.cloud import storage
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

LONG_AUDIO_BYTE_LIMIT = 5000


def synthesize_speech(text: str, output_path: str) -> str:
    """텍스트를 음성으로 변환한다. 5000바이트 초과 시 Long Audio API를 사용한다."""
    text_bytes = len(text.encode("utf-8"))
    logger.info(f"TTS 입력: {text_bytes} bytes, limit={LONG_AUDIO_BYTE_LIMIT}")

    if text_bytes <= LONG_AUDIO_BYTE_LIMIT:
        return _synthesize_standard(text, output_path)
    else:
        return _synthesize_long_audio(text, output_path)


def _get_voice_params() -> texttospeech.VoiceSelectionParams:
    return texttospeech.VoiceSelectionParams(
        language_code="ko-KR",
        name="ko-KR-Wavenet-C",
        ssml_gender=texttospeech.SsmlVoiceGender.MALE,
    )


def _get_audio_config() -> texttospeech.AudioConfig:
    return texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=0.85,
        pitch=-2.0,
    )


def _synthesize_standard(text: str, output_path: str) -> str:
    """표준 TTS API (5000바이트 이하)."""
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=_get_voice_params(),
        audio_config=_get_audio_config(),
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(response.audio_content)

    file_size = os.path.getsize(output_path)
    if file_size == 0:
        raise RuntimeError(f"TTS 출력 파일이 0바이트: {output_path}")
    logger.info(f"TTS 표준 API 완료: {output_path} ({file_size} bytes)")
    return output_path


def _synthesize_long_audio(text: str, output_path: str) -> str:
    """Long Audio API (5000바이트 초과). GCS 버킷을 통해 생성한다."""
    client = texttospeech.TextToSpeechLongAudioSynthesizeClient()
    bucket_name = os.environ["GCS_BUCKET_NAME"]
    gcs_output = f"gs://{bucket_name}/tts_output/{Path(output_path).stem}.mp3"

    synthesis_input = texttospeech.SynthesisInput(text=text)
    request = texttospeech.SynthesizeLongAudioRequest(
        parent=f"projects/{_get_project_id()}/locations/global",
        input=synthesis_input,
        voice=_get_voice_params(),
        audio_config=_get_audio_config(),
        output_gcs_uri=gcs_output,
    )

    operation = client.synthesize_long_audio(request=request)
    logger.info(f"Long Audio API 작업 시작: {gcs_output}")
    operation.result(timeout=3600)
    logger.info("Long Audio API 작업 완료")

    # GCS에서 로컬로 다운로드
    _download_from_gcs(gcs_output, output_path)

    file_size = os.path.getsize(output_path)
    if file_size == 0:
        raise RuntimeError(f"Long Audio TTS 출력 파일이 0바이트: {output_path}")
    logger.info(f"TTS Long Audio 완료: {output_path} ({file_size} bytes)")
    return output_path


def _get_project_id() -> str:
    """Google Cloud 프로젝트 ID를 환경변수에서 가져온다."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        # 서비스 계정 JSON에서 자동 추출 시도
        import json
        cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        if cred_path and os.path.exists(cred_path):
            with open(cred_path) as f:
                project_id = json.load(f).get("project_id", "")
    if not project_id:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT 환경변수를 설정하세요")
    return project_id


def _download_from_gcs(gcs_uri: str, local_path: str) -> None:
    """GCS URI에서 로컬 파일로 다운로드한다."""
    # gs://bucket/path 파싱
    parts = gcs_uri.replace("gs://", "").split("/", 1)
    bucket_name, blob_name = parts[0], parts[1]

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(local_path)
    logger.info(f"GCS 다운로드 완료: {gcs_uri} → {local_path}")
