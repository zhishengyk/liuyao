"""Check actual client traces and quotations against the current source snapshot."""
from collections import Counter
import json
from pathlib import Path
import re

from jsonschema import validate
from liuyao_mcp.chart import build_chart
from liuyao_mcp.retrieval import get_source

root = Path(__file__).resolve().parents[1]
folder = root/".local/client-batch"
answers = json.loads((folder/"answers.json").read_text(encoding="utf8"))
validate(answers,json.loads((folder/"schema.json").read_text(encoding="utf8")))
inputs = {r["case_id"]:r for r in json.loads((folder/"inputs.json").read_text(encoding="utf8"))}
events = [json.loads(l) for l in (folder/"events.jsonl").read_text(encoding="utf8").splitlines()]
calls = [e["item"] for e in events if e.get("type")=="item.completed" and e.get("item",{}).get("type")=="mcp_tool_call"]
assert len(calls)==80 and all(c["status"]=="completed" and not c.get("error") for c in calls)
assert {r["case_id"] for r in answers["runs"]} == set(inputs)
read_ids = {c["arguments"]["evidence_id"] for c in calls if c["tool"]=="get_source"}
hashes, results = set(), []
for answer in answers["runs"]:
    inp = inputs[answer["case_id"]]
    chart = build_chart(inp["line_values"],month_branch=inp["month_branch"],day_ganzhi=inp["day_ganzhi"])
    assert answer["primary"] in (chart["primary"]["name"],chart["primary"]["full_name"])
    assert answer["error"] is None
    assert answer["evidence_id"] in read_ids
    source = get_source(answer["evidence_id"],max_chars=500000)
    quote = answer["quote"]
    exact = quote in source["text"]
    normalized = re.sub(r"\s+","",quote) in re.sub(r"\s+","",source["text"])
    assert exact or normalized, (answer["case_id"],quote)
    found = {}
    for call in calls:
        if call["tool"]=="search_knowledge" and answer["case_id"] in call["arguments"].get("exclude_case_ids",[]):
            payload = call["result"]["structured_content"]
            found[call["arguments"]["kind"]] = payload["returned_count"]
            hashes.add(payload["corpus_hash"])
    assert found == {"rule":answer["rule_count"],"case":answer["case_count"]}
    results.append({"case_id":answer["case_id"],"exact_quote":exact,"whitespace_normalized_quote":normalized,"chart_name_correct":True,"recorded_counts_correct":True})
report = {"runs":len(results),"mcp_calls":dict(Counter(c["tool"] for c in calls)),"tested_corpus_hashes":sorted(hashes),"checks":results,"scope":"Checks actual tool calls, chart names, counts, citation IDs and source quotations; natural-language reasoning is not proven by these checks."}
(folder/"verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
print(json.dumps({k:v for k,v in report.items() if k!='checks'},ensure_ascii=False))
