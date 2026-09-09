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
scripts/install_release.ps1              面向使用者的GitHub安装/更新入口
```

服务发行包包含`liuyao_mcp/_data/knowledge.sqlite`，原文、知识块、卦例和索引均在库内。用户不需要原始资料目录。插件清单、服务版本和Release地址在发布时一起校验。

## 支持的接入端

| 接入端 | 入口 |
| --- | --- |
| Codex桌面端、CLI | 从GitHub目录安装六爻助手插件 |
| VS Code Codex | 直接配置同一MCP；可另装独立Skill |
| 其他支持STDIO的MCP客户端 | 使用相同uvx离线启动命令 |

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

再次运行同一脚本即可更新，不需要重新克隆仓库。网络或准备失败会停止安装，不主动卸载已安装的插件。启动新会话后使用新版；必要时重启客户端以刷新PATH和旧MCP进程。原生命令支持Git来源与目录刷新，具体依据见[OpenAI插件打包文档](https://developers.openai.com/plugins/build/plugins)。

日常查询使用`uvx --offline`。GitHub有新提交，不等于本机已自动更新；本版不增加常驻更新器。已安装版本在断网时继续工作，清理uv缓存后需要重新准备。

本机验证时曾遇到uv提示`Failed to update Windows PE resources`，即临时启动文件写入失败；再次运行同一脚本后成功。遇到此错误时先重新运行安装脚本，持续失败则保留完整错误排查运行环境。脚本在准备失败时不会继续安装新插件。

## 开发者的本机安装

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install.ps1 -InstallPlugin
```

开发安装器使用仓库`.venv`和源码数据库，注册为`liuyao-assistant@personal`。只更新Skill或清单时运行`python scripts/install_plugin.py`，由Codex辅助脚本校验、更新缓存版本并重新安装。不要直接编辑已安装的插件缓存。

GitHub发行来源为`liuyao-assistant@liuyao`。已有personal开发版时，选择一个来源使用；确认发行版可用后可通过Codex插件管理移除开发版，源码目录不因此删除。

## 验证

`codex plugin list --json`应显示目标插件已安装并启用。新会话中发送README的起卦示例，检查实际出现`build_chart`、`search_knowledge`、`get_source`调用，且排盘表、候选条件比较与原文出处可见。CLI注册成功不代替桌面界面的实际使用验证。
