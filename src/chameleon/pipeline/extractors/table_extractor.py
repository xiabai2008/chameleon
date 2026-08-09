"""表格语义抽取：HTML table → 结构化 JSON（方案 P8-7 表格语义抽取）。"""

from __future__ import annotations

from typing import Any

from selectolax.parser import HTMLParser, Node

from chameleon.pipeline.extractors.base import BaseExtractor


def extract_tables(html: str) -> list[dict[str, Any]]:
    """解析所有 table 元素，输出 [{headers, rows}]。

    - headers: thead/th 首行
    - rows: 数据行列表（dict 或 list）
    """
    tree = HTMLParser(html)
    tables: list[dict[str, Any]] = []
    for table in tree.css("table"):
        parsed = _parse_table(table)
        if parsed is not None:
            tables.append(parsed)
    return tables


def _parse_table(table: Node) -> dict[str, Any] | None:
    rows_nodes = table.css("tr")
    if not rows_nodes:
        return None
    all_rows: list[list[str]] = []
    headers: list[str] | None = None
    for row in rows_nodes:
        cells = row.css("th, td")
        values = [cell.text(separator=" ", strip=True) for cell in cells]
        if not any(v for v in values):
            continue
        th_cells = row.css("th")
        if th_cells and len(th_cells) == len(cells):
            # 整行都是 th：视为表头
            if headers is None:
                headers = values
            continue
        all_rows.append(values)

    # 无显式 th 表头时，首行作为表头（仅当列数匹配）
    if headers is None and all_rows and len(all_rows) >= 2:
        headers = all_rows[0]
        all_rows = all_rows[1:]

    if headers and len(all_rows) >= 1 and len(all_rows[0]) == len(headers):
        rows = [dict(zip(headers, row, strict=False)) for row in all_rows]
        return {"headers": headers, "rows": rows}
    return {"headers": headers or [], "rows": all_rows}


class TableExtractor(BaseExtractor):
    """表格提取策略：schema 支持 css（table 选择器，默认全部 table）。"""

    name = "table"

    async def extract(self, html: str, schema: dict[str, Any], base_url: str = "") -> dict[str, Any]:
        tables = extract_tables(html)
        if not tables:
            return {}
        selector = schema.get("css")
        if selector:
            tree = HTMLParser(html)
            matched: list[dict[str, Any]] = []
            for table in tree.css(selector):
                parsed = _parse_table(table)
                if parsed is not None:
                    matched.append(parsed)
            if matched:
                return {"tables": matched}
        return {"tables": tables}
