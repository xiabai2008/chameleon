"""合成验证码生成器：生成带标签的训练/测试数据（P8-8 测试与演示用）。"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CHARSET = "0123456789"
WIDTH, HEIGHT = 120, 40
TEMPLATE_SIZE = (28, 40)


def _find_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """优先使用系统字体，回退默认字体。"""
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


_FONT = None


def _font() -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    global _FONT
    if _FONT is None:
        _FONT = _find_font(24)
    return _FONT


def _draw_noise(draw: ImageDraw.ImageDraw) -> None:
    """随机噪点 + 干扰线。"""
    for _ in range(random.randint(30, 80)):
        x, y = random.randint(0, WIDTH - 1), random.randint(0, HEIGHT - 1)
        draw.point((x, y), fill=random.randint(120, 200))
    for _ in range(random.randint(1, 3)):
        draw.line(
            [
                (random.randint(0, WIDTH), random.randint(0, HEIGHT)),
                (random.randint(0, WIDTH), random.randint(0, HEIGHT)),
            ],
            fill=random.randint(150, 220),
            width=1,
        )


def generate_captcha(text: str, seed: int | None = None) -> bytes:
    """生成指定文本的验证码 PNG bytes（含噪声/扭曲/旋转）。"""
    img = _build_image(text, random.Random(seed))
    buf = __import__("io").BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_image(text: str, rng: random.Random) -> Image.Image:
    img = Image.new("L", (WIDTH, HEIGHT), color=random.randint(230, 250))
    draw = ImageDraw.Draw(img)
    _draw_noise(draw)
    for i, ch in enumerate(text):
        # 随机旋转与垂直抖动
        angle = rng.randint(-10, 10)
        y_offset = rng.randint(-2, 2)
        char_img = Image.new("L", (TEMPLATE_SIZE[0] + 8, TEMPLATE_SIZE[1] + 8), color=255)
        cdraw = ImageDraw.Draw(char_img)
        cdraw.text((4, 4), ch, font=_font(), fill=0)
        char_img = char_img.rotate(angle, expand=False, fillcolor=255)
        x = 8 + i * (WIDTH - 16) // len(text)
        img.paste(char_img, (x, y_offset + 6), mask=char_img)
    return img.filter(ImageFilter.GaussianBlur(0.4))


def generate_character_crops(n_chars: int = 4, seed: int = 0) -> list[tuple[str, bytes]]:
    """生成多字符图并按生成位置裁剪出每个字符 ROI（训练/测试分布一致）。"""
    rng = random.Random(seed)
    text = "".join(rng.choice(CHARSET) for _ in range(n_chars))
    img = _build_image(text, rng)
    slot = (WIDTH - 16) // n_chars
    crops: list[tuple[str, bytes]] = []
    for i, ch in enumerate(text):
        x = 8 + i * slot
        crop = img.crop((x, 0, x + slot, HEIGHT))
        buf = __import__("io").BytesIO()
        crop.save(buf, format="PNG")
        crops.append((ch, buf.getvalue()))
    return crops


def generate_labeled_dataset(n_per_char: int, out_dir: str | Path, *, chars: str = CHARSET) -> Path:
    """生成标注数据集（字符样本来自多字符图裁剪，与测试分布一致）。"""
    out = Path(out_dir)
    for ch in chars:
        (out / ch).mkdir(parents=True, exist_ok=True)
    saved: dict[str, int] = {ch: 0 for ch in chars}
    idx = 0
    while any(v < n_per_char for v in saved.values()):
        for ch, crop in generate_character_crops(n_chars=4, seed=idx):
            if saved.get(ch, 0) < n_per_char:
                (out / ch / f"{saved[ch]}.png").write_bytes(crop)
                saved[ch] += 1
        idx += 1
    return out


def generate_test_samples(n: int, text_len: int = 4, seed: int = 42) -> list[tuple[bytes, str]]:
    """生成 (图片bytes, 正确文本) 测试样本。"""
    rng = random.Random(seed)
    samples: list[tuple[bytes, str]] = []
    for i in range(n):
        text = "".join(rng.choice(CHARSET) for _ in range(text_len))
        samples.append((generate_captcha(text, seed=seed + i), text))
    return samples
