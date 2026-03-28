import json
import re
import logging
import anthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _parse_json(text: str) -> dict:
    """Claude 응답에서 JSON을 추출하여 파싱한다."""
    # ```json ... ``` 코드블록 제거
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1)
    return json.loads(text.strip())


def _call(prompt: str, max_tokens: int = 1024, retries: int = 1) -> str:
    """Claude API 호출. 실패 시 retries만큼 재시도."""
    client = get_client()
    for attempt in range(retries + 1):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        except Exception as e:
            logger.warning(f"Claude API 호출 실패 (시도 {attempt + 1}): {e}")
            if attempt == retries:
                raise
    return ""


def generate_title_description(prompt: str) -> dict:
    """제목/설명을 JSON으로 생성한다. {"title": ..., "description": ...}"""
    text = _call(prompt)
    return _parse_json(text)


def generate_script(prompt: str, max_tokens: int = 8192) -> str:
    """나레이션 스크립트를 생성한다."""
    return _call(prompt, max_tokens=max_tokens)


def generate_topic(prompt: str) -> str:
    """주제를 생성한다."""
    return _call(prompt, max_tokens=1024)
