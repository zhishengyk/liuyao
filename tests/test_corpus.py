import json
import sqlite3
from pathlib import Path

from liuyao_mcp.common import database_path, project_root
from liuyao_mcp.ingest import read_spans


def test_every_source_chunk_and_case_is_retraceable():
    report = json.loads((project_root()/"data/ingest_report.json").read_text(encoding="utf8"))
    assert len(report["sources"]) == 6 and report["total_ocr_pages"] == 811
    with sqlite3.connect(database_path()) as db:
        sources = {sid: (json.loads(meta),body.splitlines()) for sid,meta,body in db.execute("SELECT id,metadata,body FROM sources")}
        for payload, in db.execute("SELECT payload FROM chunks"):
            c = json.loads(payload)
            lines = sources[c["source_id"]][1]
            assert c["text"] == "\n".join(lines[c["start_line"]-1:c["end_line"]])
        for payload, in db.execute("SELECT payload FROM cases"):
            c = json.loads(payload)
            meta,lines = sources[c["source"]["source_id"]]
            assert c["source"]["sha256"] == meta["sha256"]
            assert c["source"]["original_text"] == read_spans(lines,c["source"]["spans"])
            if c["cast"]["line_values"]:
                assert len(c["cast"]["line_values"]) == 6
            if c["extraction"]["chart_validation"] == "conflict":
                assert "void_positions" not in c["features"]
        for source in report["sources"]:
            assert source["total_lines"] == source["covered_lines"]
            covered = set()
            for start,end in db.execute("SELECT start_line,end_line FROM chunks WHERE source_id=?",(source["source_id"],)):
                covered.update(range(start,end+1))
            for excluded in source["excluded_ranges"]:
                covered.update(range(excluded["start_line"],excluded["end_line"]+1))
            assert covered == set(range(1,source["total_lines"]+1))
