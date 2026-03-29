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


def generate_long_script(topic: str, sections: int = 4) -> str:
    """주제를 섹션으로 나눠 긴 스크립트를 생성한다. (15분 ≈ 4섹션 × 4분)"""

    # 1단계: 섹션 구성 계획
    plan_prompt = (
        f"'{topic}'에 대한 유튜브 역사 다큐 나레이션을 {sections}개 챕터로 구성해줘.\n"
        f"각 챕터 제목만 번호 없이 한 줄씩 {sections}개 출력해줘."
    )
    plan_text = _call(plan_prompt, max_tokens=512)
    chapter_titles = [t.strip() for t in plan_text.strip().split("\n") if t.strip()][:sections]

    # 부족하면 기본 구성으로 채움
    default_chapters = ["배경과 시대적 상황", "주요 사건 전개", "핵심 인물과 역할",
                        "전환점과 결정적 순간", "결과와 영향", "역사적 의의와 교훈"]
    while len(chapter_titles) < sections:
        chapter_titles.append(default_chapters[len(chapter_titles) % len(default_chapters)])

    logger.info(f"챕터 구성: {chapter_titles}")

    # 2단계: 챕터별 스크립트 생성
    full_script = ""
    for i, chapter in enumerate(chapter_titles):
        logger.info(f"스크립트 생성 중 ({i+1}/{sections}): {chapter}")
        section_prompt = (
            f"'{topic}' 역사 다큐멘터리 나레이션 중 '{chapter}' 부분을 한국어로 작성해줘.\n"
            "수면 유도에 적합한 차분하고 낮은 톤으로, 사실에 기반한 교육적 내용으로.\n"
            "반드시 6000자 이상으로 작성해줘. 시대적 배경, 인물의 심리, 현장 묘사, "
            "역사적 맥락을 풍부하고 세밀하게 서술해줘. 짧게 요약하지 말고 충분히 길게 써줘.\n"
            "순수 나레이션 텍스트만 출력해줘 (챕터 제목, 번호, 안내문 제외)."
        )
        section_text = _call(section_prompt, max_tokens=8192)
        full_script += section_text.strip() + "\n\n"

    logger.info(f"전체 스크립트 생성 완료: {len(full_script)}자 ({sections}섹션)")
    return full_script.strip()
