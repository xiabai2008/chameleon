"""去重：短文本字符相似度 + 长文本 simhash（方案 5.3）。"""

from __future__ import annotations

from difflib import SequenceMatcher

from chameleon.utils.content_hash import is_duplicate as _simhash_duplicate
from chameleon.utils.content_hash import simhash


class Deduplicator:
    """内存去重器：记录已见内容指纹。

    - 短文本（< short_threshold 字符）：SequenceMatcher 相似度 > short_ratio 判重
    - 长文本：64 位 simhash 汉明距离 <= threshold 判重
    """

    def __init__(
        self,
        *,
        threshold: int = 12,
        short_threshold: int = 100,
        short_ratio: float = 0.9,
        capacity: int = 10000,
    ) -> None:
        self.threshold = threshold
        self.short_threshold = short_threshold
        self.short_ratio = short_ratio
        self.capacity = capacity
        self._texts: list[str] = []
        self._hashes: list[int] = []

    def _matches(self, text: str) -> bool:
        if len(text) < self.short_threshold:
            for seen in self._texts:
                if len(seen) < self.short_threshold and SequenceMatcher(None, text, seen).ratio() > self.short_ratio:
                    return True
            return False
        h = simhash(text)
        return any(_simhash_duplicate(h, seen_hash, self.threshold) for seen_hash in self._hashes)

    def is_duplicate(self, text: str) -> bool:
        if not text.strip():
            return True
        return self._matches(text)

    def add(self, text: str) -> bool:
        """添加内容；若已存在返回 True（重复）。"""
        if not text.strip():
            return True
        if self._matches(text):
            return True
        if len(text) < self.short_threshold:
            self._texts.append(text)
            if len(self._texts) > self.capacity:
                self._texts = self._texts[-self.capacity :]
        else:
            self._hashes.append(simhash(text))
            if len(self._hashes) > self.capacity:
                self._hashes = self._hashes[-self.capacity :]
        return False
