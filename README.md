# 六爻 MCP 助手与资料归档

为 ChatGPT 桌面端和 VS Code Codex 提供只读排盘、理法/象法检索、结构化卦例与原文回查。在线服务不调用生成模型，新卦仅作为查询，不会自动加入历史案例库。

## uvx 安装（发布版）

先[安装 uv](https://docs.astral.sh/uv/getting-started/installation/)，确认终端能运行 `uvx --version`。GitHub Release 发布后，在 Codex 注册一次：

```powershell
codex mcp add liuyao -- uvx --python 3.11 --refresh-package liuyao-mcp --from https://github.com/zhishengyk/liuyao/releases/latest/download/liuyao-mcp.tar.gz liuyao-mcp
```

服务自带预建知识库和原文，无需下载源码、配置绝对路径或手动建库。首次启动需要联网准备 Python、依赖和安装包；客户端启动超时建议设为 180 秒。已有 `liuyao` 服务时替换其 command/args，清除旧的 `LIUYAO_ROOT`、`LIUYAO_DB` 和 cwd。直接 MCP 与插件选择一个入口即可。

通用 STDIO 配置：command 为 `uvx`，args 见 `plugins/liuyao-assistant/.mcp.json`。无需环境变量。可先将相同 uvx 命令末尾加 `--version` 运行一次，完成下载并确认版本。

每次重新启动服务，`--refresh-package liuyao-mcp` 会重新验证发布包缓存；GitHub latest 指向新版后自动获取新版。运行中的服务不会热更新。这是 GitHub 分发，尚未发布到 PyPI，不能直接使用 `uvx liuyao-mcp@latest`。

固定版本或回退：将 URL 中的 `releases/latest/download` 改成 `releases/download/v0.2.0`，并移除 `--refresh-package liuyao-mcp`。版本号可通过 `liuyao-mcp --version` 查询。

[发布与版本管理](docs/发布与版本管理.md)

## 从源码安装（开发用，Windows）

需要 Python 3.11+。默认安装脚本使用 `py -3.11`；也可传 `-Python C:\Python314\python.exe`。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
```

自动建立 `.venv`、安装依赖、处理 `data/sources.jsonl` 中的六份资料，并生成 `.local/mcp-config.toml`。如需同时注册到本机 Codex，增加 `-RegisterMcp`。脚本通过 `codex mcp add liuyao` 增加本服务，保留其他服务设置；若已有同名服务，应先核对配置。

希望在插件目录看到“六爻助手”时，增加 `-InstallPlugin`。此步骤使用本机 Codex 自带的 plugin-creator 安装辅助脚本，复制插件包并生成适合本机的绝对启动路径，再安装到个人 marketplace。源码中的 `plugins/liuyao-assistant` 是分发模板，安装后的副本位于个人插件目录；更新后在新会话中测试。直接MCP配置和插件安装是两种入口，无需重复启用同一个服务。

ChatGPT 桌面端：Settings → MCP servers → Add server。VS Code Codex：齿轮菜单 → MCP servers → Add server。选择 STDIO，按生成的配置填入解释器命令、模块参数和环境变量，保存后重启客户端或扩展，在新会话中使用。相同 Codex 主机可共用配置。

## 使用

在客户端启用六爻服务后，可以提问：

> 使用六爻助手，查询工作占问遇用神旬空时的理法，分别给出12条论述和8个相关卦例，并注明原文出处。

> 我的六爻从初爻到上爻是8、8、8、8、8、8，卯月庚子日，问感情。先排盘，再查取用依据和相似卦例，说明原文冲突和未知信息。

- `build_chart`：6老阴、7少阳、8少阴、9老阳，输入顺序为初爻到上爻。可输入完整时间或历史月支、日干支。历法口径为北京时间、节气换月、零点换日。
- `search_knowledge`：`kind=rule/case`，默认12条论述/8个案例；`method=lifa/xiangfa/all`。`limit`可提高到20/12等；`exclude_ids`补查去重，`exclude_case_ids`隔离测试案例，`features`做结构匹配。
- `get_source`：用证据ID回查原文及案例JSON；`context_lines`补前后文，超长原文按`next_offset`继续读取。

## 产物与验证

```powershell
.\.venv\Scripts\python.exe -m liuyao_mcp.ingest
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m liuyao_mcp.evaluate
```

产物为 `data/knowledge.sqlite`、`data/cases.jsonl`、`data/ingest_report.json` 与 `data/eval/`。这些均可重建；来源文件和清单哈希用于追溯。检索基线为 BM25＋结构字段匹配，Dense与reranker未默认启用。自动评测报告使用来源锚点代理指标，不代表人工相关性判断或预测准确率。

自动抽取区分可解析、部分缺失和原文冲突。OCR文本、旧书排盘和反馈未经过独立真实性验证；作者断语、实际反馈、程序重算和AI新分析分别保存。

[落地方案](docs/六爻MCP落地方案.md) · [实施验收](docs/实施验收.md)

## 原有资料归档说明

[进入资料目录](Markdown归档/README.md)

本仓库收录本地资料转换得到的全部 1,862 个 Markdown 文件，保留归档目录结构。

最初归档提交仅包含 Markdown；现在仓库同时包含 MCP 源码、配置和测试，预建数据库通过 Release 安装包分发。原始文档、图片、音频和归档转换附件未上传。文档中的本地图片链接在 GitHub 上无法显示；需要核对原图时，请使用完整的本地归档。归档内有关完整性校验及附件的说明描述的是本地完整版。

OCR 文本可能存在识别错误，专业术语、数字和复杂图表请对照原始资料核对。
