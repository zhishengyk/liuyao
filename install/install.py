#!/usr/bin/env python3
"""六爻助手通用 MCP 安装层。

只依赖 Python 标准库。唯一的权威配置是同级 `liuyao.mcp.json`
（标准 mcpServers 结构），唯一的权威技能是
`plugins/liuyao-assistant/skills/interpret-liuyao/SKILL.md`。
本脚本按客户端把这两份源文件「复制/合并/注册」到各端各自的位置，
不维护每个客户端一份模板；以后升级只改 liuyao.mcp.json 里的版本号。

用法（在仓库根目录执行）：
    python install/install.py --list                    列出支持的客户端与检测结果
    python install/install.py                           自动检测并注册已安装的客户端
    python install/install.py --workspace <目录>        额外把项目级 MCP 文件写进该目录
    python install/install.py --clients cursor,cline    只处理指定客户端（逗号分隔）
    python install/install.py --print-json              打印权威 MCP 定义（供手工导入/粘贴）
    python install/install.py --dry-run                 只显示将要执行的操作，不写文件
    python install/install.py --remove                  从已注册的客户端移除 liuyao
    python install/install.py --update 0.6.8            升级 wheel 版本并重新注册

额外依赖：目标客户端各自的命令行/应用（如 claude、codex）。uvx 需可用。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

try:  # 保证终端按 UTF-8 输出，避免 Windows 控制台代码页导致乱码
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
CANONICAL = HERE / "liuyao.mcp.json"
SKILL_SRC = ROOT / "plugins" / "liuyao-assistant" / "skills" / "interpret-liuyao" / "SKILL.md"
HOME = Path.home()

WHEEL_URL = "https://github.com/zhishengyk/liuyao/releases/download/v{ver}/liuyao_mcp-{ver}-py3-none-any.whl"


# ------------------------------------------------- 权威源

def entry() -> dict:
    """返回 liuyao 的 mcpServers 条目（每次读取权威源，保持单一事实来源）。"""
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or "liuyao" not in servers:
        raise SystemExit(f"{CANONICAL} 缺少 mcpServers.liuyao，请先检查该文件")
    return servers["liuyao"]


def wheel_url() -> str:
    args = entry().get("args") or []
    if "--from" in args:
        return args[args.index("--from") + 1]
    raise SystemExit("liuyao.mcp.json 中未找到 --from 参数")


def cli_command() -> list[str]:
    """命令及参数：uvx [args...] liuyao-mcp。"""
    e = entry()
    return [e.get("command", "uvx")] + list(e.get("args") or [])


# ------------------------------------------------- 文件合并工具

def _backup_once(path: Path) -> None:
    """首次安装时保留一份原配置备份，避免误覆盖不可恢复。"""
    bak = Path(str(path) + ".liuyao-bak")
    if path.exists() and not bak.exists():
        try:
            shutil.copy2(path, bak)
        except OSError:
            pass


def merge_json(path: Path, dry_run: bool) -> str:
    """把 liuyao 条目合并进某个 mcpServers JSON 文件（保留其他服务器）。"""
    if dry_run:
        existed = path.exists()
        return (f"将合并 -> {path}" + ("（已有其他条目会保留）" if existed else "（将新建）"))
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path} 不是有效 JSON，中止（不会覆盖原文件）：{exc}")
    servers = existing.setdefault("mcpServers", {})
    servers["liuyao"] = entry()
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup_once(path)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f"已写入 {path}"


def remove_from_json(path: Path, dry_run: bool) -> str | None:
    """从 mcpServers 文件移除 liuyao；仅当文件没有其它内容时才删除文件。"""
    if not path.exists():
        return None
    if dry_run:
        return f"将移除条目 {path}"
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or "liuyao" not in servers:
        return None
    del servers["liuyao"]
    if servers:
        data["mcpServers"] = servers
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif len(data) == 1:
        path.unlink()
    else:
        del data["mcpServers"]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f"已移除条目 {path}"


def copy_skill(dest: Path, dry_run: bool) -> str:
    """把 interpret-liuyao 技能整目录（SKILL.md 及 references/ 等）复制到目标技能目录。"""
    if not SKILL_SRC.exists():
        return "! 未找到技能源目录 plugins/liuyao-assistant/skills/interpret-liuyao"
    target_dir = dest.parent
    if dry_run:
        return f"将复制技能目录 -> {target_dir}"
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SKILL_SRC.parent, target_dir, dirs_exist_ok=True)
    return f"技能目录已复制 -> {target_dir}"


def _run(ctx: SimpleNamespace, cmd: list[str]) -> tuple[int, str]:
    """执行客户端 CLI；dry-run 时不执行。"""
    if ctx.dry_run:
        return 0, f"（dry-run）将执行：{' '.join(map(str, cmd))}"
    try:
        proc = subprocess.run(list(map(str, cmd)), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        out = (proc.stdout or "").strip()
        if proc.stderr and proc.stderr.strip():
            out += ("\n" + proc.stderr.strip())
        return proc.returncode, out
    except FileNotFoundError:
        return -1, "命令不存在"


def _fmt(rc: int, out: str) -> str:
    out = out.strip()
    return ("成功" if rc == 0 else f"失败（rc={rc}）") + (f"：{out}" if out else "")


# ------------------------------------------------- 检测

def _detect_claude() -> bool:
    return bool(shutil.which("claude")) or (HOME / ".claude").exists()


def _detect_codex() -> bool:
    return bool(shutil.which("codex")) or (HOME / ".codex").exists()


def _detect_cursor() -> bool:
    return (HOME / ".cursor").exists()


def _detect_roo() -> bool:
    return (HOME / ".roo").exists() or (
        HOME / ".config" / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline"
    ).exists()


def _detect_cline() -> bool:
    return (HOME / ".config" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev").exists() or (
        HOME / ".claude" / "settings"
    ).exists()


def _detect_opencode() -> bool:
    return bool(shutil.which("opencode"))


def _appdata(name: str) -> Path | None:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", "")) if os.environ.get("APPDATA") else HOME / "AppData" / "Roaming"
        p = base / name
        return p if p.exists() else None
    return None


def _detect_cherry() -> bool:
    candidates = [(HOME / ".config" / "cherry-studio"), _appdata("CherryStudio")]
    return any(p is not None and p.exists() for p in candidates)


def _detect_trae() -> bool:
    return bool(shutil.which("trae")) or (HOME / ".trae").exists() or _appdata("Trae") is not None


def _detect_qoder() -> bool:
    return bool(shutil.which("qoder")) or (HOME / ".qoder").exists() or _appdata("Qoder") is not None


# ------------------------------------------------- 各客户端安装实现

def install_claude_code(ctx: SimpleNamespace) -> list[str]:
    msgs: list[str] = []
    cli = shutil.which("claude")
    if cli:
        cmd = [cli, "mcp", "add", "liuyao", "--scope", "user", "--"] + cli_command()
        rc, out = _run(ctx, cmd)
        msgs.append(f"mcp add：{_fmt(rc, out)}")
    else:
        msgs.append("未检测到 claude CLI，跳过命令行注册；技能仍会复制。")
    msgs.append(copy_skill(HOME / ".claude" / "skills" / "interpret-liuyao" / "SKILL.md", ctx.dry_run))
    return msgs


def install_codex_plugin(ctx: SimpleNamespace) -> list[str]:
    msgs: list[str] = []
    if shutil.which("codex"):
        rc, out = _run(ctx, ["codex", "plugin", "marketplace", "add", "zhishengyk/liuyao",
                             "--ref", "main", "--sparse", ".agents/plugins", "--sparse", "plugins/liuyao-assistant"])
        msgs.append(f"marketplace add：{_fmt(rc, out)}")
        rc, out = _run(ctx, ["codex", "plugin", "add", "liuyao-assistant@liuyao"])
        msgs.append(f"plugin add：{_fmt(rc, out)}")
        msgs.append("安装后请开启新会话；插件自带技能，无需单独复制。")
    else:
        msgs.append("未检测到 codex CLI。Codex 走原生插件市场（本仓库 .agents/plugins），"
                    "安装 Codex 后重试，或按 README「安装到 Codex」手动添加。")
    return msgs


def install_cursor(ctx: SimpleNamespace) -> list[str]:
    msgs: list[str] = [merge_json(HOME / ".cursor" / "mcp.json", ctx.dry_run)]
    msgs.append(copy_skill(HOME / ".cursor" / "skills" / "interpret-liuyao" / "SKILL.md", ctx.dry_run))
    if ctx.workspace:
        msgs.append(merge_json(ctx.workspace / ".cursor" / "mcp.json", ctx.dry_run))
        msgs.append(copy_skill(ctx.workspace / ".cursor" / "skills" / "interpret-liuyao" / "SKILL.md", ctx.dry_run))
    return msgs


def remove_cursor(ctx: SimpleNamespace) -> list[str]:
    targets = [HOME / ".cursor" / "mcp.json"]
    if ctx.workspace:
        targets.append(ctx.workspace / ".cursor" / "mcp.json")
    msgs = [f"移除：{r}" for r in (remove_from_json(p, ctx.dry_run) for p in targets) if r]
    if not ctx.dry_run:
        shutil.rmtree(HOME / ".cursor" / "skills" / "interpret-liuyao", ignore_errors=True)
        if ctx.workspace:
            shutil.rmtree(ctx.workspace / ".cursor" / "skills" / "interpret-liuyao", ignore_errors=True)
    msgs.append("移除：Cursor 技能 ~/.cursor/skills/interpret-liuyao")
    return msgs


def install_roo(ctx: SimpleNamespace) -> list[str]:
    if not ctx.workspace:
        return ["未指定 --workspace，跳过（Roo 读取项目目录 .roo/mcp.json）"]
    return [merge_json(ctx.workspace / ".roo" / "mcp.json", ctx.dry_run)]


def remove_roo(ctx: SimpleNamespace) -> list[str]:
    if not ctx.workspace:
        return []
    r = remove_from_json(ctx.workspace / ".roo" / "mcp.json", ctx.dry_run)
    return [f"移除：{r}"] if r else []


def install_cline(ctx: SimpleNamespace) -> list[str]:
    if not ctx.workspace:
        return ["未指定 --workspace，跳过（Cline 读取项目根 .mcp.json，与 Claude Code 项目配置共用同一文件）"]
    return [merge_json(ctx.workspace / ".mcp.json", ctx.dry_run)]


def remove_cline(ctx: SimpleNamespace) -> list[str]:
    if not ctx.workspace:
        return []
    r = remove_from_json(ctx.workspace / ".mcp.json", ctx.dry_run)
    return [f"移除：{r}"] if r else []


def install_opencode(ctx: SimpleNamespace) -> list[str]:
    return [
        "OpenCode 通过 CLI 管理 MCP 配置，请在终端执行（参数以 `opencode mcp --help` 为准）：",
        f"  opencode mcp add liuyao -- {' '.join(cli_command())}",
    ]


def install_import_only(ctx: SimpleNamespace, label: str) -> list[str]:
    return [
        f"{label} 的 MCP 由应用内设置管理，本脚本不做文件写入。",
        f"请在其 MCP 设置中导入本仓库 install/liuyao.mcp.json，或粘贴：{' '.join(cli_command())}",
    ]


def install_guide(ctx: SimpleNamespace, label: str, lines: list[str]) -> list[str]:
    url = wheel_url()
    out = [f"{label}：暂不做自动写入，请按以下方式接入（以官方文档为准）："]
    out += [f"  {line.replace('{url}', url)}" for line in lines]
    return out


# ------------------------------------------------- 扩展检测（覆盖 AgentRecall 会话源列表）

def _which_any(*names: str) -> bool:
    return any(shutil.which(n) for n in names)


def _detect_codebuddy() -> bool:
    return _which_any("codebuddy", "cosy") or (HOME / ".codebuddy").exists()


def _detect_workbuddy() -> bool:
    return _which_any("workbuddy") or (HOME / ".workbuddy").exists() or (HOME / ".WorkBuddy").exists()


def _detect_codewiz() -> bool:
    return _which_any("codewiz", "wiz") or (HOME / ".codewiz").exists()


def _detect_tclaude() -> bool:
    return _which_any("tclaude") or (HOME / ".tclaude").exists()


def _detect_tcodex() -> bool:
    return _which_any("tcodex") or (HOME / ".tcodex").exists()


def _detect_openclaw() -> bool:
    return _which_any("openclaw") or (HOME / ".openclaw").exists()


def _detect_hermes() -> bool:
    return _which_any("hermes") or (HOME / ".hermes").exists()


def _detect_zcode() -> bool:
    return _which_any("zcode") or (HOME / ".zcode").exists()


def _detect_gemini() -> bool:
    return _which_any("gemini") or (HOME / ".gemini").exists()


def install_gemini(ctx: SimpleNamespace) -> list[str]:
    msgs: list[str] = [copy_skill(HOME / ".gemini" / "skills" / "interpret-liuyao" / "SKILL.md", ctx.dry_run)]
    msgs.append("Gemini CLI 的 MCP 注册请执行（以 `gemini mcp --help` 为准）：")
    msgs.append(f"  gemini mcp add liuyao -- {' '.join(cli_command())}")
    return msgs


# ------------------------------------------------- 注册表

CLIENTS = {
    "claude-code": {
        "label": "Claude Code",
        "detect": _detect_claude,
        "install": install_claude_code,
        "remove": lambda ctx: ["请在终端执行 `claude mcp remove liuyao --scope user`，并删除 ~/.claude/skills/interpret-liuyao"],
    },
    "codex": {
        "label": "Codex",
        "detect": _detect_codex,
        "install": install_codex_plugin,
        "remove": lambda ctx: ["请在 Codex 中卸载插件：`codex plugin remove liuyao-assistant`"],
    },
    "cursor": {"label": "Cursor", "detect": _detect_cursor, "install": install_cursor, "remove": remove_cursor},
    "roo": {"label": "Roo Code", "detect": _detect_roo, "install": install_roo, "remove": remove_roo},
    "cline": {"label": "Cline", "detect": _detect_cline, "install": install_cline, "remove": remove_cline},
    "opencode": {"label": "OpenCode", "detect": _detect_opencode, "install": install_opencode,
                 "remove": lambda ctx: ["请在终端执行 `opencode mcp remove liuyao`"]},
    "cherry-studio": {"label": "Cherry Studio", "detect": _detect_cherry,
                      "install": lambda ctx: install_import_only(ctx, "Cherry Studio"), "remove": lambda ctx: []},
    "trae": {"label": "Trae", "detect": _detect_trae,
             "install": lambda ctx: install_import_only(ctx, "Trae"), "remove": lambda ctx: []},
    "qoder": {"label": "Qoder", "detect": _detect_qoder,
              "install": lambda ctx: install_import_only(ctx, "Qoder"), "remove": lambda ctx: []},
    # ---- AgentRecall 会话源列表中的其余客户端（按机制分档） ----
    "gemini": {"label": "Gemini CLI", "detect": _detect_gemini, "install": install_gemini,
               "remove": lambda ctx: ["请删除 ~/.gemini/skills/interpret-liuyao，并执行 `gemini mcp remove liuyao`"]},
    "codebuddy": {"label": "CodeBuddy", "detect": _detect_codebuddy,
                  "install": lambda ctx: install_guide(ctx, "CodeBuddy", [
                      "在其 MCP 设置中导入 install/liuyao.mcp.json，或粘贴：uvx --python 3.11 --from {url} liuyao-mcp"]),
                  "remove": lambda ctx: ["在其应用内 MCP 设置中删除 liuyao 条目"]},
    "workbuddy": {"label": "WorkBuddy", "detect": _detect_workbuddy,
                  "install": lambda ctx: install_guide(ctx, "WorkBuddy", [
                      "在其 MCP 设置中导入 install/liuyao.mcp.json（或粘贴上述 uvx 命令）"]),
                  "remove": lambda ctx: ["在其应用内 MCP 设置中删除 liuyao 条目"]},
    "codewiz": {"label": "CodeWiz", "detect": _detect_codewiz,
                "install": lambda ctx: install_guide(ctx, "CodeWiz", [
                    "在其 MCP 设置中导入 install/liuyao.mcp.json（或粘贴上述 uvx 命令）"]),
                "remove": lambda ctx: ["在其应用内 MCP 设置中删除 liuyao 条目"]},
    "tclaude": {"label": "TClaude", "detect": _detect_tclaude,
                "install": lambda ctx: install_guide(ctx, "TClaude", [
                    "与 Claude Code 同一注册入口：claude mcp add liuyao --scope user -- uvx --python 3.11 --from {url} liuyao-mcp"]),
                "remove": lambda ctx: ["`claude mcp remove liuyao --scope user`（或对应 T 前缀命令）"]},
    "tcodex": {"label": "TCodex", "detect": _detect_tcodex,
               "install": lambda ctx: install_guide(ctx, "TCodex", [
                   "与 Codex 同一入口：codex mcp add liuyao -- uvx --python 3.11 --from {url} liuyao-mcp",
                   "或走本仓库插件市场：codex plugin add liuyao-assistant@liuyao"]),
               "remove": lambda ctx: ["`codex mcp remove liuyao` / `codex plugin remove liuyao-assistant`"]},
    "openclaw": {"label": "OpenClaw", "detect": _detect_openclaw,
                 "install": lambda ctx: install_guide(ctx, "OpenClaw", [
                     "OpenClaw 通过插件/技能接入，请安装 liuyao 的 MCP 插件（docs 见 openclaw 官方文档），服务命令：uvx --python 3.11 --from {url} liuyao-mcp"]),
                 "remove": lambda ctx: ["在 OpenClaw 插件配置中移除 liuyao MCP"]},
    "hermes": {"label": "Hermes", "detect": _detect_hermes,
               "install": lambda ctx: install_guide(ctx, "Hermes", [
                   "在其配置中注册 STDIO MCP：uvx --python 3.11 --from {url} liuyao-mcp"]),
               "remove": lambda ctx: ["在其配置中移除 liuyao MCP 条目"]},
    "zcode": {"label": "ZCode", "detect": _detect_zcode,
              "install": lambda ctx: install_guide(ctx, "ZCode", [
                  "在其 MCP 设置中导入 install/liuyao.mcp.json（或粘贴 uvx 命令）"]),
              "remove": lambda ctx: ["在其应用内 MCP 设置中删除 liuyao 条目"]},
}


# ------------------------------------------------- 主流程

def resolve_clients(want: str | None) -> list[str]:
    if want:
        names = [n.strip() for n in want.split(",") if n.strip()]
        unknown = [n for n in names if n not in CLIENTS]
        if unknown:
            raise SystemExit(f"不认识的客户端：{', '.join(unknown)}（支持：{', '.join(CLIENTS)}）")
        return names
    return [n for n in CLIENTS if CLIENTS[n]["detect"]()]


def show_list() -> int:
    print("六爻助手通用 MCP 安装层")
    print(f"权威源文件：{CANONICAL}")
    print(f"wheel：{wheel_url()}")
    print()
    print(f"{'客户端':<16}{'状态':<10}说明")
    for name, info in CLIENTS.items():
        present = info["detect"]()
        print(f"{info['label']:<16}{'已检测到' if present else '-':<10}{name}")
    print()
    print("用法：直接运行自动注册；--clients 指定；--workspace <目录> 写项目配置；")
    print("      --dry-run 预览；--print-json 打印权威 JSON；--update <版本> 升级；--remove 卸载。")
    return 0


def _update_version(version: str, dry_run: bool) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"无效版本号：{version}（应为 x.y.z）")
    text = CANONICAL.read_text(encoding="utf-8")
    old_url = wheel_url()
    new_url = WHEEL_URL.format(ver=version)
    if old_url not in text:
        raise SystemExit(f"{CANONICAL} 中未找到 {old_url}")
    if not dry_run:
        CANONICAL.write_text(text.replace(old_url, new_url), encoding="utf-8")
    print(f"[update] {'（预览）' if dry_run else ''}liuyao.mcp.json：{old_url} -> {new_url}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python install/install.py",
        description="六爻助手通用 MCP 安装层：一份 mcpServers 文件 + 一份 SKILL，注册到各客户端。",
    )
    ap.add_argument("--workspace", type=Path, default=None,
                    help="项目目录；把 .cursor/.roo/.mcp.json 写进该目录")
    ap.add_argument("--clients", default=None, help="逗号分隔的客户端名；缺省为自动检测（支持：%s）" % ", ".join(CLIENTS))
    ap.add_argument("--remove", action="store_true", help="从客户端移除 liuyao")
    ap.add_argument("--list", action="store_true", help="列出支持与检测结果")
    ap.add_argument("--print-json", action="store_true", help="打印权威 mcpServers JSON")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不写文件")
    ap.add_argument("--update", metavar="VERSION", default=None,
                    help="更新 liuyao.mcp.json 的 wheel 版本并重新注册，如 0.8.0")
    args = ap.parse_args(argv)

    if args.print_json:
        sys.stdout.write(CANONICAL.read_text(encoding="utf-8").rstrip() + "\n")
        return 0
    if args.list:
        return show_list()

    ctx = SimpleNamespace(workspace=args.workspace.resolve() if args.workspace else None,
                          dry_run=args.dry_run)

    if args.update:
        _update_version(args.update, dry_run=args.dry_run)

    targets = resolve_clients(args.clients)
    if not targets:
        print("未检测到已安装的客户端；可用 --clients 强制指定。")
        return 0

    for name in targets:
        info = CLIENTS[name]
        print(f"[{info['label']}] {'预览' if args.dry_run else '执行'}")
        for msg in (info["remove"] if args.remove else info["install"])(ctx):
            print("  " + msg)

    if args.dry_run:
        print("\n以上为预览，未写入任何文件。")
    else:
        print("\n完成。请重启相关客户端后开启新会话。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())