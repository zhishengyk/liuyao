"""Set output budgets for this MCP only; preserve existing user configuration."""
from pathlib import Path
import os
import re
import shutil
import tomllib

path = Path(os.environ.get("CODEX_HOME",Path.home()/".codex"))/"config.toml"
text = path.read_text(encoding="utf8")
config = tomllib.loads(text)
server = config.get("mcp_servers",{}).get("liuyao")
if not server:
    raise SystemExit("Register liuyao MCP before configuring its output budget")
additions = []
updated = text
if "tool_timeout_sec" not in server:
    updated,count = re.subn(r"(?m)^(\[mcp_servers\.liuyao\][ \t]*)$",r"\1\ntool_timeout_sec = 600",updated,count=1)
    if count != 1:
        raise SystemExit("Cannot locate liuyao server table; no changes written")
for tool in ("search_knowledge","get_source"):
    settings = server.get("tools",{}).get(tool,{})
    if "output_token_limit" in settings:
        continue
    if settings:
        raise SystemExit(f"Existing {tool} settings need a targeted edit; no changes written")
    additions.append(f"\n[mcp_servers.liuyao.tools.{tool}]\noutput_token_limit = 60000\n")
updated += "".join(additions)
if updated != text:
    tomllib.loads(updated)
    backup = path.with_name("config.toml.before-liuyao-output-budget")
    if not backup.exists():
        shutil.copy2(path,backup)
    path.write_text(updated,encoding="utf8")
print("liuyao output budgets and model timeout configured; existing settings preserved")
