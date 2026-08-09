"""验证码模型训练：模板匹配识别器（方案 P8-8）。

流程：
1. 收集：scripts/collect_captcha.py 或手动，样本存 sample_dir/{label}/xxx.png
2. 训练：TemplateTrainer.train() → 字符分割 + 归一化 + 平均模板 → 保存 npz
3. 识别：TemplateRecognizer.recognize(image_bytes) → 文本

纯 opencv + numpy 实现（无重依赖），适合简单数字/字母验证码；
粘连/扭曲严重的验证码仍建议 ddddocr 或第三方打码。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np

try:
    import cv2

    _HAS_CV2 = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]
    _HAS_CV2 = False

from chameleon.infra.logging import get_logger

log = get_logger("captcha_trainer")

CHARSET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
TEMPLATE_SIZE = (28, 40)  # 归一化模板尺寸 (w, h)
_MIN_AREA = 30  # 字符连通域最小面积
_MIN_CHAR_W = 6  # 字符最小宽度（过滤噪点碎片）
_MAX_CHAR_W = 36  # 字符最大宽度（过滤粘连/干扰线）
MAX_CHARS = 8


def _to_gray_bytes(image_bytes: bytes) -> Any:
    """bytes → 灰度图（numpy 数组）。"""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("invalid image bytes")
    return img


def _hole_count(binary_char: Any) -> int:
    """字符内部孔洞数（'8'=2，'0'/'6'/'9'=1，'1'/'2'/'3'=0）。"""
    if binary_char.dtype != np.uint8:  # 模板为 0-1 float，需转 uint8
        binary_char = (binary_char * 255).astype(np.uint8)
    contours, hierarchy = cv2.findContours(binary_char, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return 0
    return int(sum(1 for h in hierarchy[0] if h[3] != -1))


def _preprocess(img: Any) -> Any:
    """灰度 → 二值化（Otsu）→ 中值去噪 → 闭运算连接断裂笔画。"""
    img = cv2.medianBlur(img, 3)
    _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    kernel = np.ones((3, 3), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    return binary


def _split_characters(binary: Any) -> list[Any]:
    """按连通域分割字符，按 x 坐标排序。"""
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    img_h, img_w = binary.shape[:2]
    boxes: list[tuple[int, int, int, int]] = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h < _MIN_AREA:
            continue
        # 过滤干扰线形成的全图/横贯轮廓
        if w >= img_w * 0.9 or h >= img_h * 0.9:
            continue
        if w > img_w * 0.5:  # 横跨半屏（多字符粘连或长干扰线）
            continue
        if w < _MIN_CHAR_W or w > _MAX_CHAR_W:  # 宽度异常（噪点碎片/多字符粘连）
            continue
        boxes.append((x, y, w, h))
    boxes.sort(key=lambda b: b[0])
    chars: list[Any] = []
    for x, y, w, h in boxes[:MAX_CHARS]:
        roi = binary[y : y + h, x : x + w]
        chars.append(cv2.resize(roi, TEMPLATE_SIZE, interpolation=cv2.INTER_AREA))
    return chars


def _normalize_template(chars: list[Any], label: str) -> np.ndarray:
    """同类字符的样本归一化堆叠（保留细节，供最近邻匹配）。"""
    if not chars:
        raise ValueError(f"no characters found for label '{label}'")
    return np.stack([c.astype(np.float32) / 255.0 for c in chars])


class TemplateTrainer:
    """从标注样本目录训练字符模板库。

    目录结构：sample_dir/{char}/xxx.png
    """

    def __init__(self, sample_dir: str | Path) -> None:
        self.sample_dir = Path(sample_dir)

    def train(self, output_path: str | Path) -> dict[str, Any]:
        """训练并保存 npz 模型。返回 {labels, templates} 摘要。"""
        if not _HAS_CV2:  # pragma: no cover
            raise RuntimeError("opencv-python required for captcha training")
        if not self.sample_dir.is_dir():
            raise FileNotFoundError(f"sample dir not found: {self.sample_dir}")

        labels: list[str] = []
        templates: list[np.ndarray] = []
        for label_dir in sorted(p for p in self.sample_dir.iterdir() if p.is_dir()):
            label = label_dir.name
            if len(label) != 1 or label not in CHARSET:
                log.warning("skip invalid label dir", dir=str(label_dir))
                continue
            chars: list[Any] = []
            for img_file in sorted(label_dir.glob("*.png")):
                try:
                    img = _to_gray_bytes(img_file.read_bytes())
                    chars.extend(_split_characters(_preprocess(img)))
                except Exception as exc:
                    log.warning("skip sample", file=str(img_file), error=str(exc))
            if not chars:
                continue
            labels.append(label)
            templates.append(_normalize_template(chars, label))
            log.info("trained_char", char=label, samples=len(chars))

        if not labels:
            raise ValueError("no valid training samples found")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        # 最近邻模式：保存全部样本（每字符样本数可能不同 → concatenate）
        all_templates = np.concatenate(templates, axis=0)
        all_labels = np.array([label for label, arr in zip(labels, templates, strict=False) for _ in range(arr.shape[0])])
        np.savez_compressed(output, labels=all_labels, templates=all_templates)
        log.info("model_saved", path=str(output), samples=len(all_labels), chars=len(labels))
        return {"labels": labels, "char_count": len(labels), "sample_count": len(all_labels), "path": str(output)}


class TemplateRecognizer:
    """加载模板库识别验证码。"""

    def __init__(self, model_path: str | Path) -> None:
        if not _HAS_CV2:  # pragma: no cover
            raise RuntimeError("opencv-python required for captcha recognition")
        with np.load(model_path) as data:
            self._labels: list[str] = [str(x) for x in data["labels"]]
            self._templates = data["templates"]  # shape (N, 28, 40)，N = 全部样本
        flat = self._templates.reshape(len(self._labels), -1)
        norms = np.linalg.norm(flat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._normalized = (flat / norms).T  # (D, N)，列向量模板
        # 每个模板的字符标签与孔洞数（孔洞数用于相似度接近时裁决）
        self._template_holes = np.array([_hole_count(t) for t in self._templates])

    def _match_char(self, char: Any) -> str:
        """单字符最近邻匹配：余弦相似度 + 孔洞数裁决。"""
        flat = char.astype(np.float32).reshape(-1) / 255.0
        norm = np.linalg.norm(flat)
        if norm == 0:
            return ""
        flat = flat / norm
        scores = self._normalized.T @ flat  # 与全部样本的相似度
        order = np.argsort(scores)[::-1]
        best, second = int(order[0]), int(order[1])
        if scores[best] - scores[second] < 0.05:
            # 高分候选接近时用孔洞数裁决（前 5 个候选里找孔洞匹配的）
            holes = _hole_count(char)
            for idx in order[:5]:
                if self._template_holes[int(idx)] == holes:
                    return self._labels[int(idx)]
        return self._labels[best]

    def recognize(self, image_bytes: bytes) -> str:
        """识别单张验证码图片，返回文本。"""
        img = _to_gray_bytes(image_bytes)
        chars = _split_characters(_preprocess(img))
        if not chars:
            return ""
        return "".join(self._match_char(c) for c in chars)

    def recognize_accuracy(self, samples: list[tuple[bytes, str]]) -> float:
        """批量评估准确率。"""
        if not samples:
            return 0.0
        correct = sum(1 for img, label in samples if self.recognize(img) == label)
        return correct / len(samples)


def recognize_from_file(model_path: str | Path, image_bytes: bytes) -> str:
    """便捷入口：单次识别。"""
    return TemplateRecognizer(model_path).recognize(image_bytes)


def is_valid_captcha_text(text: str, min_len: int = 4, max_len: int = 8) -> bool:
    """验证码文本合理性检查。"""
    return bool(text) and min_len <= len(text) <= max_len and bool(re.match(r"^[A-Za-z0-9]+$", text))
