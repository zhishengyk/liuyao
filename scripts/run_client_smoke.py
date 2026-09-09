"""Exercise the installed MCP from the actual Codex client, without repo edits."""
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
output = root/".local/client-smoke"
output.mkdir(parents=True,exist_ok=True)
prompt = (root/"scripts/client_smoke_prompt.txt").read_text(encoding="utf8")
command = [shutil.which("codex"),"exec","--ephemeral","--json","--sandbox","read-only","-o",str(output/"answer.md"),"-"]
with (output/"events.jsonl").open("w",encoding="utf8") as stdout, (output/"stderr.log").open("w",encoding="utf8") as stderr:
    result = subprocess.run(command,input=prompt,text=True,encoding="utf8",stdout=stdout,stderr=stderr,cwd=root)
print(f"client smoke exit={result.returncode}; artifacts={output}")
raise SystemExit(result.returncode)
