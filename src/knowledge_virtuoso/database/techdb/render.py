#!/usr/bin/env python3
"""knowledge_virtuoso.database.techdb.render — 技术库属性表的渲染层。

**只做"行 → 文本"**：入参是 ``catalog.search_tech_attr()`` 返回的行，出参是字符串。
不 import ``mcp``、不读索引、不做 I/O。
"""

__all__ = ["render_techdb_attrs"]


def render_techdb_attrs(rows: list[dict], className: str = "", keyword: str = "") -> str:
    """把 tech 属性行渲染成对齐的表格；无行时按查询条件给出"未找到"提示。

    ``rw`` 在该索引里恒为 ``"?"``，无信息量时不占列。
    """
    if not rows:
        ctx = f"类='{className}'" if className else "全部类"
        ctx += f" keyword='{keyword}'" if keyword else ""
        return f"未找到匹配 {ctx} 的 tech 属性。"
    show_rw = any(r["rw"] != "?" for r in rows)
    lines = [f"匹配 {len(rows)} 个 tech 属性:"]
    if show_rw:
        lines.append(f"  {'name':25s} {'rw':2s} {'type':10s} 所属类")
        lines.append(f"  {'-'*25} {'-'*2} {'-'*10} {'-'*30}")
    else:
        lines.append(f"  {'name':25s} {'type':10s} 所属类")
        lines.append(f"  {'-'*25} {'-'*10} {'-'*30}")
    for r in rows:
        if show_rw:
            lines.append(f"  {r['name']:25s} {r['rw']:2s} {r['type']:10s} {','.join(r['classes'])}")
        else:
            lines.append(f"  {r['name']:25s} {r['type']:10s} {','.join(r['classes'])}")
    return "\n".join(lines)
