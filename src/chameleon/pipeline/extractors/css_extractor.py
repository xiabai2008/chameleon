"""CSS 选择器提取（selectolax）：JSON Schema 中 css 指令描述。"""

from __future__ import annotations

from typing import Any

from selectolax.parser import HTMLParser, Node

from chameleon.pipeline.extractors.base import BaseExtractor

_NodeLike = Node | HTMLParser


def _node_value(node: _NodeLike, attr: str | None) -> Any:
    if attr == "html":
        return node.html
    if attr == "text" or attr is None:
        return node.text(separator=" ", strip=True)
    attributes = getattr(node, "attributes", None)
    if isinstance(attributes, dict):
        return attributes.get(attr)
    return None


def _extract_prop(node: _NodeLike, prop: dict[str, Any], base_url: str) -> Any:
    if "css" not in prop:
        return None
    if "items" in prop:
        container = node.css_first(prop["css"])
        if container is None:
            return None
        return _extract_array(container, prop["items"], base_url)
    target = node.css_first(prop["css"])
    if target is None:
        return None
    if "properties" in prop:
        return _extract_node(target, prop, base_url)
    return _node_value(target, prop.get("attr"))


def _extract_array(container: Node, items: dict[str, Any], base_url: str) -> list[Any]:
    item_css = items.get("css") or "li, tr, article, .item"
    return [_extract_node(child, items, base_url) for child in container.css(item_css)]


def _extract_node(node: _NodeLike, schema: dict[str, Any], base_url: str) -> Any:  # noqa: ANN401
    """从节点提取。schema 带 properties 时提取对象；否则取节点自身值。"""
    properties = schema.get("properties")
    if properties:
        result: dict[str, Any] = {}
        for name, prop in properties.items():
            value = _extract_prop(node, prop, base_url)
            if value is not None:
                result[name] = value
        return result
    if schema.get("css"):
        target = node.css_first(schema["css"])
        if target is None:
            return None
        return _node_value(target, schema.get("attr"))
    return _node_value(node, schema.get("attr"))


class CssExtractor(BaseExtractor):
    """基于 CSS 选择器的结构化提取。

    Schema 约定（兼容 Crawl4AI JsonCssExtractionStrategy）：
    {
      "type": "object",
      "properties": {
        "title": {"type": "string", "css": "h1"},
        "price": {"type": "string", "css": "span.price"},
        "link": {"type": "string", "css": "a.buy", "attr": "href"},
        "items": {
          "type": "array",
          "css": "ul.products",
          "items": {"type": "object", "css": "li",
                    "properties": {"name": {"type": "string", "css": "h2"}}}
        }
      }
    }
    """

    name = "css"

    async def extract(self, html: str, schema: dict[str, Any], base_url: str = "") -> dict[str, Any]:
        tree = HTMLParser(html)
        node: _NodeLike = tree
        if tree.body is not None:
            node = tree.body
        result = _extract_node(node, schema, base_url)
        if not isinstance(result, dict):
            result = {}
        return result


class XPathExtractor(BaseExtractor):
    """基于 XPath 的结构化提取（lxml）。schema 中 xpath 指令描述。"""

    name = "xpath"

    async def extract(self, html: str, schema: dict[str, Any], base_url: str = "") -> dict[str, Any]:
        from lxml import html as lxml_html  # type: ignore[import-untyped]

        tree = lxml_html.fromstring(html)
        result = self._extract_node(tree, schema)
        if not isinstance(result, dict):
            result = {}
        return result

    def _extract_node(self, node: Any, schema: dict[str, Any]) -> Any:
        properties = schema.get("properties")
        if properties:
            result: dict[str, Any] = {}
            for name, prop in properties.items():
                value = self._extract_prop(node, prop)
                if value is not None:
                    result[name] = value
            return result
        return node.text_content().strip() if node.text_content() else None

    def _extract_prop(self, node: Any, prop: dict[str, Any]) -> Any:
        if "xpath" not in prop:
            return None
        nodes = node.xpath(prop["xpath"])
        if not nodes:
            return None
        if "items" in prop:
            return [self._extract_node(n, prop["items"]) for n in nodes]
        target = nodes[0]
        if isinstance(target, str):
            return target
        if prop.get("attr"):
            return target.get(prop["attr"])
        return target.text_content().strip() if target.text_content() else None
