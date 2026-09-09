import json
import sqlite3
from pathlib import Path

from liuyao_mcp.common import database_path, project_root
from liuyao_mcp.ingest import import_source, native_row, read_spans
from liuyao_mcp.retrieval import get_source, search_knowledge, structure_match


def test_native_main_line_not_changed_or_hidden():
    assert native_row("官鬼午火′ 动 父母未土″应")[1] == 9
    match,value = native_row("父母子水（伏） 妻财未土″世 青龙")
    assert match[1] == "妻财" and value == 8


def test_ocr_same_page_two_diagrams_and_cross_page_case():
    manifest = [json.loads(l) for l in (project_root()/"data/sources.jsonl").read_text(encoding="utf8").splitlines()]
    source = next(s for s in manifest if s["source_id"] == "liuyao_xiangfa_jinjie_shang")
    _,text,_,cases,_ = import_source(source,project_root())
    first = next(c for c in cases if c["case_id"].endswith("_352"))
    second = next(c for c in cases if c["case_id"].endswith("_369"))
    assert first["cast"]["line_values"] == [8,8,8,8,7,8]
    assert second["cast"]["line_values"] == [7,7,8,8,7,8]
    assert "测与女友能否结婚" not in first["source"]["original_text"]
    assert "世财即是怀孕了" in second["source"]["original_text"]
    assert read_spans(text.splitlines(),first["source"]["spans"]) == first["source"]["original_text"]


def test_defaults_expansion_followup_and_citations():
    for kind, count, larger in [("rule",12,20),("case",8,12)]:
        result = search_knowledge("工作 官鬼 求职",kind=kind,max_chars=150000)
        assert result["returned_count"] == count
        bigger = search_knowledge("工作 官鬼 求职",kind=kind,limit=larger,max_chars=150000)
        assert bigger["returned_count"] == larger
        previous = [x["evidence_id"] for x in result["items"]]
        follow = search_knowledge("工作 官鬼 求职",kind=kind,exclude_ids=previous,max_chars=150000)
        assert not set(previous)&{x["evidence_id"] for x in follow["items"]}
        for item in result["items"]:
            source = get_source(item["evidence_id"])
            if kind == "rule":
                assert source["text"] == item["quote"]
            assert source["source"]["sha256"] == item["source_hash"]


def test_filter_unknown_and_exclusion():
    result = search_knowledge("六神 青龙",method="xiangfa")
    assert result["items"] and all(x["method"]=="xiangfa" for x in result["items"])
    assert structure_match({"yongshen_void":True},{})["unknown"]
    assert structure_match({"moving_positions":[]},{"moving_positions":[2]})["different"]
    assert structure_match({"moving_positions":[]},{"moving_positions":[]})["matched"]
    assert structure_match({"moving_positions":[4,5]},{"moving_positions":[3,4,5]})["different"]
    romance = search_knowledge("是否继续感情还是创业",kind="case",topic="relationship",max_chars=150000)
    assert romance["items"] and all(x["question"]["topic"]=="relationship" for x in romance["items"])
    case = search_knowledge("求职",kind="case")["items"][0]
    rules = search_knowledge("工作",exclude_case_ids=[case["evidence_id"]])
    for item in rules["items"]:
        if item["source_id"] == case["source_id"]:
            for a in item["source_spans"]:
                assert not any(a["start_line"]<=b["end_line"] and a["end_line"]>=b["start_line"] for b in case["source_spans"])


def test_source_budget_pagination_and_no_query_writes():
    before = database_path().read_bytes()
    case = search_knowledge("工作",kind="case")["items"][0]
    full = get_source(case["evidence_id"],context_lines=30,max_chars=500000)
    text, offset = "",0
    while True:
        page = get_source(case["evidence_id"],context_lines=30,offset=offset,max_chars=1000)
        text += page["text"]
        if not page["has_more"]:
            break
        offset = page["next_offset"]
    assert text == full["text"]
    assert database_path().read_bytes() == before


def test_pdf_evidence_pages_are_not_book_page_count():
    result = get_source("case_liuyao_lifa_jinjie_475")
    assert result["pdf_pages"] == [18,19]
    assert result["source"]["total_pdf_pages"] == 257
    assert "pdf_pages" not in result["source"]


def test_cross_book_ocr_variant_is_excluded_as_possible_duplicate():
    with sqlite3.connect(database_path()) as db:
        a = db.execute("SELECT duplicate_group FROM cases WHERE id=?",("case_liuyao_lifa_jinjie_1868",)).fetchone()[0]
        b = db.execute("SELECT duplicate_group FROM cases WHERE id=?",("case_liuyao_xiangfa_jinjie_shang_2775",)).fetchone()[0]
        assert a == b
    result = search_knowledge("下午不去上班会不会有什么事",kind="case",exclude_case_ids=["case_liuyao_lifa_jinjie_1868"])
    assert "case_liuyao_xiangfa_jinjie_shang_2775" not in {i["evidence_id"] for i in result["items"]}


def test_explicit_no_feedback_is_not_an_outcome():
    with sqlite3.connect(database_path()) as db:
        c = json.loads(db.execute("SELECT payload FROM cases WHERE id=?",("case_liuyao_xiangfa_jinjie_shang_9590",)).fetchone()[0])
    assert c["outcome"]["status"] == "none"
