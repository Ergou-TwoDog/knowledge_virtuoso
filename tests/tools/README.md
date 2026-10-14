# tools：夹具生成器（**不是测试**）

这里的东西**不断言任何东西**，只从本机材料把夹具重新生成出来，所以不该混进镜像树里
（它们一个脚本跨好几个镜像目录写文件）。`run_tests.py` 不会发现它们。

```bash
uv run python -B tests/tools/capture_fixtures.py        # 记录：索引里的真实记录（需本机索引）
uv run python -B tests/tools/capture_official_html.py   # 切片：函数库解析器的 HTML 片段（需本机 doc）
uv run python -B tests/tools/capture_attrs_html.py      # 切片：四个属性库解析器的 HTML 片段（同上）
```

| 脚本 | 生成什么 | 什么时候跑 |
|---|---|---|
| `capture_fixtures.py` | `…/official/fixtures/<记录名>.json`（线上索引里的记录）与四个属性库 `cases/<用例>.json` 的 `rows` | 记录契约变了、或要新增用例 |
| `capture_official_html.py` | `…/official/fixtures/html/{topic,page}/<函数>.{html,json}` + 该目录 README | 要加/改函数库解析器的格式族 |
| `capture_attrs_html.py` | `…/database/<库>/core/fixtures/html/<片段>.{html,json}` + 各库 README | 同上，属性库 |

三条规矩：

1. **夹具由脚本写，不手工编辑**（要改就改脚本里的目标清单再重跑）——出处与体积因此不会和
   文件对不上。
2. **重跑后先看 `git diff --stat`**：体积异常膨胀、或与预期不符的改动，说明切法选错了。
3. **期望值分两类，别混**：`golden/*.txt` 是"当前输出"，可以 `--update` 重录；`fixtures/html/*.json`
   是"正解/线上记录"，**不该被重录**——所以它跟着输入放，不放进 `golden/`。
