"""工具函数测试。"""

from chameleon.utils.content_hash import hamming_distance, is_duplicate, simhash
from chameleon.utils.encoding import decode_html, normalize_newlines
from chameleon.utils.url_utils import (
    hostname,
    is_same_domain,
    is_subdomain,
    normalize_url,
    resolve_url,
)


def test_decode_utf8() -> None:
    raw = "你好 Chameleon".encode()
    assert decode_html(raw) == "你好 Chameleon"


def test_decode_gbk_via_meta() -> None:
    html = '<html><head><meta charset="gbk"></head><body>中文内容</body></html>'
    raw = html.encode("gbk")
    assert decode_html(raw) == html


def test_decode_gbk_via_headers() -> None:
    raw = "中文内容".encode("gbk")
    assert decode_html(raw, headers={"content-type": "text/html; charset=gbk"}) == "中文内容"


def test_normalize_newlines() -> None:
    assert normalize_newlines("a\r\nb\rc") == "a\nb\nc"


def test_normalize_url() -> None:
    assert normalize_url("HTTPS://Example.com/A?utm_source=x#frag") == "https://example.com/A"
    assert normalize_url("https://example.com/a?b=1&utm_source=x") == "https://example.com/a?b=1"


def test_resolve_url() -> None:
    assert resolve_url("https://example.com/a/b", "../c") == "https://example.com/c"
    assert resolve_url("https://example.com", "/x") == "https://example.com/x"
    assert resolve_url("https://example.com", "javascript:void(0)") is None


def test_domain_utils() -> None:
    assert hostname("https://Sub.Example.COM/path") == "sub.example.com"
    assert is_same_domain("https://a.com/x", "https://a.com/y")
    assert not is_same_domain("https://a.com", "https://b.com")
    assert is_subdomain("https://news.a.com", "a.com")
    assert is_subdomain("https://a.com", "a.com")
    assert not is_subdomain("https://nota.com", "a.com")


def test_simhash_duplicate_detection() -> None:
    a = simhash("这是第一段用于测试的文本内容，包含一些关键词")
    b = simhash("这是第一段用于测试的文本内容，包含一些关键词。")
    c = simhash("完全不同的内容：关于天气、股票和足球比赛的新闻")

    assert is_duplicate(a, b)
    assert not is_duplicate(a, c)
    assert hamming_distance(a, a) == 0
