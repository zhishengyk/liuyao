"""Reproducible proxy evaluation; never claims human labels or predictive skill."""
import argparse
import asyncio
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from .common import TERMS, database_path, digest, dumps, project_root
from .retrieval import get_source, search_knowledge


def check_citations(result):
    for item in result["items"]:
        source = get_source(item["evidence_id"])
        if item["source_hash"] != source["source"]["sha256"]:
            raise AssertionError("Citation hash mismatch")
        if "quote" in item and source["text"] != item["quote"]:
            raise AssertionError("Citation text mismatch")


def evaluate(output=None, protocol_runs=20, retrieval_mode="bm25"):
    output = Path(output or project_root()/"data/eval")
    output.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(database_path()) as db:
        info = dict(db.execute("SELECT key,value FROM build_info"))
        chunks = [json.loads(row[0]) for row in db.execute("SELECT payload FROM chunks ORDER BY id")]
        cases = [json.loads(row[0]) for row in db.execute("SELECT payload FROM cases ORDER BY id")]
    queries, seen = [], set()
    source_count = Counter()
    for chunk in sorted(chunks,key=lambda c:digest(c["id"])):
        terms = [term for term in TERMS if term in chunk["text"]]
        group = chunk["source_id"]+":"+chunk["chapter"]
        if len(terms)<2 or group in seen or source_count[chunk["source_id"]]>=12:
            continue
        seen.add(group)
        source_count[chunk["source_id"]]+=1
        queries.append({"id":digest(chunk["id"])[:16],"query":" ".join(terms[:3]),"anchor_id":chunk["id"],"source_id":chunk["source_id"],"group":group,"split":"holdout" if int(digest(group)[:8],16)%3==0 else "development"})
    (output/"queries.jsonl").write_text("".join(dumps(q)+"\n" for q in queries),encoding="utf8")
    runs = []
    for q in queries:
        for limit in (12,20):
            start = time.perf_counter()
            result = search_knowledge(q["query"],limit=limit,max_chars=150000,retrieval_mode=retrieval_mode)
            elapsed = time.perf_counter()-start
            check_citations(result)
            ids = [i["evidence_id"] for i in result["items"]]
            runs.append({**q,"limit":limit,"retrieval":result["retrieval"],"returned_count":len(ids),"anchor_hit":q["anchor_id"] in ids,"source_hit":any(i["source_id"]==q["source_id"] for i in result["items"]),"unique_sources":len({i["source_id"] for i in result["items"]}),"latency_ms":round(elapsed*1000,2),"used_chars":result["used_chars"],"evidence_ids":ids})
    (output/"retrieval_runs.jsonl").write_text("".join(dumps(r)+"\n" for r in runs),encoding="utf8")
    valid = [c for c in cases if c["derived"] and c["extraction"]["chart_validation"]=="calculated" and c["question"]["raw"]]
    valid.sort(key=lambda c:digest(c["case_id"]))
    selected, groups = [], set()
    for case in valid:
        if protocol_runs <= 0:
            break
        if case["duplicate_group"] not in groups:
            selected.append(case)
            groups.add(case["duplicate_group"])
        if len(selected)==protocol_runs:
            break
    async def protocol():
        if not selected:
            return []
        records = []
        params = StdioServerParameters(command=sys.executable,args=["-m","liuyao_mcp.server"],env={**os.environ,"PYTHONIOENCODING":"utf-8","LIUYAO_RETRIEVAL_MODE":retrieval_mode})
        async with Client(params,read_timeout_seconds=600) as client:
            for c in selected:
                calls = []
                async def call(name,args):
                    result = await client.call_tool(name,args)
                    if result.is_error:
                        raise AssertionError(f"MCP call failed: {name}: {result.content}")
                    payload = result.structured_content
                    calls.append({"tool":name,"arguments":args,"result":payload})
                    return payload
                pan = await call("build_chart",{"line_values":c["cast"]["line_values"],"month_branch":c["cast"]["month_branch"],"day_ganzhi":c["cast"]["day_ganzhi"]})
                query = c["question"]["raw"]
                rules = await call("search_knowledge",{"query":query,"kind":"rule","exclude_case_ids":[c["case_id"]],"max_chars":150000})
                similar = await call("search_knowledge",{"query":query,"kind":"case","features":{"shi_relative":pan["features"]["shi_relative"],"ying_relative":pan["features"]["ying_relative"]},"exclude_case_ids":[c["case_id"]],"max_chars":150000})
                check_citations(rules)
                check_citations(similar)
                assert c["case_id"] not in {i["evidence_id"] for i in similar["items"]}
                if rules["items"]:
                    await call("get_source",{"evidence_id":rules["items"][0]["evidence_id"]})
                records.append({"case_id":c["case_id"],"protocol":"stdio","calls":calls,"analysis":None,"analysis_status":"not_generated_by_this_protocol_test"})
        return records
    traces = asyncio.run(protocol())
    (output/"mcp_runs.jsonl").write_text("".join(dumps(t)+"\n" for t in traces),encoding="utf8")
    summary = {"build":info,"retrieval_mode":retrieval_mode,"query_count":len(queries),"protocol_runs":len(traces),"citations_checked":sum(r["returned_count"] for r in runs),"metric_kind":"source-derived proxy; not independent relevance labels", "llm_analysis_validation":"see retained client-batch acceptance artifacts", "groups":{}}
    for split in ("development","holdout"):
        for limit in (12,20):
            rs = [r for r in runs if r["split"]==split and r["limit"]==limit]
            if rs:
                summary["groups"][f"{split}_k{limit}"] = {"n":len(rs),"anchor_hit_rate":sum(r["anchor_hit"] for r in rs)/len(rs),"source_hit_rate":sum(r["source_hit"] for r in rs)/len(rs),"mean_sources":sum(r["unique_sources"] for r in rs)/len(rs),"mean_latency_ms":sum(r["latency_ms"] for r in rs)/len(rs)}
    (output/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path)
    parser.add_argument("--protocol-runs",type=int,default=20)
    parser.add_argument("--retrieval-mode",choices=["bm25","hybrid","hybrid_rerank"],default="bm25")
    args = parser.parse_args()
    print(dumps(evaluate(args.output,args.protocol_runs,args.retrieval_mode)))


if __name__ == "__main__":
    main()
