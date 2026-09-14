import hashlib
import json

import pytest

from liuyao_mcp.canonical import load_document, resolve_span, resolve_spans


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def write_pages(root, records):
    path = root / "data/canonical/book.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records), encoding="utf-8")


def pdf_source(root):
    pdf = root / "original.pdf"
    pdf.write_bytes(b"%PDF-original-fixture")
    source = {"source_id": "book", "source_type": "ocr_text", "pdf_pages": 2,
              "path": "unavailable-old-ocr.md", "sha256": "0" * 64,
              "original_pdf_path": str(pdf), "original_pdf_sha256": sha(pdf.read_bytes())}
    records = [{"page": page, "text": text, "text_sha256": sha(text.encode("utf-8")),
                "provenance": {"method": "manual_transcription", "review_status": "reviewed",
                               "original_pdf_sha256": source["original_pdf_sha256"]}}
               for page, text in [(1, "  预测必成。反馈：未成。复盘：旬空。  \n\n页末  "), (2, " 续页\n末行\n")]]
    write_pages(root, records)
    return source, records


def write_review(root, source, text="雷地豫", page=1, **extra):
    proof = {"source_id": source["source_id"], "pdf_page": page,
             "pdf_sha256": source["original_pdf_sha256"], "original_sha256": source["sha256"],
             "status": "visually_checked", "method": "word_by_word_against_pdf", "text": text,
             "unclear": [{"line": 2, "candidates": ["甲", "乙"]}], "notes": ["保留未明文字"],
             "provenance": {"reviewer": "test reviewer"}, **extra}
    path = root / "data/proofread_pages" / source["source_id"] / f"{page:04d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(proof, ensure_ascii=False), encoding="utf-8")
    return path, proof


def test_native_crcrlf_preserves_line_coordinates_and_whitespace(tmp_path):
    blob = " 甲\r\r\n乙 \r\n丙\r丁\n\n".encode("utf-8")
    (tmp_path / "native.md").write_bytes(blob)
    source = {"source_id": "native", "source_type": "native_text", "path": "native.md", "sha256": sha(blob)}
    document = load_document(tmp_path, source)
    assert document.lines == [" 甲", "", "乙 ", "丙", "丁", ""]
    assert document.body == "\n".join(blob.decode("utf-8").splitlines())
    assert document.source_sha256 == sha(blob)
    assert document.canonical_text_sha256 == sha(document.body.encode("utf-8")) != document.source_sha256
    assert resolve_span(document, {"page": None, "start_line": 1, "end_line": 3})["exact_text"] == " 甲\n\n乙 "
    assert resolve_span(document, {"page": None, "start_line": 6, "end_line": 6})["exact_text"] == ""
    source["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="native source SHA-256 mismatch"):
        load_document(tmp_path, source)


def test_current_review_replaces_base_in_the_only_body_and_spans(tmp_path):
    source, records = pdf_source(tmp_path)
    records[0].update(text="雷地阶", text_sha256=sha("雷地阶".encode("utf-8")))
    records[0]["provenance"]["review_status"] = "machine_extracted"
    write_pages(tmp_path, records)
    before = load_document(tmp_path, source)
    path, proof = write_review(tmp_path, source, "雷地豫\n")
    after = load_document(tmp_path, source)
    span = {"page": 1, "start_line": 1, "end_line": 1}
    assert resolve_span(before, span)["exact_text"] == "雷地阶"
    assert resolve_span(after, span)["exact_text"] == "雷地豫"
    assert "雷地豫\n" in after.body and "雷地阶" not in after.body
    assert after.canonical_text_sha256 != before.canonical_text_sha256
    assert after.pages[2].line_offset == before.pages[2].line_offset + 1
    provenance = after.pages[1].provenance
    assert provenance["review_status"] == "visually_reviewed"
    assert provenance["proofread_record_sha256"] == sha(path.read_bytes())
    assert provenance["proofread_metadata"] == {key: value for key, value in proof.items() if key != "text"}
    assert provenance["base_text_sha256"] == records[0]["text_sha256"]
    assert provenance["base_provenance"] == records[0]["provenance"]
    assert load_document(tmp_path, source).pages[1].provenance == provenance


def test_review_supplies_a_missing_canonical_page_before_completeness_check(tmp_path):
    source, records = pdf_source(tmp_path)
    records[0]["provenance"]["review_status"] = "machine_extracted"
    write_pages(tmp_path, records[:1])
    write_review(tmp_path, source, page=2, status="visually_reviewed")
    document = load_document(tmp_path, source)
    assert document.missing_pages == []
    assert document.pages[1].provenance["review_status"] == "machine_extracted"
    assert document.pages[2].provenance["review_status"] == "visually_reviewed"
    assert document.pages[2].provenance["base_text_sha256"] is None
    assert document.pages[2].provenance["base_provenance"] is None


@pytest.mark.parametrize("update, message", [
    ({"pdf_sha256": "0" * 64}, "source/PDF SHA-256 mismatch"),
    ({"source_id": "another-book"}, "source/PDF SHA-256 mismatch"),
    ({"pdf_page": True}, "invalid or duplicate proofread page"),
    ({"pdf_page": 3}, "invalid or duplicate proofread page"),
    ({"status": "machine_extracted"}, "unreviewed record"),
    ({"text": None}, "text must be a string"),
])
def test_review_rejects_wrong_source_page_hash_state_and_text(tmp_path, update, message):
    source, _ = pdf_source(tmp_path)
    path, proof = write_review(tmp_path, source)
    path.write_text(json.dumps({**proof, **update}), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_document(tmp_path, source)


def test_changed_review_invalidates_a_manual_quote_hash(tmp_path):
    from liuyao_mcp.manual_ingest import build_database

    source, _ = pdf_source(tmp_path)
    source.update(title="测试书", method_hint="lifa")
    (tmp_path / "data/canonical/sources.jsonl").write_text(json.dumps(source), encoding="utf-8")
    write_review(tmp_path, source)
    before = load_document(tmp_path, source)
    manifest = {"schema_version": "manual-slices-1", "source_id": "book",
                "source_sha256": source["original_pdf_sha256"], "units": [
                    {"unit_id": "rule", "kind": "rule", "title": "卦名", "method": "lifa",
                     "review": {"status": "approved", "basis": "direct_source_read", "reviewer": "test"},
                     "spans": [{"page": 1, "start_line": 1, "end_line": 1,
                                "quote_sha256": sha("雷地豫".encode("utf-8"))}]}]}
    path = tmp_path / "data/manual_slices/book.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    build_database(tmp_path, allow_partial=True)
    write_review(tmp_path, source, "雷水解")
    after = load_document(tmp_path, source)
    assert after.canonical_text_sha256 != before.canonical_text_sha256
    with pytest.raises(ValueError, match="manual span quote_sha256 mismatch"):
        build_database(tmp_path, allow_partial=True)


def test_pdf_exact_fields_and_cross_page_global_spans(tmp_path):
    source, records = pdf_source(tmp_path)
    document = load_document(tmp_path, source)
    assert document.source_sha256 == source["original_pdf_sha256"]
    assert document.source["raw_ocr_sha256"] == source["sha256"]
    assert document.missing_pages == []
    assert document.pages[1].line_offset == 1
    assert document.pages[2].line_offset == 5
    assert document.lines[4] == "========== PDF 第 2 页 / 共 2 页 =========="
    assert "\n".join(document.pages[2].lines) == records[1]["text"]
    row = document.pages[1].lines[0]
    feedback_start, analysis_start = row.index("反馈"), row.index("复盘")
    for start, end, expected in [(0, feedback_start, "  预测必成。"),
                                 (feedback_start, analysis_start, "反馈：未成。"),
                                 (analysis_start, len(row), "复盘：旬空。  ")]:
        result = resolve_span(document, {"page": 1, "start_line": 1, "end_line": 1,
                                         "start_column": start, "end_column": end})
        assert result["exact_text"] == expected
        assert result["source_spans"] == [{"start_line": 2, "end_line": 2, "start_column": start, "end_column": end}]
        assert result["canonical_spans"][0]["page"] == 1
    result = resolve_spans(document, [{"page": 1, "start_line": 3, "end_line": 3, "start_column": 1},
                                      {"page": 2, "start_line": 1, "end_line": 2, "end_column": 1}])
    assert result["exact_text"] == "末  \n 续页\n末"
    assert result["source_spans"] == [{"start_line": 4, "end_line": 4, "start_column": 1, "end_column": 4},
                                       {"start_line": 6, "end_line": 7, "start_column": 0, "end_column": 1}]
    assert [span["page"] for span in result["canonical_spans"]] == [1, 2]


def test_pdf_missing_pages_fail_strict_and_partial_never_reads_old_ocr(tmp_path):
    source, records = pdf_source(tmp_path)
    write_pages(tmp_path, records[1:])
    with pytest.raises(ValueError, match="missing canonical pages: \\[1\\]"):
        load_document(tmp_path, source)
    document = load_document(tmp_path, source, allow_partial=True)
    assert document.missing_pages == [1]
    assert list(document.pages) == [2]
    assert document.pages[2].line_offset == 1
    (tmp_path / "data/canonical/book.jsonl").unlink()
    source.pop("original_pdf_path")
    with pytest.raises(ValueError, match="missing canonical pages"):
        load_document(tmp_path, source)
    document = load_document(tmp_path, source, allow_partial=True)
    assert document.body == "" and document.missing_pages == [1, 2]


@pytest.mark.parametrize("corruption, message", [
    ("text", "page text SHA-256 mismatch"),
    ("provenance_hash", "provenance original PDF SHA-256 mismatch"),
    ("pdf_bytes", "original PDF SHA-256 mismatch"),
    ("source_hash", "expected lowercase SHA-256"),
    ("provenance", "provenance requires"),
    ("page", "page outside"),
    ("duplicate", "duplicate page"),
])
def test_pdf_rejects_invalid_records_and_hashes(tmp_path, corruption, message):
    source, records = pdf_source(tmp_path)
    if corruption == "text":
        records[0]["text"] += "修改"
    elif corruption == "provenance_hash":
        records[0]["provenance"]["original_pdf_sha256"] = "0" * 64
    elif corruption == "pdf_bytes":
        (tmp_path / "original.pdf").write_bytes(b"changed PDF bytes")
    elif corruption == "source_hash":
        source.pop("original_pdf_sha256")
    elif corruption == "provenance":
        records[0]["provenance"].pop("review_status")
    elif corruption == "page":
        records[0]["page"] = 3
    elif corruption == "duplicate":
        records.append(records[0])
    write_pages(tmp_path, records)
    with pytest.raises(ValueError, match=message):
        load_document(tmp_path, source)


@pytest.mark.parametrize("update", [
    {"page": None}, {"page": 0}, {"page": True},
    {"start_line": 0}, {"end_line": 4}, {"start_line": 2},
    {"start_column": -1}, {"end_column": 100}, {"start_column": 4, "end_column": 3},
])
def test_span_rejects_invalid_page_line_and_column(tmp_path, update):
    source, _ = pdf_source(tmp_path)
    document = load_document(tmp_path, source)
    with pytest.raises(ValueError):
        resolve_span(document, {"page": 1, "start_line": 1, "end_line": 1, **update})
