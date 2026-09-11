import json
import sqlite3

import pytest

from liuyao_mcp.rule_references import load_mapping, resolve, resolve_rule_reference, store_mapping


def _entry(target_ids=(), status="mapped", legacy_ids=()):
    return {"concept": "测试概念", "source_id": "book", "legacy_ids": list(legacy_ids),
            "status": status, "target_ids": list(target_ids),
            "locator": {"kind": "chapter_navigation_only", "chapter": "测试章"},
            "source_scope": "原文定义", "algorithm_boundary": "候选不等于结论"}


def _mapping(tmp_path, entries):
    path = tmp_path / "data/manual_slices/rule_references.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "rule-references-1", "references": entries}), encoding="utf-8")
    return path


def _unit(**changes):
    return {"source_id": "book", "chapter": "人工批准正文", "content_role": "theory",
            "extraction": {"method": "approved_manual_slices"},
            "review": {"status": "approved", "reviewer": "reader", "basis": "direct_source_read"},
            "canonical_spans": [{"page": None, "start_line": 4, "end_line": 5}], **changes}


def test_mapping_is_compiled_and_legacy_alias_resolves_new_units(tmp_path):
    path = _mapping(tmp_path, {"lifa.example": _entry(["book.manual.rule"], legacy_ids=["old_ocr_rule_4520"])})
    database = tmp_path / "knowledge.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE chunks(id TEXT PRIMARY KEY, payload TEXT)")
        db.execute("INSERT INTO chunks VALUES (?, ?)", ("book.manual.rule", json.dumps(_unit())))
        assert store_mapping(db, tmp_path) == 1
    path.unlink()  # Installed runtime has only SQLite, not the build-time JSON.
    result = resolve_rule_reference("old_ocr_rule_4520", database)
    assert result["status"] == "available"
    assert result["reference_id"] == "lifa.example"
    assert result["legacy_alias"] == "old_ocr_rule_4520"
    assert result["source_rule_ids"] == ["book.manual.rule"]
    assert result["target_checks"][0]["canonical_spans"][0]["start_line"] == 4


def test_incomplete_or_unapproved_target_set_never_becomes_a_valid_citation(tmp_path):
    targets = ["approved", "missing", "unapproved", "automatic", "case_feedback", "wrong_book"]
    _mapping(tmp_path, {"lifa.example": _entry(targets)})
    units = {"approved": _unit(), "unapproved": _unit(review={"status": "pending"}),
             "automatic": _unit(extraction={"method": "source-parser"}),
             "case_feedback": _unit(content_role="case_analysis"),
             "wrong_book": _unit(source_id="another_book")}
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE chunks(id TEXT PRIMARY KEY, payload TEXT)")
        db.executemany("INSERT INTO chunks VALUES (?, ?)", ((key, json.dumps(value)) for key, value in units.items()))
        store_mapping(db, tmp_path)
        result = resolve(db, "lifa.example")
    assert result["status"] == "unavailable" and result["source_rule_ids"] == []
    assert [check.get("reason") for check in result["target_checks"]] == [
        None, "rule_target_missing", "target_not_approved", "not_manual_rule", "not_manual_rule", "target_source_mismatch"]


def test_unresolved_navigation_and_missing_registry_stay_unavailable(tmp_path):
    _mapping(tmp_path, {"xiangfa.example": _entry(status="unresolved", legacy_ids=["xf_old"])})
    with sqlite3.connect(":memory:") as db:
        assert resolve(db, "xf_old")["reason"] == "reference_registry_unavailable"
        store_mapping(db, tmp_path)
        unresolved = resolve(db, "xf_old")
        assert unresolved["status"] == "unavailable" and unresolved["source_rule_ids"] == []
        assert unresolved["locator"]["kind"] == "chapter_navigation_only"
        assert unresolved["reason"] == "unresolved_reference"
        assert resolve(db, "missing")["reason"] == "unknown_reference"
    assert resolve_rule_reference("xf_old", tmp_path / "absent.sqlite")["reason"] == "database_unavailable"


def test_duplicate_aliases_cannot_select_an_arbitrary_concept(tmp_path):
    _mapping(tmp_path, {"lifa.a": _entry(legacy_ids=["old_id"]), "lifa.b": _entry(legacy_ids=["old_id"])})
    with pytest.raises(ValueError, match="duplicate rule reference"):
        load_mapping(tmp_path)


def test_manual_catalog_covers_every_legacy_mechanical_reference():
    references = load_mapping()
    aliases = {alias for entry in references.values() for alias in entry["legacy_ids"]}
    expected = {"rule_liuyao_zixiu_dxj_4520", "rule_liuyao_zixiu_dxj_4784", "xf_shang_c03",
                "xf_xia_c05", "xf_xia_c08", "xf_xia_c09"}
    expected.update(f"xf_shang_c02_u{number:02}" for number in range(1, 19))
    expected.update(f"xf_xia_c04_s{number:02}" for number in range(1, 6))
    expected.update(f"xf_xia_c07_u{number:02}" for number in range(1, 3))
    expected.update(f"xf_xia_c10_u{number:02}" for number in range(1, 5))
    assert aliases == expected
    for entry in references.values():
        assert entry["locator"]["kind"] == "chapter_navigation_only"
        assert "start_line" not in entry["locator"] and "end_line" not in entry["locator"]
        assert entry["algorithm_boundary"]
        if entry["status"] == "unresolved":
            assert entry["target_ids"] == []


def _readable_database(tmp_path):
    from liuyao_mcp.ingest import SCHEMA

    database = tmp_path / "knowledge.sqlite"
    text = "人工规则正文。" * 180
    metadata = {"source_id": "book", "source_type": "native_text", "sha256": "a" * 64,
                "text_schema": "canonical-1", "canonical_line_count": 1}
    unit = _unit(start_line=1, end_line=1, source_spans=[{"start_line": 1, "end_line": 1}],
                 canonical_spans=[{"page": None, "start_line": 1, "end_line": 1}],
                 required_contexts=[{"text": "共同前提仍须读取。"}])
    with sqlite3.connect(database) as db:
        db.executescript(SCHEMA)
        db.execute("INSERT INTO sources VALUES (?, ?, ?)", ("book", json.dumps(metadata), text))
        for evidence_id in ("book.manual.a", "book.manual.b", "rule_liuyao_zixiu_dxj_4520"):
            db.execute("INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (evidence_id, "book", "passage", "lifa", "正文", 1, 1, "hash", json.dumps(unit)))
        node = {"node_id": "xf_xia_c06_u03", "title": "普通目录", "start_line": 1, "end_line": 1}
        db.execute("INSERT INTO outline_nodes VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (node["node_id"], "book", None, 0, 1, 1, json.dumps(node)))
    return database, text


def test_get_source_returns_reference_targets_and_preserves_direct_source_reads(tmp_path):
    from liuyao_mcp.retrieval import get_source

    database, text = _readable_database(tmp_path)
    _mapping(tmp_path, {"lifa.example": _entry(["book.manual.a", "book.manual.b"],
                                               legacy_ids=["rule_liuyao_zixiu_dxj_4520", "custom_alias"]),
                        "xiangfa.waiting": _entry(status="unresolved", legacy_ids=["xf_xia_c09"])})
    with sqlite3.connect(database) as db:
        store_mapping(db, tmp_path)
    for reference in ("lifa.example", "rule_liuyao_zixiu_dxj_4520", "custom_alias"):
        result = get_source(reference, db_path=database)
        assert result["kind"] == "rule_reference" and result["status"] == "available"
        assert result["targets"] == ["book.manual.a", "book.manual.b"]
        assert result["algorithm_boundary"] == "候选不等于结论"
        assert "text" not in result and "source_spans" not in result
    unresolved = get_source("xf_xia_c09", db_path=database)
    assert unresolved["status"] == "unavailable" and unresolved["reason"] == "unresolved_reference"
    direct = get_source("book.manual.a", db_path=database)
    assert direct["text"] == text and direct["review"]["status"] == "approved"
    assert direct["required_contexts"][0]["text"] == "共同前提仍须读取。"
    page = get_source("book.manual.a", max_chars=1000, db_path=database)
    assert page["has_more"] and page["next_offset"] == 1000
    rest = get_source("book.manual.a", offset=1000, text_version="original", db_path=database)
    assert page["text"] + rest["text"] == text
    with sqlite3.connect(database) as db:
        db.execute("DELETE FROM chunks WHERE id='book.manual.b'")
    incomplete = get_source("rule_liuyao_zixiu_dxj_4520", db_path=database)
    assert incomplete["status"] == "unavailable" and incomplete["targets"] == []
    assert incomplete["target_checks"][1]["reason"] == "rule_target_missing"
    assert "text" not in incomplete


def test_get_source_never_falls_back_for_legacy_mechanical_aliases(tmp_path):
    from liuyao_mcp.retrieval import get_source

    database, text = _readable_database(tmp_path)
    aliases = {alias for entry in load_mapping().values() for alias in entry["legacy_ids"]}
    for db_path in (tmp_path / "absent.sqlite", database):
        for alias in aliases:
            result = get_source(alias, db_path=db_path)
            assert result["status"] == "unavailable" and "text" not in result
    # A missing registry must not intercept ordinary evidence or other xf_ nodes.
    assert get_source("book.manual.a", db_path=database)["text"] == text
    assert get_source("xf_xia_c06_u03", db_path=database)["outline_node"]["title"] == "普通目录"
    with sqlite3.connect(database) as db:
        store_mapping(db, tmp_path)  # Empty registry: still no old-chunk fallback.
    for alias in aliases:
        result = get_source(alias, db_path=database)
        assert result["reason"] == "unknown_reference" and "text" not in result
    assert get_source("lifa.unregistered", db_path=database)["status"] == "unavailable"


def test_build_chart_exposes_reference_status_without_requiring_a_database(tmp_path, monkeypatch):
    from liuyao_mcp.server import build_chart

    database, _ = _readable_database(tmp_path)
    _mapping(tmp_path, {"xiangfa.combination.01": _entry(["book.manual.a"], legacy_ids=["xf_shang_c02_u01"])})
    with sqlite3.connect(database) as db:
        store_mapping(db, tmp_path)
    monkeypatch.setenv("LIUYAO_DB", str(database))
    chart = build_chart([2] * 6, month_branch="卯", day_ganzhi="庚子")
    patterns = chart["patterns"]
    references = set(patterns["source_rule_ids"]) | {item["source_rule_id"] for item in patterns["combination_checks"]}
    assert set(patterns["resolved_references"]) == references
    assert patterns["resolved_references"]["xf_shang_c02_u01"]["status"] == "available"
    assert patterns["resolved_references"]["xf_shang_c03"]["status"] == "unavailable"
    assert all(fact["source_rule_id"] in patterns["resolved_references"] for fact in patterns["facts"])
    monkeypatch.setenv("LIUYAO_DB", str(tmp_path / "absent.sqlite"))
    offline = build_chart([2] * 6, month_branch="卯", day_ganzhi="庚子")
    assert offline["primary"] == chart["primary"] and offline["display"]["markdown"]
    assert all(ref["status"] == "unavailable" and ref["reason"] == "database_unavailable"
               for ref in offline["patterns"]["resolved_references"].values())
