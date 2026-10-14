# 官方 doc 的 HTML 片段（解析器夹具）

由 `tests/capture_official_html.py` 从本机官方 doc 切出，**只留判别特征 + 够解析的
上下文**：`topic/` 是一个 topic 的正文（两个标记之间），`page/` 覆盖整个标记区间。
每份片段对应解析器的一个格式族（族的清单见 `tests/README.md`「片段夹具覆盖的格式族」）。

每份 `.html` 旁边有一份同名 `.json`，是**线上索引里的那条记录**（写法与
`capture_fixtures.py` 一致）：片段单独喂解析器，产出的 `decl`/`sections`/
`field_status`/`status` 必须与之逐字段相同——夹具自足与解析口径两条一起管。

| 片段 | 体积 | 源文件（doc 根下） | 覆盖的格式族 |
|---|---|---|---|
| `topic/hiSetCursor.html` + `.json` | 53.0 KB | `skuiref/chap9.html` | C7 裸 <tr> 续排的大表（全库独一份） |
| `topic/rodCreatePath.html` + `.json` | 151.6 KB | `rodskillref/chap1.html` | B3 节内子范围标题 + C2 超长声明 + C10 子参数列表 + D2 编号步骤表 |
| `topic/error.html` + `.json` | 3.4 KB | `sklangref/funcprog.html` | B3 合并标题（Arguments<br>Values Returned）+ D3 返回节只有散文 |
| `topic/evalstring.html` + `.json` | 4.6 KB | `sklangref/funcprog.html` | C9 允许取值表（'symbol 行） |
| `topic/pcreCompile.html` + `.json` | 14.2 KB | `sklangref/stringfunc.html` | C4 首列被占位的续排行（名称一行、说明下一行） |
| `topic/gdmstatus.html` + `.json` | 21.3 KB | `caiskill/gdm.html` | C4/C5 首列被占位 + 名称与说明同格 |
| `topic/absAbstract.html` + `.json` | 127.2 KB | `sklayoutref/abs.html` | B4 documented_none + E4 option_descriptions 大字典 |
| `topic/awvCreateBus.html` + `.json` | 2.8 KB | `oceanref/chap10.html` | E3 description 缺失、只有 definition |
| `topic/asiMapInstanceName.html` + `.json` | 3.3 KB | `skartistref/chap16.html` | B2 官方笔误标题 value returned\ |
| `page/ccpGetAutoRename.html` + `.json` | 19.3 KB | `caiskill/cdsCopy.html` | A1 标记协议 + A2 一个标记含多个函数标题 |
| `page/caaar.html` + `.json` | 5.5 KB | `sklangref/list.html` | A3 名字在散文里列出 + F5 共享声明（取同 topic 的 <dl>） |
| **合计** | **406.4 KB** | | |

**这是 Cadence 官方文档的原文摘录**：进公开仓库前请确认符合其许可；要缩小暴露就
减少族、或在切法上再删上下文（改 `TEST_TARGETS` 与切法，重跑采集脚本即可）。

