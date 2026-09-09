"""Read-only AI/MCP acceptance run, distinct from scripted protocol tests."""
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

root = Path(__file__).resolve().parents[1]
output = root/".local/client-batch"
output.mkdir(parents=True,exist_ok=True)
with sqlite3.connect(root/"data/knowledge.sqlite") as db:
    cases = [json.loads(row[0]) for row in db.execute("SELECT payload FROM cases WHERE topic IN ('job','relationship','lost','study','travel') ORDER BY id")]
selected = []
seen = set()
for c in cases:
    if c["extraction"]["chart_validation"] != "calculated" or c["duplicate_group"] in seen:
        continue
    seen.add(c["duplicate_group"])
    selected.append({"case_id":c["case_id"],"question":c["question"]["raw"],"line_values":c["cast"]["line_values"],"month_branch":c["cast"]["month_branch"],"day_ganzhi":c["cast"]["day_ganzhi"]})
    if len(selected)==20:
        break
assert len(selected)==20
(output/"inputs.json").write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding="utf8")
schema = {"type":"object","additionalProperties":False,"properties":{"runs":{"type":"array","minItems":20,"maxItems":20,"items":{"type":"object","additionalProperties":False,"properties":{"case_id":{"type":"string"},"primary":{"type":"string"},"rule_count":{"type":"integer"},"case_count":{"type":"integer"},"evidence_id":{"type":"string"},"quote":{"type":"string"},"analysis":{"type":"string"},"uncertainty":{"type":"string"},"error":{"type":["string","null"]}},"required":["case_id","primary","rule_count","case_count","evidence_id","quote","analysis","uncertainty","error"]}}},"required":["runs"]}
(output/"schema.json").write_text(json.dumps(schema),encoding="utf8")
prompt = """Perform a read-only acceptance test of the liuyao MCP plugin for every one of the 20 supplied inputs. Do not use shell, filesystem, web, subagents, or code execution. Use only the liuyao MCP tools. For EACH input: call build_chart; search_knowledge for rule and case evidence, with limit=2 and max_chars=6000 for this bounded test, excluding that input's case_id through exclude_case_ids; then get_source for ONE rule to verify a short quote. Do not infer that the historical result was successful. The production defaults 12 and 8 are covered in separate tests. Return the required JSON with a short Chinese analysis of 1-2 sentences for each input, one exact short source quotation and its evidence_id, factual primary name, actual returned counts, and uncertainty. Preserve source OCR instead of inventing corrections. If a call fails, report it in error. Complete all 20 inputs; no progress-only final response.\nInputs:\n""" + json.dumps(selected,ensure_ascii=False)
command = [shutil.which("codex"),"exec","--ephemeral","--json","--sandbox","read-only","--output-schema",str(output/"schema.json"),"-o",str(output/"answers.json"),"-"]
with (output/"events.jsonl").open("w",encoding="utf8") as stdout, (output/"stderr.log").open("w",encoding="utf8") as stderr:
    result = subprocess.run(command,input=prompt,text=True,encoding="utf8",stdout=stdout,stderr=stderr,cwd=root)
print(f"client batch exit={result.returncode}; artifacts={output}")
raise SystemExit(result.returncode)
