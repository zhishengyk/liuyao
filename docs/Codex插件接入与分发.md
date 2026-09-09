# Codex插件接入与分发

本项目采用「GitHub插件目录＋Skill＋本地MCP＋预建SQLite」。Codex负责理解问题、筛选候选和引用分析，程序负责排盘、查库和原文回查。安装过程不要求用户重建资料或配置模型API。

## 目录与职责

```text
.agents/plugins/marketplace.json          GitHub插件目录，名称liuyao
plugins/liuyao-assistant/
  .codex-plugin/plugin.json              插件名称、版本和展示信息
  .mcp.json                             固定版本的本地服务启动命令
  skills/interpret-liuyao/SKILL.md        起卦输入、检索、筛选与引用流程
src/liuyao_mcp/                          排盘与检索代码
scripts/install_release.ps1              首次安装与修复入口
```

服务发行包包含`liuyao_mcp/_data/knowledge.sqlite`，原文、知识块、卦例和索引均在库内。用户不需要原始资料目录。插件清单、服务版本和Release地址在发布时一起校验。

## 支持的接入端

| 接入端 | 入口 |
| --- | --- |
| Codex桌面端、CLI | 从GitHub目录安装六爻助手插件 |
| VS Code Codex | 直接配置同一MCP；可另装独立Skill |
| 其他支持STDIO的MCP客户端 | 使用相同uvx命令，首次下载后可离线运行 |

当前官方文档明确IDE扩展不支持插件包；MCP能力与插件包支持范围应分别判断。[插件支持范围](https://learn.chatgpt.com/docs/plugins)、[MCP配置](https://learn.chatgpt.com/docs/extend/mcp)

## 使用者安装与更新

先安装Codex CLI和[uv](https://docs.astral.sh/uv/getting-started/installation/)，在新终端确认`codex --version`及`uvx --version`成功。从[最新Release](https://github.com/zhishengyk/liuyao/releases/latest)下载`install.ps1`，执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

脚本按顺序执行：

1. 添加GitHub目录；已添加时使用`marketplace upgrade liuyao`刷新候选版本。
2. 读取候选插件的`.mcp.json`，准备其中固定版本的服务包和数据库。
3. 以`--offline --self-check`验证本地排盘、12条论述、8个案例和原文回查。
4. 自检成功后才执行`codex plugin add liuyao-assistant@liuyao`。

Codex原生支持Git插件自动更新。已核对本机CLI 0.153.0对应源码：`maybe_start_plugin_startup_tasks_for_config`在启动阶段发起Git目录自动升级；目录有变化时，`refresh_non_curated_plugin_cache_force_reinstall_detailed`也会刷新已安装插件缓存。因此，`marketplace upgrade`不能仅理解成刷新目录列表，手工脚本也不是Codex更新插件的必要条件。[对应版本源码](https://github.com/openai/codex/blob/rust-v0.153.0/codex-rs/core-plugins/src/manager.rs#L2735-L2939)

这是启动时的自动检查，不保证GitHub推送后立即生效或客户端一直开启时定时轮询。本项目复用原生能力，不增加自定义更新器。personal本机开发来源及直接注册固定URL的MCP不随Git插件目录更新。

从0.4.1起，`.mcp.json`使用带版本号的wheel URL，并允许uvx首次下载。Codex更新插件配置后，下一次启动MCP会自动取得对应程序、数据库和依赖，之后复用缓存，用户不需要为每次升级重跑安装脚本。服务预留180秒启动时间；首次下载超时后可重新连接重试。启动新会话以加载新版；必要时重启客户端以刷新PATH和旧MCP进程。

这里使用`liuyao_mcp-<版本>-py3-none-any.whl`，不使用无版本文件名的sdist入口。实测后者即使已缓存也可能联网解析元数据，而版本化wheel在阻断HTTP/HTTPS代理后仍能启动并完成三个MCP工具调用。uvx缓存被清理后会重新下载，详见[uv工具缓存](https://docs.astral.sh/uv/concepts/tools/#tool-versions)。

断网可使用配置指向的已缓存版本；若配置已切到未缓存版本，当前不能自动回退。目录升级可能在服务包准备前已刷新插件缓存，因此不能承诺准备失败时插件一定保持旧版。

本机验证曾遇到uv提示`Failed to update Windows PE resources`，即临时启动文件写入失败。0.4.1将依赖安装并发设为1，安装脚本与插件使用相同环境；本机复测通过，但不据此认定解决了所有Windows环境的此类错误。若仍失败，可重新连接MCP或运行安装脚本重试，持续失败则保留完整错误排查运行环境。

## 开发者的本机安装

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install.ps1 -InstallPlugin
```

开发安装器使用仓库`.venv`和源码数据库，注册为`liuyao-assistant@personal`。只更新Skill或清单时运行`python scripts/install_plugin.py`，由Codex辅助脚本校验、更新缓存版本并重新安装。不要直接编辑已安装的插件缓存。

GitHub发行来源为`liuyao-assistant@liuyao`。已有personal开发版时，选择一个来源使用；确认发行版可用后可通过Codex插件管理移除开发版，源码目录不因此删除。

## 验证

`codex plugin list --json`应显示目标插件已安装并启用。新会话中发送README的起卦示例，检查实际出现`build_chart`、`search_knowledge`、`get_source`调用，且排盘表、候选条件比较与原文出处可见。CLI注册成功不代替桌面界面的实际使用验证。
