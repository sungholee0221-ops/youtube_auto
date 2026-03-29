"""
썸네일 텍스트 오버레이 생성 모듈.

채널별 레이아웃:
  rain    : [상단] 영상 길이  [중앙] 빗소리 ASMR  [하단] 수면유도 · 집중 · 명상
  dino    : [상단] 공룡 이름  [중앙] 공룡 다큐멘터리  [하단] BBC 스타일 · 교육
  history : [상단] 주제명    [중앙] 역사 다큐멘터리  [하단] 카테고리
"""

import os
import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# 한글 폰트 경로 (Bold → Regular 순으로 fallback)
_FONT_CANDIDATES = [
    "/Library/Fonts/NanumSquareExtraBold.ttf",
    "/Library/Fonts/NanumSquareBold.ttf",
    "/Library/Fonts/NanumGothicBold.ttf",
    "/Library/Fonts/NanumGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]

# 채널별 고정 문구
_CHANNEL_CONFIG = {
    "rain": {
        "mid":    "빗소리 ASMR",
        "bottom": "수면유도 · 집중 · 명상",
    },
    "dino": {
        "mid":    "공룡 다큐멘터리",
        "bottom": "BBC 스타일 · 교육 · 흥미",
    },
    "history": {
        "mid":    "역사 다큐멘터리",
        "bottom": "교육 · 흥미 · 지식",
    },
}


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_text_with_shadow(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple,
    shadow_offset: int = 3,
) -> None:
    """그림자 효과가 있는 텍스트를 그린다."""
    x, y = xy
    shadow_color = (0, 0, 0, 200)
    draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_color)
    draw.text((x, y), text, font=font, fill=fill)


def _centered_x(draw: ImageDraw.ImageDraw, text: str, font, img_width: int) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    return (img_width - text_width) // 2


def add_thumbnail_overlay(
    image_path: str,
    output_path: str,
    channel: str,
    top_text: str = "",
) -> str:
    """
    썸네일 이미지에 채널별 텍스트 오버레이를 추가한다.

    Args:
        image_path: 원본 썸네일 JPG 경로
        output_path: 저장할 경로
        channel: "rain" / "dino" / "history"
        top_text: 상단에 표시할 동적 텍스트 (영상 길이, 공룡 이름, 주제명 등)
    """
    cfg = _CHANNEL_CONFIG.get(channel, {})
    if not cfg:
        logger.warning(f"썸네일 오버레이: 알 수 없는 채널 '{channel}', 원본 유지")
        return image_path

    img = Image.open(image_path).convert("RGBA")
    W, H = img.size

    # 하단 그라데이션 오버레이 (검정 반투명)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    gradient_top = int(H * 0.45)
    for y in range(gradient_top, H):
        alpha = int(200 * (y - gradient_top) / (H - gradient_top))
        draw_ov.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, overlay)

    draw = ImageDraw.Draw(img)

    font_top = _load_font(72)
    font_mid = _load_font(100)
    font_bot = _load_font(54)

    # 상단 텍스트 (동적: 길이 / 공룡이름 / 주제명)
    if top_text:
        x = _centered_x(draw, top_text, font_top, W)
        _draw_text_with_shadow(draw, (x, int(H * 0.52)), top_text, font_top,
                               fill=(255, 220, 80, 255))  # 노란색

    # 중앙 텍스트 (채널 고정)
    mid_text = cfg["mid"]
    x = _centered_x(draw, mid_text, font_mid, W)
    _draw_text_with_shadow(draw, (x, int(H * 0.64)), mid_text, font_mid,
                           fill=(255, 255, 255, 255))  # 흰색

    # 하단 텍스트 (채널 고정)
    bot_text = cfg["bottom"]
    x = _centered_x(draw, bot_text, font_bot, W)
    _draw_text_with_shadow(draw, (x, int(H * 0.82)), bot_text, font_bot,
                           fill=(200, 230, 255, 255))  # 연한 파란색

    # JPEG 저장
    result = img.convert("RGB")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path, "JPEG", quality=95)
    logger.info(f"썸네일 오버레이 완료: {output_path}")
    return output_path
