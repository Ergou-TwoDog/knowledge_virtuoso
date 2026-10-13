#!/usr/bin/env python3
"""knowledge_virtuoso.database.cdfdb.render — CDF 属性表的渲染层。

**只做"行 → 文本"**：入参是 ``catalog.search_cdf_attr()`` 返回的行，出参是字符串。
不 import ``mcp``、不读索引、不做 I/O。描述截断（55 字）是本库自己的表示。
"""

__all__ = ["render_cdfdb_attrs"]


def render_cdfdb_attrs(rows: list[dict], className: str = "", keyword: str = "") -> str:
    """把 CDF 属性行渲染成对齐的表格；无行时按查询条件给出"未找到"提示。"""
    if not rows:
        ctx = f"类='{className}'" if className else "全部类"
        ctx += f" keyword='{keyword}'" if keyword else ""
        return f"未找到匹配 {ctx} 的 CDF 属性。"
    lines = [f"匹配 {len(rows)} 个 CDF 属性:"]
    lines.append(f"  {'name':25s} {'rw':4s} {'type':10s} desc")
    lines.append(f"  {'-'*25} {'-'*4} {'-'*10} {'-'*40}")
    for r in rows:
        desc = r["desc"] if len(r["desc"]) <= 55 else r["desc"][:54] + "…"
        lines.append(f"  {r['name']:25s} {r['rw']:4s} {r['type']:10s} {desc}")
    return "\n".join(lines)
