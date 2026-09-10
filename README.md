# 六爻助手 · Codex 插件与本地 MCP

让你正在使用的 AI 按资料检索六爻理法、象法和卦例，并提供可回查的出处。程序负责排盘和查库，AI 负责理解问题、筛选资料和组织分析。

- **预建数据库**：六份资料，保留原文、校订记录、盘面核对状态与出处；实际数量以随包发行清单为准。
- **使用RAG查询卦理**：AI结合问题、盘面和已有证据，从多个角度按需检索、补查与去重。
- **本地排盘与检索**：下载完成后离线运行，无需额外模型或API Key；接入端AI按其原有方式运行。
- **可直接展示的排盘**：本变卦并排，包含六神、伏神、纳甲六亲、动爻、世应、干支与农历。
- **象法目录与场景检索**：按原书PDF核对目录，支持跨章节查场景、按目录范围查用法与案例，并回查章首条件。

**建议使用GPT-6 Astra Max 使用本插件**

默认提供中文BM25＋六爻结构匹配。配置本地语义模型后可启用真实SQLite混合检索；CPU神经重排是显式可选模式，默认安装不会下载BGE模型。配置及性能边界见[检索与资料验收流程](docs/检索与资料验收流程.md)和[CPU检索性能与扩容](docs/CPU检索性能与扩容.md)。

## 安装到 Codex

需要可用的 **Codex CLI** 和 **uv**。先按[uv官方说明](https://docs.astral.sh/uv/getting-started/installation/)安装uv，在新终端确认 `codex --version`、`uvx --version` 能运行。

**Windows推荐入口**：从[最新Release](https://github.com/zhishengyk/liuyao/releases/latest)下载 `install.ps1`，在下载目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

它会注册GitHub插件目录，下载对应预建包，完成离线自检，再安装插件。**不需要克隆源码仓库、手工修改JSON或重新建库。** 安装后由Codex更新插件，新版程序与数据库在首次启动时自动下载，日常复用缓存，无需为每次升级重新运行脚本。

也可以手动安装对应发行版。以下0.6.6命令须以对应Release的wheel实际可用为前提；候选测试请使用已核验的本地wheel路径：

```powershell
uvx --python 3.11 --from https://github.com/zhishengyk/liuyao/releases/download/v0.6.6/liuyao_mcp-0.6.6-py3-none-any.whl liuyao-mcp --self-check
codex plugin marketplace add zhishengyk/liuyao --ref main --sparse .agents/plugins --sparse plugins/liuyao-assistant
codex plugin add liuyao-assistant@liuyao
```

在桌面端插件页或Codex CLI的 `/plugins` 中确认“六爻助手”已启用，然后**开启新会话**。如果装过 `liuyao-assistant@personal` 开发版，选择一个来源使用，避免重复入口。安装状态可用 `codex plugin list --json` 查看。

> 按当前[OpenAI插件文档](https://learn.chatgpt.com/docs/plugins)，IDE扩展不支持插件包。VS Code Codex使用下面的直接MCP入口；桌面端/CLI使用插件入口。

### VS Code 或其他 MCP 客户端

先运行上述uvx准备命令，再注册本地服务：

```powershell
codex mcp add liuyao -- uvx --python 3.11 --from https://github.com/zhishengyk/liuyao/releases/download/v0.6.6/liuyao_mcp-0.6.6-py3-none-any.whl liuyao-mcp
```

其他客户端使用相同的 `uvx` 命令和参数，传输选择STDIO。已有开发配置时，清除旧的 `LIUYAO_ROOT`、`LIUYAO_DB` 和仓库 `cwd`。首次下载可以先在终端完成，避免客户端启动超时；MCP初始化说明已包含使用流程，独立Skill可按需安装。

## 怎样提问与起卦

如果你不熟悉如何起卦，请阅读[如何起卦](docs/如何起卦.md)，了解摇卦方法、记录示例与注意事项。

先明确一个问题和时间范围。用三枚相同硬币，固定约定**字面=0，背面=1**，连续摇六次；每次背面个数就是爻值，按先后顺序记为初爻到上爻。输入、排盘计算和卦例JSON统一使用0/1/2/3。

| 每次结果 | 爻值 | 含义 |
| --- | --- | --- |
| 三字 | 0 | 老阴，阴变阳，× |
| 一背两字 | 1 | 少阳，静爻 |
| 两背一字 | 2 | 少阴，静爻 |
| 三背 | 3 | 老阳，阳变阴，○ |

记录起卦时刻和时区，可以按下面格式发送作为参考：

```text
使用六爻助手。
占问：当前项目未来三个月的发展如何？
起卦时间：2026-09-05 01:27，北京时间。
六次背面数（初爻→上爻）：0 1 2 2 1 3。
请展示本变卦排盘，结合问题和盘面从多个角度检索理法与卦例，
比较适用条件，根据已有证据按需调整检索参数、补充查询，并回查关键原文。
```

已有排盘软件时，直接提供六个爻值、动爻、日期或清晰截图；看不清的信息需补充。纯理论问题可以直接问“工作变动如何取用”，不需要起卦。详细步骤、不同记录方式与时区约定见[起卦与排盘指南](docs/起卦与排盘指南.md)。

## 排盘输出示例

下表由程序生成，使用参考截图对应的爻值`0 1 1 2 1 1`；占问使用通用示例。输入按初爻到上爻，显示按上爻到初爻。

**六爻排盘**

占问：当前项目的前景如何？

时间：2026-09-05T01:27:00+08:00　星期六（二〇二六年七月廿四）

干支：丙午年　丙申月　壬午日　辛丑时（旬空：申、酉）

参考神煞：羊刃—子　驿马—申　咸池—卯

| 爻位 | 六神 | 伏神 | 本卦：巽为风（巽宫·六冲） | 动爻 | 变卦：风天小畜（巽宫） |
| --- | --- | --- | --- | --- | --- |
| 上爻 | 白虎 | — | `兄弟辛卯木 ━━━━━━━ 世` | — | `兄弟辛卯木 ━━━━━━━` |
| 五爻 | 螣蛇 | — | `子孙辛巳火 ━━━━━━━` | — | `子孙辛巳火 ━━━━━━━` |
| 四爻 | 勾陈 | — | `妻财辛未土 ━━━　━━━` | — | `妻财辛未土 ━━━　━━━ 应` |
| 三爻 | 朱雀 | — | `官鬼辛酉金 ━━━━━━━ 应` | — | `妻财甲辰土 ━━━━━━━` |
| 二爻 | 青龙 | — | `父母辛亥水 ━━━━━━━` | — | `兄弟甲寅木 ━━━━━━━` |
| 初爻 | 玄武 | — | `妻财辛丑土 ━━━　━━━` | × → | `父母甲子水 ━━━━━━━ 世` |

×：老阴变阳；○：老阳变阴。输入爻值从初爻到上爻，表格从上爻到初爻展示。

变卦六亲沿用本卦宫五行，变卦世应按其自身八宫位置标注。神煞不代替取用与理法判断。

排盘工具返回结构化JSON及 `display.markdown`；AI可以直接展示表格，不必重新计算或手写纳甲。

查明取用依据后，AI可分别选择显爻、同位伏神或实际动爻所化的变爻，使用各自的旬空与日月关系核查组合条件；相似卦例也保留不同层的候选。详见[取用与排盘指南](docs/起卦与排盘指南.md#显爻伏神和变爻取用)。

## 资料如何进入分析

检索条件和资料字段修复不等于预测准确率提升。0.6.4的8例成对试验没有观察到检索带来主方向增益，结果及边界见[完整评测记录](docs/评测结果-0.6.4.md)；这些冻结预测不覆盖0.6.5新增的分层用神接口。

```mermaid
flowchart TD
    subgraph Build["离线建库：资料更新时执行"]
        Books["已确定的6份资料"] --> Parse["自动解析、去重、保留出处"]
        Parse --> Rules["理法与象法知识块"]
        Parse --> Cases["结构化卦例 JSON"]
        PDF["象法PDF目录核对"] --> OutlineDB["目录节点、用法与案例关联"]
        OutlineDB --> DB
        Rules --> DB[("SQLite知识库与检索索引")]
        Cases --> DB
    end
    DB --> Release["GitHub Release：预建数据库与程序"]
    Release --> Local[("用户本地知识库")]
    subgraph Use["使用时：MCP本地查询，AI按客户端方式运行"]
        User["问题、六次爻值、起卦时间"] --> AI["ChatGPT / Codex 理解问题"]
        AI --> Chart["MCP 排盘"]
        Chart --> Facts["盘面事实与检索条件"]
        Facts --> RuleSearch["理法与象法检索"]
        Facts --> CaseSearch["相似卦例检索"]
        AI --> Outline["MCP get_outline：浏览象法目录"]
        Outline --> RuleSearch
        Outline --> CaseSearch
        RuleSearch --> Merge["MCP排序、去重、返回证据"]
        CaseSearch --> Merge
        Merge --> Evidence["相关论述与卦例，附原文与出处"]
        Evidence --> Review["AI比较条件、筛选证据"]
        Facts --> Review
        Review --> Answer["带依据、差异与未知项的分析"]
        Review -->|"缺少依据：换角度补查"| Facts
        Review -->|"核对关键原文"| Source["MCP get_source"]
        Source --> Review
    end
    Local --> RuleSearch
    Local --> CaseSearch
    Local --> Source
    Local --> Outline
```

图中的检索包括两路：论述回答“应参考哪些规则”，卦例回答“有哪些可比较的盘面与解释”。AI结合占问、六亲、世应、动爻、空破及已找到的证据，选择查询角度，并按需要调整返回数量、过滤条件和补查范围。读取候选后再判断适用性；相同卦名、相同结论或较高检索分数都不等于可直接照搬。新卦仅作为查询，不自动写入历史案例库。

检索数量由AI每次主动选择：简单问题少量起查，复杂问题或证据有分歧时扩查，并排除已读条目。论述和卦例没有固定配额；关键判断有适用原文支持、重要分歧已核对后停止，资料不足则明确说明。

象法采用原书目录与场景检索：`get_outline`浏览册、章、节和用法，`search_knowledge(method="xiangfa")`按场景查询，`outline_ids`可限定某个目录及其后代。象法模式不按事项大类过滤；`get_source`补充目录上下文和关联案例。详见[PDF核对目录](docs/六爻象法进阶目录.md)与[接口说明](docs/象法目录与场景索引方案.md)。

## 更新

**Codex自带Git插件自动更新。** 已核对本机Codex CLI 0.153.0对应源码：启动任务会检查已配置的Git插件目录，发现更新后也会刷新已安装插件的缓存。我们采用这一原生机制，无需另写插件更新器。这是启动时的检查，不代表GitHub推送后客户端立即更新，也不保证客户端一直开启时定时轮询。[Codex 0.153.0实现](https://github.com/openai/codex/blob/rust-v0.153.0/codex-rs/core-plugins/src/manager.rs#L2735-L2939)

从0.4.1起，插件直接启动固定版本的wheel发行包：**Codex更新插件 → 首次启动自动下载新版程序和数据库 → 后续使用本地缓存。** 不需要为每次更新运行安装脚本。首次下载需要联网，插件预留180秒启动时间；下载完成后的排盘、检索和原文回查均在本机执行。[uv缓存机制](https://docs.astral.sh/uv/concepts/tools/#tool-versions)

已缓存版本可离线使用；新版首次下载失败或超时时，恢复网络后重新连接MCP即可重试。配置已指向未缓存的新版本，或uv缓存被清理时，需要联网下载，当前不会自动回退到旧包。直接注册固定URL的MCP以及personal本机开发来源，不随这个Git插件目录自动升级。

[插件安装与分发](docs/Codex插件接入与分发.md) · [发布与版本管理](docs/发布与版本管理.md)

## 开发与验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m liuyao_mcp.evaluate
.\.venv\Scripts\python.exe scripts/build_release.py
```

默认源码安装不下载推理模型。`-InstallPlugin`安装本机开发版；`-RegisterMcp`注册开发MCP。向量相关代码与依赖单独保留，实验边界见[实施验收](docs/实施验收.md)。

## 资料与边界

首批资料为《六爻预测自修宝典》《王虎应增删卜易评释》《增删卜易》《六爻理法进阶》《六爻象法进阶》上、下，共六份文件，清单及哈希见[data/sources.jsonl](data/sources.jsonl)。候选卦例可能存在OCR错误、字段缺失和原书排盘冲突，工具会保留问题，不把候选数量当作已核验数量。历史反馈是原作者的记载，不等于独立验证或未来预测保证。

原始资料归档包含1,862个Markdown文件，保留原目录结构：[资料目录](Markdown归档/README.md)。原始文档、图片、音频和转换附件未上传；旧文档中的本地图片链接可能无法在GitHub显示。
