#!/usr/bin/env python3
"""knowledge_virtuoso.database.db.render — 设计库属性表的渲染层。

**只做"行 → 文本"**：入参是 ``catalog.search_attr()`` 返回的行，出参是字符串。
不 import ``mcp``、不读索引、不做 I/O。列宽与描述截断（60 字）都属于本库的表示，
改它不影响别的库。
"""

__all__ = ["render_db_attrs"]


def render_db_attrs(rows: list[dict], objType: str = "", keyword: str = "") -> str:
    """把属性行渲染成对齐的表格；无行时按查询条件给出"未找到"提示。"""
    if not rows:
        ctx = f"objType='{objType}'" if objType else "全部类型"
        ctx += f" keyword='{keyword}'" if keyword else ""
        return f"未找到匹配 {ctx} 的属性。"
    lines = [f"匹配 {len(rows)} 个属性:"]
    lines.append(f"  {'name':25s} {'rw':4s} {'type':15s} desc")
    lines.append(f"  {'-'*25} {'-'*4} {'-'*15} {'-'*30}")
    for r in rows:
        desc = r["desc"] if len(r["desc"]) <= 60 else r["desc"][:59] + "…"
        lines.append(f"  {r['name']:25s} {r['rw']:4s} {r['type']:15s} {desc}")
    return "\n".join(lines)
