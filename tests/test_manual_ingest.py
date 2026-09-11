import hashlib
import copy
import json
import sqlite3
from contextlib import closing

import pytest

from liuyao_mcp.common import case_search_text, digest
from liuyao_mcp.manual_ingest import IncompleteCorpusError, build_database


REVIEW = {"status": "approved", "basis": "direct_source_read", "reviewer": "test reviewer", "notes": "explicit manual boundaries"}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def fixture_source(root):
    lines = ["用神通则：以所问事项取用。", "问求职。背景：已投简历。辰月戊申日。",
             "六爻初至上：1 1 1 3 1 1", "作者断：父母为用，丑日可成。反馈：最终未录用。事后分析：另有所指。"]
    blob = "\r\n".join(lines).encode("utf-8")
    (root / "source.md").write_bytes(blob)
    source = {"source_id": "book", "title": "测试书", "source_type": "native_text", "path": "source.md",
              "sha256": hashlib.sha256(blob).hexdigest(), "method_hint": "lifa", "author": "作者", "pdf_pages": None}
    write_json(root / "data/canonical/sources.jsonl", source)

    def span(start, end=None, quote=None):
        end = end or start
        text = "\n".join(lines[start - 1:end])
        result = {"page": None, "start_line": start, "end_line": end}
        if quote is not None:
            result.update(start_column=text.index(quote), end_column=text.index(quote) + len(quote))
            text = quote
        result.update(exact_text=text, quote_sha256=digest(text))
        return result

    rule = {"unit_id": "manual.rule", "kind": "rule", "title": "用神", "method": "lifa", "scope": "common", "topic_ids": [], "spans": [span(1)], "review": REVIEW}
    case = {"unit_id": "manual.case", "kind": "case", "title": "求职卦", "method": "lifa", "scope": "case", "topic_ids": ["job/job_search"], "spans": [span(2, 4)], "review": REVIEW,
            "quality": {"status": "eligible", "reason": "求职原问与未录用反馈对应，可核验原断失败", "reviewer": "fixture quality reviewer"},
            "parts": {"question": [span(2, quote="问求职。")], "background": [span(2, quote="背景：已投简历。")],
                      "chart": [span(3)], "author_analysis": [span(4, quote="作者断：父母为用，丑日可成。")],
                      "feedback": [span(4, quote="反馈：最终未录用。")], "post_feedback_analysis": [span(4, quote="事后分析：另有所指。") ]},
            "cast": {"line_values": [1, 1, 1, 3, 1, 1], "month_branch": "辰", "day_ganzhi": "戊申",
                     "field_spans": {"line_values": [span(3)], "month_branch": [span(2, quote="辰月")],
                                     "day_ganzhi": [span(2, quote="戊申日")]}}}
    manifest = {"schema_version": "manual-slices-1", "source_id": "book", "source_sha256": source["sha256"], "units": [rule, case]}
    write_json(root / "data/manual_slices/book.json", manifest)
    return source, manifest, lines


def audit_cast(root, manifest, cast_index=0):
    case = manifest["units"][1]
    cast = case["cast"] if cast_index == 0 else case["additional_casts"][cast_index - 1]
    path = root / f"data/manual_slices/audits/cast{cast_index or ''}.json"
    case_id = case["unit_id"] if cast_index == 0 else f"{case['unit_id']}.cast{cast_index + 1}"
    diagram = cast.get("diagram_spans", case["parts"]["chart"])
    record = {"unit_id": case_id, "source_sha256": manifest["source_sha256"],
              "chart_text_sha256": digest("\n".join(s["exact_text"] for s in diagram)),
              "input_line_values": cast["line_values"], "month_branch": cast["month_branch"],
              "day_ganzhi": cast["day_ganzhi"], "status": "passed"}
    write_json(path, {"records": [record]})
    cast["verification"] = {"status": "verified", "basis": "independent_literal_chart_labels", "reviewer": "independent test reviewer",
                            "evidence": path.relative_to(root).as_posix(), "evidence_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    write_json(root / "data/manual_slices/book.json", manifest)
    return path, record


def fixture_two_casts(root):
    source, manifest, lines = fixture_source(root)
    lines = lines[:3] + ["第一断：自占以世爻为用。", "母占六爻初至上：3 1 1 1 1 1", "第二断：代占取子孙。", "总论：不可拘泥。", "反馈：最终未录用。"]
    blob = "\r\n".join(lines).encode("utf-8")
    (root / "source.md").write_bytes(blob)
    source["sha256"] = manifest["source_sha256"] = hashlib.sha256(blob).hexdigest()
    write_json(root / "data/canonical/sources.jsonl", source)
    def span(start, end=None, **extra):
        text = "\n".join(lines[start - 1:end or start])
        return {"page": None, "start_line": start, "end_line": end or start,
                "exact_text": text, "quote_sha256": digest(text), **extra}
    case = manifest["units"][1]
    case["spans"] = [span(2, 8)]
    case["parts"].update(chart=[span(3), span(5)], author_analysis=[span(4, cast_index=0), span(6, cast_index=1), span(7)],
                         feedback=[span(8)], post_feedback_analysis=[])
    case["cast"].update(diagram_spans=[span(3)], relationship="自占")
    second = copy.deepcopy(case["cast"])
    second.update(line_values=[3, 1, 1, 1, 1, 1], diagram_spans=[span(5)], relationship="母亲代占")
    second["field_spans"]["line_values"] = [span(5)]
    case["additional_casts"] = [second]
    write_json(root / "data/manual_slices/book.json", manifest)
    return manifest


def test_fresh_build_approved_units_fts_roles_and_manual_calculation(tmp_path, monkeypatch):
    source, manifest, lines = fixture_source(tmp_path)
    audit_cast(tmp_path, manifest)
    # Any attempt to reconstruct boundaries with the old parser must fail.
    import liuyao_mcp.ingest as old_ingest
    def forbidden(*args, **kwargs):
        raise AssertionError("old parser was called")
    monkeypatch.setattr(old_ingest, "extract_cases", forbidden)
    monkeypatch.setattr(old_ingest, "import_source", forbidden)
    out = tmp_path / "knowledge.sqlite"
    with closing(sqlite3.connect(out)) as db:
        db.execute("CREATE TABLE old_business_rows(payload TEXT)")
        db.execute("INSERT INTO old_business_rows VALUES('STALE')")
        db.commit()
    report = build_database(tmp_path, out)
    assert report["status"] == "complete" and report["total_chunks"] == report["total_cases"] == 1
    with closing(sqlite3.connect(out)) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='old_business_rows'").fetchone() is None
        assert db.execute("SELECT evidence_id FROM search_index WHERE search_index MATCH '求职' AND kind='case'").fetchone() == ("manual.case",)
        assert db.execute("SELECT evidence_id FROM search_index WHERE search_index MATCH '用神' AND kind='rule'").fetchone() == ("manual.rule",)
        case = json.loads(db.execute("SELECT payload FROM cases").fetchone()[0])
        search_text = case_search_text(case)
        assert "已投简历" in search_text
        for secret in ("最终未录用", "事后分析", "另有所指", "丑日可成"):
            assert secret not in search_text
        assert case["interpretations"][0]["original_text"] == "作者断：父母为用，丑日可成。"
        assert case["outcome"]["quotes"] == ["反馈：最终未录用。"]
        assert case["post_feedback_analysis"]["exact_text"] == "事后分析：另有所指。"
        assert case["extraction"]["chart_validation"] == "calculated"
        assert case["extraction"]["source_chart_independently_verified"] is True
        assert case["cast"].get("year_ganzhi") is None
        feedback_span = case["parts"]["feedback"]["source_spans"][0]
        assert lines[3][feedback_span["start_column"]:feedback_span["end_column"]] == "反馈：最终未录用。"
        metadata, body = db.execute("SELECT metadata,body FROM sources").fetchone()
        metadata = json.loads(metadata)
        assert body == "\n".join(lines) and metadata["sha256"] == digest(body)
        assert metadata["source_sha256"] == source["sha256"]
        assert metadata["text_schema"] == "canonical-1" and metadata["canonical_line_count"] == 4
        assert db.execute("SELECT value FROM build_info WHERE key='mode'").fetchone()[0] == "manual-corpus"
    assert build_database(tmp_path, out)["corpus_hash"] == report["corpus_hash"]


def test_unapproved_units_reported_and_strict_failure_preserves_database(tmp_path):
    _, manifest, _ = fixture_source(tmp_path)
    manifest["units"][0]["review"] = {"status": "draft"}
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    out = tmp_path / "knowledge.sqlite"
    out.write_bytes(b"existing database must survive a rejected build")
    with pytest.raises(IncompleteCorpusError) as caught:
        build_database(tmp_path, out)
    assert out.read_bytes() == b"existing database must survive a rejected build"
    assert caught.value.report["total_unapproved_units"] == 1
    assert caught.value.report["sources"][0]["unapproved_units"][0]["unit_id"] == "manual.rule"
    report = build_database(tmp_path, out, allow_partial=True)
    assert report["status"] == "incomplete" and report["total_chunks"] == 0 and report["total_cases"] == 1


def test_coverage_tracks_partial_lines_and_explicit_reviewed_exclusions(tmp_path):
    _, manifest, lines = fixture_source(tmp_path)
    first = manifest["units"][0]["spans"][0]
    first.update(end_column=4, exact_text=lines[0][:4], quote_sha256=digest(lines[0][:4]))
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    with pytest.raises(IncompleteCorpusError) as caught:
        build_database(tmp_path)
    coverage = caught.value.report["sources"][0]
    assert coverage["coverage_ratio"] < 1
    assert coverage["uncovered_spans"] == [{"page": None, "start_line": 1, "end_line": 1, "start_column": 4, "end_column": len(lines[0])}]
    manifest["exclusions"] = [{"spans": coverage["uncovered_spans"], "reason": "fixture exclusion explicitly reviewed", "review": REVIEW}]
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    assert build_database(tmp_path)["status"] == "complete"


def test_missing_manifest_is_never_an_automatic_fallback(tmp_path):
    fixture_source(tmp_path)
    (tmp_path / "data/manual_slices/book.json").unlink()
    with pytest.raises(IncompleteCorpusError) as caught:
        build_database(tmp_path)
    assert caught.value.report["sources"][0]["manifest_missing"]
    report = build_database(tmp_path, allow_partial=True)
    assert report["total_cases"] == report["total_chunks"] == 0


def test_get_outline_uses_only_approved_manual_unit_labels(tmp_path):
    from liuyao_mcp.retrieval import get_outline
    _, manifest, _ = fixture_source(tmp_path)
    manifest["units"][0]["review"] = {"status": "draft"}
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    out = tmp_path / "knowledge.sqlite"
    build_database(tmp_path, out, allow_partial=True)
    books = get_outline(db_path=out)["items"]
    assert len(books) == 1 and books[0]["title_basis"] == "source_manifest"
    units = get_outline(source_id="book", db_path=out)["items"]
    assert len(units) == 1 and units[0]["title"] == "求职卦"
    assert units[0]["title_basis"] == "manual_unit_label"
    assert units[0]["source_spans"][0]["start_line"] == 2
    assert units[0]["related_cases"]["case_ids"] == ["manual.case"]


@pytest.mark.parametrize("explicit", [False, True])
def test_unknown_method_stays_unknown_and_only_matches_all_methods(tmp_path, explicit):
    from liuyao_mcp.retrieval import search_knowledge
    _, manifest, _ = fixture_source(tmp_path)
    for unit in manifest["units"]:
        if explicit:
            unit["method"] = "unknown"
        else:
            unit.pop("method")
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    out = tmp_path / "knowledge.sqlite"
    build_database(tmp_path, out)
    with closing(sqlite3.connect(out)) as db:
        assert db.execute("SELECT DISTINCT method FROM evidence_metadata").fetchall() == [("unknown",)]
        assert json.loads(db.execute("SELECT payload FROM cases").fetchone()[0])["method"] == "unknown"
        assert json.loads(db.execute("SELECT payload FROM chunks").fetchone()[0])["method"] == "unknown"
    found = search_knowledge("求职", kind="case", method="all", db_path=out)
    assert [item["evidence_id"] for item in found["items"]] == ["manual.case"]
    assert found["items"][0]["method"] == "unknown"
    for method in ("lifa", "xiangfa"):
        assert search_knowledge("求职", kind="case", method=method, db_path=out)["items"] == []


def test_case_without_reported_feedback_is_preserved_without_claiming_an_outcome(tmp_path):
    source, manifest, lines = fixture_source(tmp_path)
    case = manifest["units"][1]
    lines[3] = case["parts"]["author_analysis"][0]["exact_text"]
    blob = "\r\n".join(lines).encode("utf-8")
    (tmp_path / "source.md").write_bytes(blob)
    source["sha256"] = manifest["source_sha256"] = hashlib.sha256(blob).hexdigest()
    write_json(tmp_path / "data/canonical/sources.jsonl", source)
    case["spans"][0].update(exact_text="\n".join(lines[1:]), quote_sha256=digest("\n".join(lines[1:])))
    case["parts"]["feedback"] = []
    case["parts"]["post_feedback_analysis"] = []
    case["quality"] = {"status": "noise", "reason": "未报告实际反馈，不能检验原问", "reviewer": "fixture quality reviewer"}
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    report = build_database(tmp_path)
    assert report["total_cases"] == 1
    with closing(sqlite3.connect(tmp_path / "data/knowledge.sqlite")) as db:
        saved = json.loads(db.execute("SELECT payload FROM cases").fetchone()[0])
        assert saved["outcome"]["status"] == "none"
        assert saved["outcome"]["quotes"] == []
        assert saved["outcome"]["independently_verified"] is False
        assert saved["parts"]["feedback"]["exact_text"] == ""
        assert saved["interpretations"][0]["original_text"] == lines[3]


def test_manual_classification_preserves_common_scope_and_explicit_topic_retrieval(tmp_path):
    from liuyao_mcp.retrieval import search_knowledge
    source, manifest, lines = fixture_source(tmp_path)
    rule = manifest["units"][0]
    rule["title"] = "元神受伤的一般生克原则"
    lines[0] = "元神受伤时，须看用神是否得生。"
    rule["spans"][0].update(exact_text=lines[0], quote_sha256=digest(lines[0]))
    blob = "\r\n".join(lines).encode("utf-8")
    (tmp_path / "source.md").write_bytes(blob)
    source["sha256"] = manifest["source_sha256"] = hashlib.sha256(blob).hexdigest()
    write_json(tmp_path / "data/canonical/sources.jsonl", source)
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    out = tmp_path / "knowledge.sqlite"
    build_database(tmp_path, out)
    with closing(sqlite3.connect(out)) as db:
        saved = json.loads(db.execute("SELECT payload FROM chunks").fetchone()[0])
        assert saved["classification"]["scope"] == "common"
        assert saved["classification"]["roots"] == []
        assert saved["classification"]["basis"] == "manual_slice_review"
        case = json.loads(db.execute("SELECT payload FROM cases").fetchone()[0])
        assert case["classification"]["scope"] == "case"
        assert case["classification"]["roots"] == ["job"]
        assert case["classification"]["topic_ids"] == ["job/job_search"]
    found = search_knowledge("求职", kind="case", topic="job", subtopic="job/job_search", db_path=out)
    assert [item["evidence_id"] for item in found["items"]] == ["manual.case"]


def test_missing_manual_classification_stays_unknown_despite_text_keywords(tmp_path):
    _, manifest, _ = fixture_source(tmp_path)
    for unit in manifest["units"]:
        unit.pop("scope")
        unit.pop("topic_ids")
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    build_database(tmp_path)
    with closing(sqlite3.connect(tmp_path / "data/knowledge.sqlite")) as db:
        for table in ("chunks", "cases"):
            saved = json.loads(db.execute(f"SELECT payload FROM {table}").fetchone()[0])
            classification = saved["classification"]
            assert classification["status"] == "unknown" and classification["topic"] is None
            assert classification["roots"] == classification["topic_ids"] == []
            assert classification["scope"] == ("case" if table == "cases" else "unknown")
            assert classification["basis"] == "not_annotated"


def test_manual_classification_rejects_unknown_taxonomy_ids(tmp_path):
    _, manifest, _ = fixture_source(tmp_path)
    manifest["units"][1]["topic_ids"] = ["health/not_a_taxonomy_id"]
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    with pytest.raises(ValueError, match="known taxonomy IDs"):
        build_database(tmp_path)


@pytest.mark.parametrize("contradictory_overlap", [False, True])
def test_late_disclosed_background_retains_span_metadata_but_never_enters_initial_input(tmp_path, contradictory_overlap):
    from liuyao_mcp.retrieval import get_source
    source, manifest, lines = fixture_source(tmp_path)
    case = manifest["units"][1]
    late_text = "事后才说：大学同学且恋爱三年。"
    start = len(lines[1])
    lines[1] += late_text
    blob = "\r\n".join(lines).encode("utf-8")
    (tmp_path / "source.md").write_bytes(blob)
    source["sha256"] = manifest["source_sha256"] = hashlib.sha256(blob).hexdigest()
    write_json(tmp_path / "data/canonical/sources.jsonl", source)
    case["spans"][0].update(exact_text="\n".join(lines[1:]), quote_sha256=digest("\n".join(lines[1:])))
    early = case["parts"]["background"][0]
    early.update(disclosure_phase="before_initial_prediction", eligible_for_initial_blind_input=True, speaker="求测者")
    late = {"page": None, "start_line": 2, "end_line": 2, "start_column": start, "end_column": len(lines[1]),
            "exact_text": late_text, "quote_sha256": digest(late_text), "disclosure_phase": "after_initial_prediction",
            "eligible_for_initial_blind_input": False, "speaker": "求测者", "cast_index": 0,
            "review_note": {"basis": "explicit_later_disclosure"}}
    case["parts"]["background"].append(late)
    if contradictory_overlap:
        case["parts"]["question"].append(dict(late))
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    out = tmp_path / "knowledge.sqlite"
    if contradictory_overlap:
        with pytest.raises(ValueError, match="late-disclosed background overlaps"):
            build_database(tmp_path, out)
        return
    build_database(tmp_path, out)
    with closing(sqlite3.connect(out)) as db:
        saved = json.loads(db.execute("SELECT payload FROM cases").fetchone()[0])
        assert saved["question"]["known_background"] == "背景：已投简历。"
        assert saved["question"]["background"] == "背景：已投简历。"
        assert "大学同学" not in saved["question"]["raw"] and "恋爱三年" not in case_search_text(saved)
        assert "已投简历" in case_search_text(saved)
        assert db.execute("SELECT evidence_id FROM search_index WHERE search_index MATCH '大学' AND kind='case'").fetchall() == []
        assert "大学" not in db.execute("SELECT body FROM search_index WHERE kind='case'").fetchone()[0]
        assert late_text in saved["parts"]["background"]["exact_text"]
        assert late_text in saved["source"]["original_text"]
    structured = get_source("manual.case", db_path=out)["structured_case"]
    background = structured["parts"]["background"]
    for key in ("source_spans", "canonical_spans"):
        assert background[key][1]["disclosure_phase"] == "after_initial_prediction"
        assert background[key][1]["eligible_for_initial_blind_input"] is False
        assert background[key][1]["speaker"] == "求测者"
        assert background[key][1]["cast_index"] == 0
        assert background[key][1]["review_note"] == {"basis": "explicit_later_disclosure"}
        assert background[key][0]["disclosure_phase"] == "before_initial_prediction"


def test_only_explicit_manual_event_ids_group_records(tmp_path):
    _, manifest, _ = fixture_source(tmp_path)
    first = manifest["units"][1]
    first["event_id"] = "reviewed.same.event"
    second = copy.deepcopy(first)
    second["unit_id"] = "another.manual.case"
    manifest["units"].append(second)
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    assert build_database(tmp_path)["total_case_events"] == 1
    with closing(sqlite3.connect(tmp_path / "data/knowledge.sqlite")) as db:
        case = json.loads(db.execute("SELECT payload FROM cases WHERE id='manual.case'").fetchone()[0])
        assert case["duplicate_candidates"] == ["another.manual.case"]
        assert case["duplicate_group_basis"] == "manual_event_id"
    del second["event_id"]
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    assert build_database(tmp_path)["total_case_events"] == 2


def test_two_casts_keep_separate_features_queries_and_one_shared_event(tmp_path):
    from liuyao_mcp.retrieval import get_outline, search_knowledge
    manifest = fixture_two_casts(tmp_path)
    audit_cast(tmp_path, manifest)
    audit_cast(tmp_path, manifest, cast_index=1)
    out = tmp_path / "knowledge.sqlite"
    report = build_database(tmp_path, out)
    assert report["total_case_units"] == report["total_case_events"] == 1
    assert report["total_cases"] == 2 and report["sources"][0]["approved_units"] == 2
    with closing(sqlite3.connect(out)) as db:
        records = [json.loads(row[0]) for row in db.execute("SELECT payload FROM cases ORDER BY id")]
        assert [r["case_id"] for r in records] == ["manual.case", "manual.case.cast2"]
        assert [r["features"]["moving_positions"] for r in records] == [[4], [1]]
        assert {r["duplicate_group"] for r in records} == {"manual.case"}
        assert records[0]["source"] == records[1]["source"]
        assert records[0]["outcome"] == records[1]["outcome"]
        for index, record in enumerate(records):
            assert record["additional_casts"] == manifest["units"][1]["additional_casts"]
            assert record["related_case_ids"] == [records[1 - index]["case_id"]]
            assert [entry["relationship"] for entry in record["cast_sequence"]] == ["自占", "母亲代占"]
            assert [entry["cast_index"] for entry in record["cast_sequence"]] == [0, 1]
            assert [item["cast_attribution"] for item in record["interpretations"]] == ["explicit", "unspecified"]
            assert record["interpretations"][0]["cast_index"] == index
            assert record["interpretations"][1]["original_text"] == "总论：不可拘泥。"
            assert len(record["parts"]["author_analysis"]["source_spans"]) == 2
    units = get_outline(source_id="book", db_path=out)["items"]
    case_nodes = [node for node in units if node["related_cases"]["total_cases"]]
    assert len(case_nodes) == 1 and case_nodes[0]["related_cases"]["total_cases"] == 2
    for moving, expected in (([4], "manual.case"), ([1], "manual.case.cast2")):
        found = search_knowledge("", kind="case", features={"moving_positions": moving}, db_path=out)
        assert [item["evidence_id"] for item in found["items"]] == [expected]
    excluded = search_knowledge("", kind="case", features={"moving_positions": [1]}, exclude_case_ids=["manual.case"], db_path=out)
    assert excluded["items"] == []


@pytest.mark.parametrize("verified_index", [None, 0, 1])
def test_each_cast_requires_its_own_independent_verification(tmp_path, verified_index):
    manifest = fixture_two_casts(tmp_path)
    if verified_index is not None:
        audit_cast(tmp_path, manifest, cast_index=verified_index)
    build_database(tmp_path)
    with closing(sqlite3.connect(tmp_path / "data/knowledge.sqlite")) as db:
        records = [json.loads(row[0]) for row in db.execute("SELECT payload FROM cases ORDER BY id")]
        for index, record in enumerate(records):
            expected = "calculated" if index == verified_index else "not_run"
            assert record["extraction"]["chart_validation"] == expected
            assert ("moving_positions" in record["features"]) == (index == verified_index)
            assert record["cast"]["line_values"] == ([1, 1, 1, 3, 1, 1] if index == 0 else [3, 1, 1, 1, 1, 1])


def test_text_only_case_remains_one_record_and_event(tmp_path):
    _, manifest, _ = fixture_source(tmp_path)
    manifest["units"][1]["cast"] = {}
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    report = build_database(tmp_path)
    assert report["total_case_units"] == report["total_cases"] == report["total_case_events"] == 1
    with closing(sqlite3.connect(tmp_path / "data/knowledge.sqlite")) as db:
        case = json.loads(db.execute("SELECT payload FROM cases").fetchone()[0])
        assert case["derived"] is None and case["extraction"]["chart_validation"] == "not_run"


def test_reported_recast_without_diagram_does_not_inherit_previous_cast(tmp_path):
    manifest = fixture_two_casts(tmp_path)
    second = manifest["units"][1]["additional_casts"][0]
    second.update(line_values=None, diagram_spans=[], relationship="原文只称又得此卦，未列新图")
    second["field_spans"].pop("line_values")
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    report = build_database(tmp_path)
    assert report["total_cases"] == 2 and report["total_case_events"] == 1
    with closing(sqlite3.connect(tmp_path / "data/knowledge.sqlite")) as db:
        record = json.loads(db.execute("SELECT payload FROM cases WHERE id='manual.case.cast2'").fetchone()[0])
        assert record["cast"]["line_values"] is None and record["derived"] is None
        assert record["parts"]["chart"]["source_spans"] == []
        assert record["extraction"]["chart_validation"] == "not_run"
    second["line_values"] = [3, 1, 1, 1, 1, 1]
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    with pytest.raises(ValueError, match="diagram_spans"):
        build_database(tmp_path)


@pytest.mark.parametrize("verified", [False, True])
def test_manual_author_choice_has_source_proof_and_only_verified_chart_candidates(tmp_path, verified):
    from liuyao_mcp.retrieval import search_knowledge
    _, manifest, _ = fixture_source(tmp_path)
    case = manifest["units"][1]
    case["author_yongshen"] = [{"relative": "父母", "spans": case["parts"]["author_analysis"]}]
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    if verified:
        audit_cast(tmp_path, manifest)
    out = tmp_path / "data/knowledge.sqlite"
    build_database(tmp_path, out)
    with closing(sqlite3.connect(out)) as db:
        record = json.loads(db.execute("SELECT payload FROM cases").fetchone()[0])
        assert record["features"]["yongshen_reported"] == ["父母"]
        assert record["interpretations"][0]["yongshen_reported"] == ["父母"]
        assert record["author_yongshen"][0]["exact_text"] == case["parts"]["author_analysis"][0]["exact_text"]
        assert bool(record["features"].get("yongshen_candidates")) == verified
    found = search_knowledge("", kind="case", features={"yongshen_relative": "父母", "yongshen_scope": "primary"}, db_path=out)
    assert bool(found["items"]) == verified
    case["author_yongshen"][0]["spans"] = case["parts"]["feedback"]
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    with pytest.raises(ValueError, match="outside"):
        build_database(tmp_path, out)


def test_manual_author_choice_is_attributed_to_its_own_cast(tmp_path):
    manifest = fixture_two_casts(tmp_path)
    case = manifest["units"][1]
    statement = {"relative": "子孙", "spans": [case["parts"]["author_analysis"][1]]}
    case["author_yongshen"] = [statement]
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    with pytest.raises(ValueError, match="cast_index"):
        build_database(tmp_path)
    statement["cast_index"] = 1
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    build_database(tmp_path)
    with closing(sqlite3.connect(tmp_path / "data/knowledge.sqlite")) as db:
        records = [json.loads(row[0]) for row in db.execute("SELECT payload FROM cases ORDER BY id")]
        assert records[0]["features"]["yongshen_reported"] is None
        assert records[1]["features"]["yongshen_reported"] == ["子孙"]


@pytest.mark.parametrize("bad_field", ["diagram_spans", "cast_index"])
def test_multiple_casts_reject_ambiguous_diagrams_or_invalid_role_index(tmp_path, bad_field):
    manifest = fixture_two_casts(tmp_path)
    case = manifest["units"][1]
    if bad_field == "diagram_spans":
        del case["additional_casts"][0]["diagram_spans"]
    else:
        case["parts"]["author_analysis"][0]["cast_index"] = 2
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    with pytest.raises(ValueError, match=bad_field):
        build_database(tmp_path)


@pytest.mark.parametrize("field", ["source_sha256", "exact_text", "quote_sha256"])
def test_manifest_hash_and_quotes_are_verified(tmp_path, field):
    _, manifest, _ = fixture_source(tmp_path)
    if field == "source_sha256":
        manifest[field] = "0" * 64
    else:
        manifest["units"][0]["spans"][0][field] = "wrong"
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    with pytest.raises(ValueError, match="mismatch"):
        build_database(tmp_path, allow_partial=True)


def test_feedback_cannot_overlap_searchable_or_author_roles(tmp_path):
    _, manifest, _ = fixture_source(tmp_path)
    case = manifest["units"][1]
    case["parts"]["question"].extend(case["parts"]["feedback"])
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    with pytest.raises(ValueError, match="case roles overlap: question / feedback"):
        build_database(tmp_path)


def test_missing_cast_inputs_stay_not_run_and_unsourced_inputs_rejected(tmp_path):
    _, manifest, _ = fixture_source(tmp_path)
    cast = manifest["units"][1]["cast"]
    cast["line_values"] = None
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    build_database(tmp_path)
    with closing(sqlite3.connect(tmp_path / "data/knowledge.sqlite")) as db:
        case = json.loads(db.execute("SELECT payload FROM cases").fetchone()[0])
        assert case["extraction"]["chart_validation"] == "not_run" and case["derived"] is None
        assert db.execute("SELECT chart_valid FROM evidence_metadata WHERE kind='case'").fetchone()[0] == 0
    cast["line_values"] = [1] * 6
    del cast["field_spans"]["line_values"]
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    with pytest.raises(ValueError, match="line_values requires explicit source evidence"):
        build_database(tmp_path)


def test_mechanical_success_without_independent_audit_is_not_validated(tmp_path):
    fixture_source(tmp_path)
    build_database(tmp_path)
    with closing(sqlite3.connect(tmp_path / "data/knowledge.sqlite")) as db:
        case = json.loads(db.execute("SELECT payload FROM cases").fetchone()[0])
        assert case["extraction"]["chart_validation"] == "not_run"
        assert case["extraction"]["computed"] is True and case["derived"] is not None
        assert case["extraction"]["source_chart_independently_verified"] is False
        assert "shi_relative" not in case["features"]
        assert db.execute("SELECT chart_valid FROM evidence_metadata WHERE kind='case'").fetchone()[0] == 0
        assert db.execute("SELECT body FROM search_index WHERE kind='case'").fetchone()[0].find("乾为天") == -1


@pytest.mark.parametrize("field", ["source_sha256", "input_line_values", "day_ganzhi", "chart_text_sha256", "status", "unit_id", "file_hash"])
def test_independent_cast_audit_must_match_current_manual_unit(tmp_path, field):
    _, manifest, _ = fixture_source(tmp_path)
    path, record = audit_cast(tmp_path, manifest)
    if field == "file_hash":
        path.write_bytes(b"changed audit")
    else:
        record[field] = "changed"
        write_json(path, {"records": [record]})
        manifest["units"][1]["cast"]["verification"]["evidence_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        write_json(tmp_path / "data/manual_slices/book.json", manifest)
    with pytest.raises(ValueError, match="cast verification"):
        build_database(tmp_path)


def test_pdf_uses_only_canonical_pages_and_reports_missing_pages(tmp_path):
    source = {"source_id": "pdf", "title": "PDF", "source_type": "ocr_text", "path": "old-ocr-must-not-be-read.md",
              "sha256": "0" * 64, "original_pdf_sha256": "a" * 64, "pdf_pages": 2, "method_hint": "lifa"}
    write_json(tmp_path / "data/canonical/sources.jsonl", source)
    text = "用神取法。\n"
    write_json(tmp_path / "data/canonical/pdf.jsonl", {"page": 2, "text": text, "text_sha256": digest(text),
               "provenance": {"method": "fresh_extraction", "review_status": "method_sample_checked", "original_pdf_sha256": "a" * 64}})
    write_json(tmp_path / "data/manual_slices/pdf.json", {"schema_version": "manual-slices-1", "source_id": "pdf", "source_sha256": "a" * 64,
               "units": [{"unit_id": "pdf.manual", "kind": "rule", "title": "用神", "method": "lifa", "review": REVIEW,
                          "spans": [{"page": 2, "start_line": 1, "end_line": 1, "exact_text": "用神取法。"}]}]})
    with pytest.raises(IncompleteCorpusError) as caught:
        build_database(tmp_path)
    assert caught.value.report["sources"][0]["missing_pages"] == [1]
    report = build_database(tmp_path, allow_partial=True)
    assert report["sources"][0]["page_review_status"] == {"method_sample_checked": 1}
    with closing(sqlite3.connect(tmp_path / "data/knowledge.sqlite")) as db:
        metadata, body = db.execute("SELECT metadata,body FROM sources").fetchone()
        metadata = json.loads(metadata)
        assert body.endswith(text) and metadata["canonical_line_count"] == 3
        assert metadata["original_mapping_status"] == "unavailable_old_ocr_lines"
        assert db.execute("SELECT count(*) FROM original_sources").fetchone()[0] == 0
        rule = json.loads(db.execute("SELECT payload FROM chunks").fetchone()[0])
        assert rule["source_spans"] == [{"start_line": 2, "end_line": 2, "start_column": 0, "end_column": 5}]


def test_shared_rule_context_is_indexed_but_does_not_expand_primary_coverage(tmp_path):
    source, manifest, lines = fixture_source(tmp_path)
    context_text = "共享限制：伏神须先看飞神旺衰。"
    lines.append(context_text)
    blob = "\r\n".join(lines).encode("utf-8")
    (tmp_path / "source.md").write_bytes(blob)
    source["sha256"] = manifest["source_sha256"] = hashlib.sha256(blob).hexdigest()
    write_json(tmp_path / "data/canonical/sources.jsonl", source)
    manifest["units"][0]["context_spans"] = [{"page": None, "start_line": 5, "end_line": 5,
        "exact_text": context_text, "quote_sha256": digest(context_text), "role": "shared_introduction", "author": "原作者"}]
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    report = build_database(tmp_path, allow_partial=True)
    coverage = report["sources"][0]
    assert coverage["covered_nonwhitespace_chars"] == sum(not char.isspace() for line in lines[:4] for char in line)
    assert coverage["uncovered_spans"][0]["start_line"] == 5
    with closing(sqlite3.connect(tmp_path / "data/knowledge.sqlite")) as db:
        rule = json.loads(db.execute("SELECT payload FROM chunks").fetchone()[0])
        context = rule["required_contexts"][0]
        assert context["text"] == context["exact_text"] == context_text
        assert context["source_spans"][0]["start_line"] == context["canonical_spans"][0]["start_line"] == 5
        assert context["role"] == "shared_introduction" and context["author"] == "原作者"
        assert db.execute("SELECT evidence_id FROM search_index WHERE search_index MATCH '伏神' AND kind='rule'").fetchall() == [("manual.rule",)]
    manifest["units"][0]["context_spans"][0]["quote_sha256"] = "0" * 64
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    with pytest.raises(ValueError, match="quote_sha256 mismatch"):
        build_database(tmp_path, allow_partial=True)


def test_rule_context_cannot_index_case_feedback(tmp_path):
    _, manifest, _ = fixture_source(tmp_path)
    manifest["units"][0]["context_spans"] = manifest["units"][1]["parts"]["feedback"]
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    with pytest.raises(ValueError, match="shared rule context overlaps case feedback"):
        build_database(tmp_path)


def fixture_pdf_page(root):
    source = {"source_id": "pdf", "title": "测试PDF", "source_type": "ocr_text", "path": "old-ocr-unavailable.md",
              "sha256": "0" * 64, "original_pdf_sha256": "a" * 64, "pdf_pages": 1, "method_hint": "lifa"}
    text = "用神宜旺。\n"
    record = {"source_id": "pdf", "page": 1, "text": text, "text_sha256": digest(text),
              "provenance": {"method": "fresh_extraction", "review_status": "machine_extracted", "original_pdf_sha256": "a" * 64,
                             "cache_page": "/machine-a/cache/1.json", "engine_versions": {"ocr": "1.0"}}}
    write_json(root / "data/canonical/sources.jsonl", source)
    write_json(root / "data/canonical/pdf.jsonl", record)
    manifest = {"schema_version": "manual-slices-1", "source_id": "pdf", "source_sha256": "a" * 64,
                "units": [{"unit_id": "pdf.rule", "kind": "rule", "title": "测试规则", "method": "lifa", "scope": "common", "review": REVIEW,
                           "spans": [{"page": 1, "start_line": 1, "end_line": 1, "exact_text": text.rstrip("\n"), "quote_sha256": digest(text.rstrip("\n"))}]}]}
    write_json(root / "data/manual_slices/pdf.json", manifest)
    return record, manifest


def test_canonical_page_lookup_and_corrected_source_fts_share_one_document(tmp_path):
    from liuyao_mcp.retrieval import get_source
    record, manifest = fixture_pdf_page(tmp_path)
    out = tmp_path / "knowledge.sqlite"
    first = build_database(tmp_path, out)
    page = get_source("page:pdf:1", db_path=out)
    assert page["text"] == record["text"]
    with closing(sqlite3.connect(out)) as db:
        stored = json.loads(db.execute("SELECT payload FROM ocr_pages").fetchone()[0])
        body = db.execute("SELECT body FROM sources").fetchone()[0]
        assert stored["canonical_text"] == "\n".join(body.split("\n")[1:]) == page["text"]
        assert stored["visual_reviewed"] is False and stored["status"] == "canonical_machine"
        assert "reviewed_text" not in stored
    corrected = "元神宜旺。\n"
    write_json(tmp_path / "data/proofread_pages/pdf/0001.json", {"source_id": "pdf", "pdf_page": 1, "pdf_sha256": "a" * 64,
        "original_sha256": "0" * 64, "status": "visually_checked", "text": corrected, "method": "word_by_word",
        "review_date": "2026-09-11", "normalization": "canonical LF", "unclear": []})
    with pytest.raises(ValueError, match="exact_text mismatch"):
        build_database(tmp_path, out)
    assert get_source("page:pdf:1", db_path=out)["text"] == record["text"]
    manifest["units"][0]["spans"][0].update(exact_text=corrected.rstrip("\n"), quote_sha256=digest(corrected.rstrip("\n")))
    write_json(tmp_path / "data/manual_slices/pdf.json", manifest)
    second = build_database(tmp_path, out)
    assert second["corpus_hash"] != first["corpus_hash"]
    assert get_source("page:pdf:1", db_path=out)["text"] == corrected
    assert get_source("pdf.rule", db_path=out)["text"] == corrected.rstrip("\n")
    with closing(sqlite3.connect(out)) as db:
        stored = json.loads(db.execute("SELECT payload FROM ocr_pages").fetchone()[0])
        body = db.execute("SELECT body FROM sources").fetchone()[0]
        assert stored["reviewed_text"] == stored["canonical_text"] == "\n".join(body.split("\n")[1:]) == corrected
        assert stored["visual_reviewed"] is True and stored["provenance"]["review_status"] == "visually_reviewed"
        assert db.execute("SELECT evidence_id FROM search_index WHERE search_index MATCH '元神'").fetchall() == [("pdf.rule",)]
        assert db.execute("SELECT evidence_id FROM search_index WHERE search_index MATCH '用神'").fetchall() == []


def test_review_semantics_change_hash_but_absolute_cache_locations_do_not(tmp_path):
    record, _ = fixture_pdf_page(tmp_path)
    first = build_database(tmp_path)
    record["provenance"]["cache_page"] = "D:\\another-machine\\cache\\1.json"
    write_json(tmp_path / "data/canonical/pdf.jsonl", record)
    assert build_database(tmp_path)["corpus_hash"] == first["corpus_hash"]
    record["provenance"]["review_note"] = "independent method sample confirmed"
    write_json(tmp_path / "data/canonical/pdf.jsonl", record)
    changed = build_database(tmp_path)
    assert changed["corpus_hash"] != first["corpus_hash"]
    assert changed["sources"][0]["page_provenance_sha256"] != first["sources"][0]["page_provenance_sha256"]


def test_manual_rule_registry_is_compiled_resolvable_and_part_of_corpus_hash(tmp_path):
    from liuyao_mcp.rule_references import resolve_rule_reference
    fixture_source(tmp_path)
    out = tmp_path / "knowledge.sqlite"
    first = build_database(tmp_path, out)
    entry = {"concept": "用神规则", "source_id": "book", "status": "mapped", "target_ids": ["manual.rule"], "legacy_ids": ["old_rule"]}
    path = tmp_path / "data/manual_slices/rule_references.json"
    write_json(path, {"schema_version": "rule-references-1", "references": {"lifa.yongshen": entry}})
    mapped = build_database(tmp_path, out)
    assert mapped["corpus_hash"] != first["corpus_hash"] and mapped["total_rule_references"] == 1
    path.unlink()
    result = resolve_rule_reference("old_rule", out)
    assert result["status"] == "available" and result["source_rule_ids"] == ["manual.rule"]


def quality_sidecar(root, manifest):
    case = manifest["units"][1]
    review = {"schema_version": "case-quality-1", "source_id": manifest["source_id"], "source_sha256": manifest["source_sha256"],
              "reviews": [{"unit_id": case["unit_id"], "unit_text_sha256": digest("\n".join(span["exact_text"] for span in case["spans"])),
                           "status": "eligible", "reason": "原问与实际反馈明确对应，原断失败仍可核验", "reviewer": "sidecar reviewer"}]}
    write_json(root / "data/manual_slices/quality_reviews/book.json", review)
    return review


@pytest.mark.parametrize("status", ["noise", "pending"])
def test_ineligible_quality_keeps_archive_but_excludes_fts_and_structure(tmp_path, status):
    from liuyao_mcp.retrieval import get_source, search_knowledge
    _, manifest, _ = fixture_source(tmp_path)
    manifest["units"][1]["quality"] = {"status": status, "reason": "反馈与原问关系待核实", "reviewer": "quality reviewer"}
    audit_cast(tmp_path, manifest)
    out = tmp_path / "knowledge.sqlite"
    report = build_database(tmp_path, out)
    assert report["case_quality"] == {status: 1}
    archived = get_source("manual.case", db_path=out)
    assert "最终未录用" in archived["text"]
    assert archived["structured_case"]["quality"]["status"] == status
    assert archived["structured_case"]["extraction"]["chart_validation"] == "calculated"
    archive_node = get_source(archived["outline"]["node_id"], db_path=out)
    assert archive_node["related_cases"]["quality_counts"] == {status: 1}
    assert archive_node["related_cases"]["eligible_case_ids"] == []
    assert search_knowledge("求职", kind="case", db_path=out)["items"] == []
    assert search_knowledge("", kind="case", features={"moving_positions": [4]}, db_path=out)["items"] == []
    with closing(sqlite3.connect(out)) as db:
        assert db.execute("SELECT count(*) FROM cases").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM search_index WHERE kind='case'").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM case_features").fetchone()[0] == 0
        assert db.execute("SELECT searchable,chart_valid FROM evidence_metadata WHERE kind='case'").fetchone() == (0, 1)
        assert db.execute("SELECT evidence_id FROM search_index WHERE search_index MATCH '用神' AND kind='rule'").fetchone() == ("manual.rule",)


def test_case_without_quality_declaration_defaults_to_pending(tmp_path):
    from liuyao_mcp.retrieval import get_source, search_knowledge
    _, manifest, _ = fixture_source(tmp_path)
    del manifest["units"][1]["quality"]
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    out = tmp_path / "knowledge.sqlite"
    build_database(tmp_path, out)
    quality = get_source("manual.case", db_path=out)["structured_case"]["quality"]
    assert quality["status"] == "pending" and quality["reason"] == "quality_not_reviewed"
    assert search_knowledge("求职", kind="case", db_path=out)["items"] == []


def test_clear_failure_feedback_remains_eligible_and_summary_reports_quality(tmp_path):
    from liuyao_mcp.retrieval import get_source, search_knowledge
    fixture_source(tmp_path)
    out = tmp_path / "knowledge.sqlite"
    build_database(tmp_path, out)
    found = search_knowledge("求职", kind="case", db_path=out)
    assert found["items"][0]["case"]["quality"]["status"] == "eligible"
    archived = get_source("manual.case", db_path=out)["structured_case"]
    assert "丑日可成" in archived["interpretations"][0]["original_text"]
    assert archived["outcome"]["quotes"] == ["反馈：最终未录用。"]
    assert archived["quality"]["status"] == "eligible"


def test_actual_feedback_can_be_eligible_without_author_analysis(tmp_path):
    from liuyao_mcp.retrieval import get_source, search_knowledge
    source, manifest, lines = fixture_source(tmp_path)
    case = manifest["units"][1]
    lines[3] = "反馈：最终未录用。"
    blob = "\r\n".join(lines).encode("utf-8")
    (tmp_path / "source.md").write_bytes(blob)
    source["sha256"] = manifest["source_sha256"] = hashlib.sha256(blob).hexdigest()
    write_json(tmp_path / "data/canonical/sources.jsonl", source)
    case["spans"][0].update(exact_text="\n".join(lines[1:]), quote_sha256=digest("\n".join(lines[1:])))
    case["parts"]["author_analysis"] = case["parts"]["post_feedback_analysis"] = []
    case["parts"]["feedback"] = [{"page": None, "start_line": 4, "end_line": 4, "exact_text": lines[3]}]
    case["quality"]["reason"] = "有完整原问、起卦输入与实际反馈，可检验预测，不要求原作者断语"
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    out = tmp_path / "knowledge.sqlite"
    build_database(tmp_path, out)
    assert search_knowledge("求职", kind="case", db_path=out)["items"]
    assert get_source("manual.case", db_path=out)["structured_case"]["interpretations"] == []


def test_quality_sidecar_applies_and_inline_quality_takes_precedence(tmp_path):
    from liuyao_mcp.retrieval import get_source
    _, manifest, _ = fixture_source(tmp_path)
    del manifest["units"][1]["quality"]
    quality_sidecar(tmp_path, manifest)
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    out = tmp_path / "knowledge.sqlite"
    first = build_database(tmp_path, out)
    quality = get_source("manual.case", db_path=out)["structured_case"]["quality"]
    assert quality["status"] == "eligible" and quality["basis"] == "quality_review_sidecar"
    assert first["sources"][0]["quality_reviews_sha256"]
    manifest["units"][1]["quality"] = {"status": "noise", "reason": "后续人工复核发现关键原文冲突", "reviewer": "inline reviewer"}
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    second = build_database(tmp_path, out)
    quality = get_source("manual.case", db_path=out)["structured_case"]["quality"]
    assert quality["status"] == "noise" and quality["basis"] == "inline_manual_quality"
    assert first["corpus_hash"] != second["corpus_hash"]


def test_stale_quality_review_becomes_pending_when_unit_text_changes(tmp_path):
    from liuyao_mcp.retrieval import get_source, search_knowledge
    _, manifest, lines = fixture_source(tmp_path)
    case = manifest["units"][1]
    del case["quality"]
    quality_sidecar(tmp_path, manifest)
    old_hash = digest(case["spans"][0]["exact_text"])
    # Change the reviewed slice, keeping the original source identity intact.
    end = lines[3].index("事后分析")
    case["parts"]["post_feedback_analysis"] = []
    text = "\n".join(lines[1:3] + [lines[3][:end]])
    case["spans"][0].update(end_column=end, exact_text=text, quote_sha256=digest(text))
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    out = tmp_path / "knowledge.sqlite"
    build_database(tmp_path, out, allow_partial=True)
    quality = get_source("manual.case", db_path=out)["structured_case"]["quality"]
    assert quality["status"] == "pending" and quality["basis"] == "expired_quality_review"
    assert "stale_text" in quality["reason"]
    assert quality["unit_text_sha256"] == digest(text) != old_hash
    assert quality["previous_review"]["unit_text_sha256"] == old_hash
    assert search_knowledge("求职", kind="case", db_path=out)["items"] == []


@pytest.mark.parametrize("field", ["source_id", "source_sha256"])
def test_quality_sidecar_rejects_mismatched_source_identity(tmp_path, field):
    _, manifest, _ = fixture_source(tmp_path)
    sidecar = quality_sidecar(tmp_path, manifest)
    sidecar[field] = "wrong"
    write_json(tmp_path / "data/manual_slices/quality_reviews/book.json", sidecar)
    with pytest.raises(ValueError, match="case quality sidecar schema/source/SHA-256 mismatch"):
        build_database(tmp_path)


def test_pre_quality_database_rejects_case_and_rule_retrieval(tmp_path):
    from liuyao_mcp.retrieval import get_source, search_knowledge
    fixture_source(tmp_path)
    out = tmp_path / "knowledge.sqlite"
    build_database(tmp_path, out)
    with closing(sqlite3.connect(out)) as db:
        assert db.execute("SELECT value FROM build_info WHERE key='search_index_version'").fetchone()[0] == "manual-quality-1"
        db.execute("UPDATE build_info SET value='focused-3' WHERE key='search_index_version'")
        legacy = json.loads(db.execute("SELECT payload FROM cases").fetchone()[0])
        legacy.pop("quality")
        db.execute("UPDATE cases SET payload=?", (json.dumps(legacy, ensure_ascii=False),))
        db.commit()
    for kind in ("case", "rule"):
        with pytest.raises(ValueError, match="检索索引版本过旧"):
            search_knowledge("求职 用神", kind=kind, db_path=out)
    assert get_source("manual.case", db_path=out)["structured_case"]["quality"]["status"] == "pending"


@pytest.mark.parametrize("shared_context", [False, True])
def test_case_exclusion_uses_actual_rule_spans_and_required_contexts(tmp_path, shared_context):
    from liuyao_mcp.retrieval import search_knowledge
    source, manifest, lines = fixture_source(tmp_path)
    lines.append("用神通则的另一条独立限制。")
    blob = "\r\n".join(lines).encode("utf8")
    (tmp_path / "source.md").write_bytes(blob)
    source["sha256"] = manifest["source_sha256"] = hashlib.sha256(blob).hexdigest()
    write_json(tmp_path / "data/canonical/sources.jsonl", source)
    rule, case = manifest["units"]
    rule["spans"].append({"page": None, "start_line": 5, "end_line": 5,
                          "exact_text": lines[4], "quote_sha256": digest(lines[4])})
    if shared_context:
        rule["context_spans"] = case["parts"]["author_analysis"]
    write_json(tmp_path / "data/manual_slices/book.json", manifest)
    out = tmp_path / "knowledge.sqlite"
    build_database(tmp_path, out)
    assert search_knowledge("用神", kind="rule", db_path=out)["items"]
    found = search_knowledge("用神", kind="rule", exclude_case_ids=["manual.case"], db_path=out)
    assert [item["evidence_id"] for item in found["items"]] == ([] if shared_context else ["manual.rule"])
