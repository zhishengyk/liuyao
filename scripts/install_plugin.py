"""Install the project plugin into the personal marketplace using Codex's helpers."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
name = "liuyao-assistant"
helpers = Path.home()/".codex/skills/.system/plugin-creator/scripts"
marketplace = Path.home()/".agents/plugins/marketplace.json"
destination = Path.home()/"plugins"/name
source = root/"plugins"/name


def run(*args):
    result = subprocess.run([str(a) for a in args],text=True,encoding="utf8",capture_output=True)
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)
    return result.stdout.strip()


if not (helpers/"create_basic_plugin.py").is_file():
    raise SystemExit("Codex plugin-creator helper is required for marketplace installation; direct MCP setup remains available.")
existing = False
if marketplace.exists():
    marketplace_name = run(sys.executable,"-X","utf8",helpers/"read_marketplace_name.py")
    catalog = json.loads(marketplace.read_text(encoding="utf8"))
    entry = next((p for p in catalog["plugins"] if p["name"]==name),None)
    existing = entry is not None
    if entry and entry["source"] != {"source":"local","path":f"./plugins/{name}"}:
        raise SystemExit("Existing plugin points to a different source; no files changed.")
if not existing:
    print(run(sys.executable,"-X","utf8",helpers/"create_basic_plugin.py",name,"--path",destination.parent,"--with-skills","--with-mcp","--with-marketplace"))
for file in source.rglob("*"):
    if file.is_file():
        target = destination/file.relative_to(source)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(file,target)
config = {"mcpServers":{"liuyao":{"command":str(root/".venv/Scripts/python.exe"),"args":["-m","liuyao_mcp.server"],"tool_timeout_sec":600,"env":{"LIUYAO_ROOT":str(root),"PYTHONIOENCODING":"utf-8"}}}}
(destination/".mcp.json").write_text(json.dumps(config,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
if existing:
    print(run(sys.executable,"-X","utf8",helpers/"update_plugin_cachebuster.py",destination))
print(run(sys.executable,"-X","utf8",helpers/"validate_plugin.py",destination))
marketplace_name = run(sys.executable,"-X","utf8",helpers/"read_marketplace_name.py")
print(run(shutil.which("codex"),"plugin","add",f"{name}@{marketplace_name}","--json"))
print(json.dumps({"plugin":name,"marketplace":str(marketplace),"path":str(destination)},ensure_ascii=False))
