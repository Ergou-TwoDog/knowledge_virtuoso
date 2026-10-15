#!/usr/bin/env python3
"""真实 MCP stdio 冒烟：`src/knowledge_virtuoso/server.py` 的接线。

渲染回归覆盖不到服务入口——哪个工具查哪张索引、参数怎么转给渲染层，只有真起一次才看得见。
这里把服务当**子进程**起起来、走真实 MCP 协议、列工具并逐个调用。

两种跑法：

```bash
uv run python -B tests/knowledge_virtuoso/test_server.py   # 独立跑：打每个调用的明细
uv run python -B tests/run_tests.py server                 # 测试网里跑：静默，结果变成断言
```

**本机没有索引时**（没设 `VIRTUOSO_DATA_DIR`、平台目录也没有，且没设 `VIRTUOSO_DOC_DIR`）
协议与工具列表照验，查询会明确报"索引不可用"——那种情况记一条 **SKIP**（不算失败，但会在
汇总里露面，免得把"没验到"读成"验过了"）。

子进程用 `sys.executable -B -m knowledge_virtuoso` 起（不再过一次 uv：这里要验的是服务本身）。
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys

TESTS = pathlib.Path(__file__).resolve().parents[1]          # tests/
REPO = TESTS.parent                                          # 仓库根（子进程的工作目录）
sys.path.insert(0, str(TESTS))

from common import Report  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# 每个工具至少走一次，参数取各自文档里的例子。
CALLS = (
    ("skill_language_search_doc", {"func_name": "dbCreateRect", "detail": "brief"}),
    ("skill_language_search_doc", {"func_name": "rodCreatePath", "detail": "skel"}),
    ("skill_language_search_components", {"prefix": "tech", "keywords": "find via def"}),
    # 属性查询是**一个工具**：四个库各走一次（`lib` 选库），再一次不给 `lib` 走跨库。
    ("search_attr", {"lib": "db", "object": "rect", "keyword": "bBox"}),
    ("search_attr", {"lib": "techdb", "object": "viaDefs"}),
    ("search_attr", {"lib": "cdfdb", "object": "cdfParamId", "keyword": "value"}),
    ("search_attr", {"lib": "dd", "object": "cellFile"}),
    ("search_attr", {"object": "rect"}),
)

# 属性工具的参数名——**这是会静默坏掉的一道缝**：名字注册错了，工具照样出现在列表里，
# 但每次调用都会因为 schema 不符而失败。合并成一个工具后，四库共用的选择器参数叫 `object`
# （各库不再有自己的参数名；额外认哪些写法见各库 `DOC` 与 `LIB.aliases`）。
ATTR_TOOL = "search_attr"
ATTR_PARAMS = {"lib", "object", "keyword"}

# 这几次 `search_attr` 调用的**第一行**应该是什么：
#   * 单库命中 → 对象头（回显解析到的对象；给的还是别名 `rect`）；
#   * 跨库      → 节首 `── <库名> ──`（`rect` 只有 db 认得，所以只出一节）。
# dd 那次也有——它的对象记录里除 `id` 全是空的，所以对象头只有 `对象 cellFile`。
ECHOES = (
    ({"lib": "db", "object": "rect", "keyword": "bBox"}, "对象 Rectangle"),
    ({"lib": "techdb", "object": "viaDefs"}, "对象 viaDefs"),
    ({"lib": "cdfdb", "object": "cdfParamId", "keyword": "value"}, "对象 cdfParamId"),
    ({"object": "rect"}, "── db ──"),
    ({"lib": "dd", "object": "cellFile"}, "对象 cellFile"),
)

# 索引缺失时服务会报这些字样——那是环境问题（没索引也没 doc），不是服务坏了。
INDEX_HINTS = ("索引不可用", "IndexLoadError", "请重建索引", "重建索引", "index JSON unavailable")


async def _smoke(verbose: bool) -> dict:
    """起一次服务、走一遍协议；返回结果字典（`verbose` 时顺带打明细）。"""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    def say(line: str) -> None:
        if verbose:
            print(line)

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    params = StdioServerParameters(command=sys.executable, args=["-B", "-m", "knowledge_virtuoso"],
                                   env=env, cwd=str(REPO))

    # 独立跑时把子进程的 stderr 放出来（启动失败要靠它看原因）；测试网里跑则丢进 devnull，
    # 否则服务自己的日志会混进 `run_tests.py` 的报告里。
    sink = None if verbose else open(os.devnull, "w", encoding="utf-8")
    try:
        async with stdio_client(params, errlog=sink or sys.stderr) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = (await session.list_tools()).tools
                tools = sorted(t.name for t in listed)
                tool_params = {t.name: sorted(t.inputSchema.get("properties", {})) for t in listed}
                say(f"工具列表（{len(tools)}）: {', '.join(tools)}")
                missing = sorted({name for name, _ in CALLS} - set(tools))
                if missing:
                    say(f"FAIL 缺工具: {missing}")
                    return {"tools": tools, "toolParams": tool_params, "missing": missing,
                            "failures": [], "verified": 0, "skipped": 0}

                failures: list[str] = []
                # 同一个工具可能被调多次（属性查询就是），所以按**调用**记而不是按工具名记。
                results: list[tuple[str, dict, str]] = []
                skipped = verified = 0
                for name, args in CALLS:
                    result = await session.call_tool(name, args)
                    text = "".join(getattr(block, "text", "") for block in result.content)
                    head = text.splitlines()[0] if text else "(空)"
                    if result.isError and any(hint in text for hint in INDEX_HINTS):
                        skipped += 1
                        say(f"  [skip] {name}  ← 索引不可用（先设 VIRTUOSO_DOC_DIR 或跑构建）")
                    elif result.isError:
                        failures.append(f"{name}({args}) ← {head[:70]}")
                        say(f"  [FAIL] {name}({args})  ← {head[:70]}")
                    else:
                        verified += 1
                        results.append((name, args, head))
                        say(f"  [ok  ] {name}  {len(text)} 字  ← {head[:50]}")
    finally:
        if sink is not None:
            sink.close()

    return {"tools": tools, "toolParams": tool_params, "missing": missing, "failures": failures,
            "verified": verified, "skipped": skipped, "results": results}


async def main() -> int:
    """独立跑（启动 Claude 之前的那条命令）：打明细，返回退出码。"""
    outcome = await _smoke(verbose=True)
    if outcome["missing"]:
        print(f"\nFAIL 缺工具: {outcome['missing']}")
        return 1
    if outcome["failures"]:
        print(f"\nFAIL {len(outcome['failures'])} 次调用报错")
        return 1
    if outcome["skipped"] == len(CALLS):
        print("\nSKIP 协议与工具列表通过，但本机索引不可用，查询未真正验证"
              "（设 VIRTUOSO_DOC_DIR 或运行 knowledge-virtuoso-build <库> 后重跑）")
        return 0
    print(f"\nOK  工具列表与全部调用均通过真实 stdio（跳过 {outcome['skipped']} 次）")
    return 0


def run(report: Report, update: bool = False) -> None:
    """被 `tests/run_tests.py` 调用：静默跑一遍，把结果变成断言。

    索引不可用时查询全部 SKIP——记 `report.skip()`，不算过也不算错，但汇总里会写"跳过 1 次"。
    """
    outcome = asyncio.run(_smoke(verbose=False))
    report.expect("stdio/工具列表齐全（CALLS 里点到的工具都在）", outcome["missing"], [])
    report.expect("stdio/工具列表恰好三个（两个函数库 + 一个属性）",
                  sorted(outcome["tools"]),
                  ["search_attr", "skill_language_search_components",
                   "skill_language_search_doc"])
    report.expect(f"stdio/{ATTR_TOOL} 的参数恰好是 lib / object / keyword",
                  sorted(outcome["toolParams"].get(ATTR_TOOL) or []), sorted(ATTR_PARAMS))
    report.expect("stdio/没有调用报错", outcome["failures"], [])
    if outcome["skipped"] == len(CALLS):
        report.skip("stdio/查询真验过", "本机索引不可用（设 VIRTUOSO_DOC_DIR 或跑构建）")
    else:
        report.expect("stdio/真验过的调用数 = 总数 − 跳过数",
                      outcome["verified"], len(CALLS) - outcome["skipped"])
    # 这两道缝**只有真调用能验**：渲染用例是直接把 obj 喂进去的，接线忘了传照样全绿。
    # 库名与描述由 registry 现场拼，也一并看一眼。
    heads = {(name, repr(sorted(args.items()))): head for name, args, head in outcome["results"]}
    for args, want in ECHOES:
        key = (ATTR_TOOL, repr(sorted(args.items())))
        if key not in heads:
            continue          # 索引不可用被跳过了；上面那条 skip 会说明
        report.truthy(f"stdio/{ATTR_TOOL}({args}) 首行是 {want!r}",
                      heads[key].startswith(want), heads[key][:80])


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
