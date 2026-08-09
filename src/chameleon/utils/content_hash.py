"""内容指纹：simhash 用于去重与相似度判断。"""

from __future__ import annotations

import hashlib
import re

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]{2,}", re.UNICODE)
_HASH_BITS = 64


def _token_hashes(text: str, window: int = 4) -> list[int]:
    tokens = _TOKEN_RE.findall(text.lower())
    hashes: list[int] = []
    for i in range(len(tokens)):
        if window > 1 and i + window <= len(tokens):
            gram = " ".join(tokens[i : i + window])
        else:
            gram = tokens[i]
        hashes.append(int.from_bytes(hashlib.md5(gram.encode("utf-8")).digest()[:8], "big"))
    return hashes


def simhash(text: str, window: int = 4) -> int:
    """计算 64 位 simhash。"""
    vectors = [0] * _HASH_BITS
    for h in _token_hashes(text, window):
        for i in range(_HASH_BITS):
            vectors[i] += 1 if (h >> i) & 1 else -1
    result = 0
    for i in range(_HASH_BITS):
        if vectors[i] > 0:
            result |= 1 << i
    return result


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def is_duplicate(a: int, b: int, threshold: int = 6) -> bool:
    """simhash 距离 <= threshold 视为重复。"""
    return hamming_distance(a, b) <= threshold
