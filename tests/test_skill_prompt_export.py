"""Production prompts contain routing and evidence IDs, never book/case answers."""
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest


def exporter():
    path = Path(__file__).resolve().parents[1] / "scripts/build_skill_prompts.py"
    spec = importlib.util.spec_from_file_location("skill_prompt_export", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(tmp_path):
    database = tmp_path / "knowledge.sqlite"
    with sqlite3.connect(database) as db:
        db.executescript("CREATE TABLE sources(id TEXT,metadata TEXT,body TEXT);"
                         "CREATE TABLE chunks(id TEXT,payload TEXT);"
                         "CREATE TABLE ocr_pages(source_id TEXT,pdf_page INT,payload TEXT);")
        db.execute("INSERT INTO sources VALUES(?,?,?)", ("book_a", json.dumps({"title": "甲书"}),
                   "通用规则\n案例判断\n反馈：没有成功\n卒于次年"))
        db.execute("INSERT INTO chunks VALUES(?,?)", ("rule_a", json.dumps({
            "source_id": "book_a", "source_spans": [{"start_line": 1, "end_line": 4}],
            "classification": {"roots": ["study"]}})))
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({
        "domains": {"study": {"title": "学习", "questions": ["考试"], "flow": "先按考试事项取用。"}},
        "workflow": [{"step": 1, "title": "锁定问题", "route": "没有问题先询问。", "evidence_ids": ["rule_a"]}],
        "selection_policy": "prediction-only",
    }), encoding="utf-8")
    return database, plan


def test_builds_prediction_only_prompts_and_regenerates(tmp_path):
    database, plan = fixture(tmp_path)
    output = tmp_path / "prompts"
    before = database.read_bytes()
    result = exporter().build(database, output, plan)
    global_prompt = (output / "GLOBAL.md").read_text(encoding="utf-8")
    domain_prompt = (output / "study/PROMPT.md").read_text(encoding="utf-8")
    assert "没有问题先询问" in global_prompt and "`rule_a`" in global_prompt
    assert "先按考试事项取用" in domain_prompt
    leaked = ("案例判断", "反馈：没有成功", "卒于次年")
    assert all(text not in global_prompt + domain_prompt for text in leaked)
    assert set(result["files_sha256"]) == {"GLOBAL.md", "study/PROMPT.md"}
    assert result["sections"] == [] and result["evidence_by_bucket"]["global"] == ["rule_a"]
    hashes = dict(result["files_sha256"])
    assert exporter().build(database, output, plan)["files_sha256"] == hashes
    assert database.read_bytes() == before


def test_missing_workflow_evidence_stops_without_changing_existing_prompt(tmp_path):
    database, plan = fixture(tmp_path)
    output = tmp_path / "prompts"
    exporter().build(database, output, plan)
    before = (output / "GLOBAL.md").read_bytes()
    config = json.loads(plan.read_text(encoding="utf-8"))
    config["workflow"][0]["evidence_ids"] = ["missing"]
    plan.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="missing evidence"):
        exporter().build(database, output, plan)
    assert (output / "GLOBAL.md").read_bytes() == before


def test_public_source_reader_paginates_and_rejects_stale_files(tmp_path):
    from liuyao_mcp.retrieval import get_source

    database, plan = fixture(tmp_path)
    output = tmp_path / "source-prompts"
    exporter().build(database, output, plan)
    original = (output / "GLOBAL.md").read_text(encoding="utf-8")
    parts, offset = [], 0
    while True:
        result = get_source("prompt:GLOBAL.md", offset=offset, max_chars=1000, db_path=database)
        parts.append(result["text"])
        if not result["has_more"]:
            break
        offset = result["next_offset"]
    assert "".join(parts) == original
    assert result["source_sections"] == []
    for bad in ("prompt:../secret.md", "prompt:/GLOBAL.md", "prompt:unknown.md"):
        with pytest.raises(ValueError):
            get_source(bad, db_path=database)
    page = output / "GLOBAL.md"
    page.write_text(original + "unexpected edit", encoding="utf-8")
    with pytest.raises(ValueError, match="文件校验失败"):
        get_source("prompt:GLOBAL.md", db_path=database)
