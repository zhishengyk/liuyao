"""Same-query/corpus ablation, with explicit source-derived proxy labels."""
import argparse
import json
from pathlib import Path
import time

from liuyao_mcp.common import digest, dumps, project_root
from liuyao_mcp.retrieval import get_source, search_knowledge

parser = argparse.ArgumentParser()
parser.add_argument("--queries",type=int,default=12)
parser.add_argument("--output",type=Path,default=project_root()/"data/eval/semantic-comparison")
args = parser.parse_args()
source = project_root()/"data/eval/queries.jsonl"
queries = [json.loads(l) for l in source.read_text(encoding="utf8").splitlines()]
dev = sorted((q for q in queries if q["split"]=="development"),key=lambda q:digest(q["id"]))
holdout = sorted((q for q in queries if q["split"]=="holdout"),key=lambda q:digest(q["id"]))
selected = dev[:args.queries//2]+holdout[:args.queries-args.queries//2]
args.output.mkdir(parents=True,exist_ok=True)
(args.output/"queries.json").write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding="utf8")
results = []
(args.output/"runs.jsonl").write_text("",encoding="utf8")
for index,q in enumerate(selected,1):
    for mode in ("bm25","hybrid","hybrid_rerank"):
        for limit in (12,20):
            start = time.perf_counter()
            result = search_knowledge(q["query"],retrieval_mode=mode,limit=limit,max_chars=150000)
            for item in result["items"]:
                assert get_source(item["evidence_id"],max_chars=500000)["text"]==item["quote"]
            results.append({**q,"mode":mode,"limit":limit,"elapsed_ms":round((time.perf_counter()-start)*1000,2),"corpus_hash":result["corpus_hash"],"models":result["models"],"timings":result["timings"],"anchor_hit":any(i["evidence_id"]==q["anchor_id"] for i in result["items"]),"source_hit":any(i["source_id"]==q["source_id"] for i in result["items"]),"returned_count":result["returned_count"],"evidence_ids":[i["evidence_id"] for i in result["items"]]})
            with (args.output/"runs.jsonl").open("a",encoding="utf8") as stream:
                stream.write(dumps(results[-1])+"\n")
        print(dumps({"done_query":index,"total_queries":len(selected),"mode":mode}),flush=True)
assert len({r["corpus_hash"] for r in results})==1
summary = {"query_count":len(selected),"metric_kind":"source-derived anchor proxy, not independently judged relevance","groups":{}}
for split in ("development","holdout"):
    for mode in ("bm25","hybrid","hybrid_rerank"):
        for limit in (12,20):
            rs = [r for r in results if r["split"]==split and r["mode"]==mode and r["limit"]==limit]
            if rs:
                summary["groups"][f"{split}_{mode}_k{limit}"] = {"n":len(rs),"anchor_hit_rate":sum(r["anchor_hit"] for r in rs)/len(rs),"source_hit_rate":sum(r["source_hit"] for r in rs)/len(rs),"mean_ms":sum(r["elapsed_ms"] for r in rs)/len(rs)}
(args.output/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")
print(dumps(summary))
