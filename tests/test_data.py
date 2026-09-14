import json
import sqlite3
from liuyao_mcp.common import database_path
from liuyao_mcp.ingest import native_row, read_spans
from liuyao_mcp.retrieval import get_source, search_knowledge, structure_match


def test_native_main_line_not_changed_or_hidden():
    assert native_row('妻财未土×世')[1] == 0
    assert native_row("官鬼午火′ 动 父母未土″应")[1] == 3
    match,value = native_row("父母子水（伏） 妻财未土″世 青龙")
    assert match[1] == "妻财" and value == 2


def test_reviewed_same_page_two_diagrams_and_cross_page_case():
    with sqlite3.connect(database_path()) as db:
        def case(eid):
            return json.loads(db.execute('SELECT payload FROM cases WHERE id=?', (eid,)).fetchone()[0])
        first = case('liuyao_xiangfa_jinjie_shang.manual.p0014_job')
        second = case('liuyao_xiangfa_jinjie_shang.manual.p0015_marriage')
        text = db.execute('SELECT body FROM sources WHERE id=?', (first['source']['source_id'],)).fetchone()[0]
    assert first["cast"]["line_values"] == [2,2,2,2,1,2]
    assert second["cast"]["line_values"] == [1,1,2,2,1,2]
    assert "测与女友能否结婚" not in first["source"]["original_text"]
    assert "世财即是怀孕了" in second["source"]["original_text"]
    assert first['source']['pdf_pages'] == [14, 15]
    assert second['source']['pdf_pages'] == [15, 16]
    assert read_spans(text.split('\n'),first["source"]["spans"]) == first["source"]["original_text"]
    assert read_spans(text.split('\n'),second["source"]["spans"]) == second["source"]["original_text"]


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
    assert result["items"] and all(x["method"] in ('xiangfa', 'mixed') for x in result["items"])
    assert structure_match({"yongshen_void":True},{})["unknown"]
    assert structure_match({"moving_positions":[]},{"moving_positions":[2]})["different"]
    assert structure_match({"moving_positions":[]},{"moving_positions":[]})["matched"]
    assert structure_match({"moving_positions":[4,5]},{"moving_positions":[3,4,5]})["different"]
    romance = search_knowledge("是否继续感情还是创业",kind="case",topic="relationship",max_chars=150000)
    assert romance["items"] and all('relationship' in x['classification']['roots'] or not x['classification']['roots'] for x in romance['items'])
    case = search_knowledge("求职",kind="case")["items"][0]
    rules = search_knowledge("工作",exclude_case_ids=[case["evidence_id"]])
    with sqlite3.connect(database_path()) as db:
        lines = db.execute('SELECT body FROM sources WHERE id=?', (case['source_id'],)).fetchone()[0].split('\n')
    for item in rules["items"]:
        if item["source_id"] == case["source_id"]:
            for a in item["source_spans"]:
                for b in case['source_spans']:
                    start = max((a['start_line'], a['start_column']), (b['start_line'], b['start_column']))
                    end = min((a['end_line'], a['end_column']), (b['end_line'], b['end_column']))
                    if start < end:
                        overlap = {'start_line':start[0], 'start_column':start[1],
                                   'end_line':end[0], 'end_column':end[1]}
                        assert not read_spans(lines, [overlap]).strip()


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
    result = get_source("liuyao_lifa_jinjie.manual.p0018_relationship_persist")
    assert result["pdf_pages"] == [18,19]
    assert result["source"]["total_pdf_pages"] == 257
    assert "pdf_pages" not in result["source"]


def test_confirmed_cross_book_event_is_excluded_from_both_sources():
    first = 'liuyao_lifa_jinjie.manual.p0049_skip_work'
    second = 'liuyao_xiangfa_jinjie_shang.manual.p0067_skipping_work'
    with sqlite3.connect(database_path()) as db:
        a = db.execute("SELECT duplicate_group FROM cases WHERE id=?",(first,)).fetchone()[0]
        b = db.execute("SELECT duplicate_group FROM cases WHERE id=?",(second,)).fetchone()[0]
        assert a == b
    result = search_knowledge("下午不去上班会不会有什么事",kind="case",exclude_case_ids=[first])
    assert not {first, second} & {i["evidence_id"] for i in result["items"]}


def test_explicit_no_feedback_is_not_an_outcome():
    with sqlite3.connect(database_path()) as db:
        c = json.loads(db.execute("SELECT payload FROM cases WHERE id=?",('liuyao_xiangfa_jinjie_shang.manual.p0213_marry_boyfriend',)).fetchone()[0])
    assert c["outcome"]["status"] == "none"
    assert c['outcome']['quotes'] == [] and c['quality']['status'] == 'noise'
