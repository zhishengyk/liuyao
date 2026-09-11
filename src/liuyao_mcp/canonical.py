"""One canonical body, with page-local and global coordinates for manual slices.

Native line numbers come directly from ``read_bytes().decode().splitlines()``.
PDF text comes from canonical page records with current reviewed pages applied,
never old OCR. The resulting body is shared by every ingestion consumer.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class CanonicalPage:
    lines: list[str]
    line_offset: int  # Add to a 1-based page-local line to get its global line.
    provenance: dict


@dataclass
class CanonicalDocument:
    source: dict
    source_sha256: str
    body: str
    canonical_text_sha256: str
    lines: list[str]
    pages: dict[int | None, CanonicalPage]
    missing_pages: list[int]


def _sha256(value, label):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{label}: expected lowercase SHA-256")
    return value


def _apply_reviewed_pages(root, source_id, source_sha, total, records):
    reviewed = set()
    for path in sorted((root / "data/proofread_pages" / source_id).glob("*.json")):
        blob = path.read_bytes()
        proof = json.loads(blob.decode("utf-8"))
        label = f"{source_id}: proofread record {path.name}"
        if not isinstance(proof, dict):
            raise ValueError(f"{label}: expected an object")
        if proof.get("source_id") != source_id or proof.get("pdf_sha256") != source_sha:
            raise ValueError(f"{label}: proofread source/PDF SHA-256 mismatch")
        page = proof.get("pdf_page")
        if type(page) is not int or not 1 <= page <= total or page in reviewed:
            raise ValueError(f"{label}: invalid or duplicate proofread page")
        if proof.get("status") not in ("visually_checked", "visually_reviewed"):
            raise ValueError(f"{label}: unreviewed record in proofread directory")
        text = proof.get("text")
        if not isinstance(text, str):
            raise ValueError(f"{label}: text must be a string")
        reviewed.add(page)
        base = records.get(page, {})
        provenance = {**base.get("provenance", {}),
                      "method": "reviewed_text_copy", "review_status": "visually_reviewed",
                      "original_pdf_sha256": source_sha, "source_page": page,
                      "proofread_record_path": str(path.resolve()),
                      "proofread_record_sha256": hashlib.sha256(blob).hexdigest(),
                      "proofread_metadata": {key: value for key, value in proof.items() if key != "text"},
                      "base_text_sha256": base.get("text_sha256"),
                      "base_provenance": base.get("provenance")}
        records[page] = {**base, "source_id": source_id, "page": page, "text": text,
                         "text_sha256": text_hash(text), "provenance": provenance}


def load_document(root, source, allow_partial=False):
    """Load native bytes or explicit ``data/canonical/<source_id>.jsonl`` pages.

    A PDF source requires ``original_pdf_sha256``. If ``original_pdf_path`` is
    supplied, verify the original PDF bytes too; the path may be absolute for
    local review. The historical OCR path and hash never supply canonical text.
    Page ``text_sha256`` hashes the exact UTF-8 text stored in the JSON record.
    Current reviewed files in ``data/proofread_pages/<source_id>`` override base
    pages before completeness checks and line coordinates are computed.
    """
    root = Path(root).resolve()
    source = dict(source)
    source_id = source["source_id"]
    pages, missing = {}, []
    if source["source_type"] == "native_text":
        path = (root / source["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"{source_id}: native source path leaves project root")
        blob = path.read_bytes()
        source_sha = hashlib.sha256(blob).hexdigest()
        if source_sha != source["sha256"]:
            raise ValueError(f"{source_id}: native source SHA-256 mismatch")
        # Reading bytes avoids universal-newline conversion of CRCRLF to CRLF.
        lines = blob.decode("utf-8").splitlines()
        pages[None] = CanonicalPage(lines, 0, {"method": "native_text"})
    else:
        total = source.get("pdf_pages")
        if type(total) is not int or total < 1:
            raise ValueError(f"{source_id}: pdf_pages must be a positive integer")
        source_sha = _sha256(source.get("original_pdf_sha256"), f"{source_id}: original_pdf_sha256")
        if source.get("original_pdf_path"):
            blob = (root / source["original_pdf_path"]).read_bytes()
            if hashlib.sha256(blob).hexdigest() != source_sha:
                raise ValueError(f"{source_id}: original PDF SHA-256 mismatch")
        if source.get("sha256"):
            source.setdefault("raw_ocr_sha256", source["sha256"])
        path = (root / "data/canonical" / f"{source_id}.jsonl").resolve()
        if not path.is_relative_to(root / "data/canonical"):
            raise ValueError(f"{source_id}: canonical page path leaves data/canonical")
        records = {}
        for number, row in enumerate(path.read_text(encoding="utf-8").splitlines() if path.is_file() else [], 1):
            if not row.strip():
                continue
            label = f"{source_id}: canonical record {number}"
            try:
                record = json.loads(row)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{label}: invalid JSON") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{label}: expected an object")
            if record.get("source_id", source_id) != source_id:
                raise ValueError(f"{label}: canonical source_id mismatch")
            page = record.get("page")
            if type(page) is not int or not 1 <= page <= total:
                raise ValueError(f"{label}: page outside 1..{total}")
            if page in records:
                raise ValueError(f"{label}: duplicate page {page}")
            text = record.get("text")
            if not isinstance(text, str):
                raise ValueError(f"{label}: text must be a string")
            if record.get("text_sha256") != text_hash(text):
                raise ValueError(f"{label}: page text SHA-256 mismatch")
            provenance = record.get("provenance")
            if not isinstance(provenance, dict) or any(not isinstance(provenance.get(key), str) or not provenance[key].strip()
                                                       for key in ("method", "review_status", "original_pdf_sha256")):
                raise ValueError(f"{label}: provenance requires method, review_status and original_pdf_sha256")
            if provenance["original_pdf_sha256"] != source_sha:
                raise ValueError(f"{label}: provenance original PDF SHA-256 mismatch")
            if "source_page" in provenance and (type(provenance["source_page"]) is not int or provenance["source_page"] != page):
                raise ValueError(f"{label}: provenance source_page mismatch")
            records[page] = record
        _apply_reviewed_pages(root, source_id, source_sha, total, records)
        missing = [page for page in range(1, total + 1) if page not in records]
        if missing and not allow_partial:
            raise ValueError(f"{source_id}: missing canonical pages: {missing}")
        lines = []
        for page, record in sorted(records.items()):
            lines.append(f"========== PDF 第 {page} 页 / 共 {total} 页 ==========")
            # Preserve the page record exactly, including trailing blank lines.
            page_lines = record["text"].split("\n")
            pages[page] = CanonicalPage(page_lines, len(lines), record["provenance"])
            lines.extend(page_lines)
    body = "\n".join(lines)
    return CanonicalDocument(source, source_sha, body, text_hash(body), lines, pages, missing)


def resolve_span(document, span):
    """Resolve inclusive 1-based lines and optional Python character columns.

    The start column applies to the first line; the exclusive end column applies
    to the last. Omitted columns include each full boundary line. No whitespace
    is stripped. PDF spans never include generated page anchors.
    """
    if "page" not in span:
        raise ValueError("canonical span requires page (null for native text)")
    page = span["page"]
    if page is not None and type(page) is not int:
        raise ValueError("canonical span page must be an integer or null")
    if page not in document.pages:
        raise ValueError(f"{document.source['source_id']}: canonical page {page} is unavailable")
    part = document.pages[page]
    start, end = span.get("start_line"), span.get("end_line")
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(part.lines):
        raise ValueError(f"canonical page {page}: span lines outside 1..{len(part.lines)} or reversed")
    start_column = span.get("start_column", 0)
    end_column = span.get("end_column", len(part.lines[end - 1]))
    if (type(start_column) is not int or type(end_column) is not int
            or not 0 <= start_column <= len(part.lines[start - 1])
            or not 0 <= end_column <= len(part.lines[end - 1])
            or (start == end and start_column > end_column)):
        raise ValueError(f"canonical page {page}: span columns out of bounds or reversed")
    selected = part.lines[start - 1:end]
    if start == end:
        selected[0] = selected[0][start_column:end_column]
    else:
        selected[0] = selected[0][start_column:]
        selected[-1] = selected[-1][:end_column]
    columns = {"start_column": start_column, "end_column": end_column}
    return {"exact_text": "\n".join(selected),
            "source_spans": [{"start_line": start + part.line_offset, "end_line": end + part.line_offset, **columns}],
            "canonical_spans": [{"page": page, "start_line": start, "end_line": end, **columns}]}


def resolve_spans(document, spans):
    """Resolve ordered spans, including cross-page slices, joined by one LF."""
    resolved = [resolve_span(document, span) for span in spans]
    return {"exact_text": "\n".join(item["exact_text"] for item in resolved),
            "source_spans": [span for item in resolved for span in item["source_spans"]],
            "canonical_spans": [span for item in resolved for span in item["canonical_spans"]]}
