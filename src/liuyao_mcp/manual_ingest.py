"""Build a fresh corpus from approved, explicitly located manual slices."""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import sqlite3
import tempfile

from .canonical import load_document, resolve_span, resolve_spans
from .chart import build_chart
from .common import case_search_text, digest, dumps, project_root, tokens
from .ingest import SCHEMA, SEARCH_INDEX_VERSION, store_search_metadata
from .outline import store_outline
from .rule_references import load_mapping, store_mapping
from .taxonomy import nodes as topic_nodes

VERSION = "manual-corpus-1"
PARTS = ("question", "background", "chart", "author_analysis", "feedback", "post_feedback_analysis")


def _portable(value):
    """Remove machine-local locations from metadata used for content identity."""
    if isinstance(value, dict):
        return {key: _portable(item) for key, item in value.items()
                if not (isinstance(item, str) and (PurePosixPath(item).is_absolute() or PureWindowsPath(item).is_absolute())
                        and ("path" in key or key in ("cache_page", "cwd", "root", "directory")))}
    if isinstance(value, list):
        return [_portable(item) for item in value]
    return value


class IncompleteCorpusError(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__("Manual corpus is incomplete; inspect .report or use explicit --allow-partial for development")


def _resolved(document, spans):
    if not isinstance(spans, list):
        raise ValueError("spans must be a list")
    for span in spans:
        quote = resolve_span(document, span)["exact_text"]
        if "exact_text" in span and quote != span["exact_text"]:
            raise ValueError("manual span exact_text mismatch")
        if "quote_sha256" in span and digest(quote) != span["quote_sha256"]:
            raise ValueError("manual span quote_sha256 mismatch")
    result = resolve_spans(document, spans)
    coordinates = {"page", "start_line", "end_line", "start_column", "end_column", "exact_text", "quote_sha256"}
    for index, span in enumerate(spans):
        annotations = {key: value for key, value in span.items() if key not in coordinates}
        result["source_spans"][index].update(annotations)
        result["canonical_spans"][index].update(annotations)
    if any("author" in span for span in spans):
        result["span_authors"] = [span.get("author") for span in spans]
    if any("cast_index" in span for span in spans):
        result["span_cast_indices"] = [span.get("cast_index") for span in spans]
    return result


def _reviewed(item):
    review = item.get("review", {})
    if review.get("status") != "approved":
        return False
    if any(not isinstance(review.get(key), str) or not review[key].strip()
           for key in ("basis", "reviewer")):
        raise ValueError("approved review requires basis and reviewer")
    return True


def _validate_quality(quality):
    if not isinstance(quality, dict) or quality.get("status") not in ("eligible", "noise", "pending"):
        raise ValueError("case quality requires eligible/noise/pending status")
    if any(not isinstance(quality.get(key), str) or not quality[key].strip() for key in ("reason", "reviewer")):
        raise ValueError("declared case quality requires reason and reviewer")
    return dict(quality)


def _quality_reviews(root, document):
    path = root / "data/manual_slices/quality_reviews" / f"{document.source['source_id']}.json"
    if not path.is_file():
        return {}, None
    review = json.loads(path.read_text(encoding="utf-8"))
    if (review.get("schema_version") != "case-quality-1"
            or review.get("source_id") != document.source["source_id"]
            or review.get("source_sha256") != document.source_sha256):
        raise ValueError("case quality sidecar schema/source/SHA-256 mismatch")
    entries = review.get("reviews")
    if not isinstance(entries, list):
        raise ValueError("case quality sidecar reviews must be a list")
    by_id = {}
    for entry in entries:
        _validate_quality(entry)
        unit_id = entry.get("unit_id")
        if not isinstance(unit_id, str) or not unit_id.strip() or unit_id in by_id:
            raise ValueError("case quality sidecar requires unique unit IDs")
        if not isinstance(entry.get("unit_text_sha256"), str):
            raise ValueError("case quality sidecar requires unit_text_sha256")
        by_id[unit_id] = entry
    return by_id, digest(dumps(_portable(review)))


def _case_quality(document, unit, whole, reviews):
    text_sha = digest(whole["exact_text"])
    if "quality" in unit:
        quality = {**_validate_quality(unit["quality"]), "basis": "inline_manual_quality"}
    elif unit["unit_id"] in reviews:
        review = reviews[unit["unit_id"]]
        if review["unit_text_sha256"] == text_sha:
            quality = {**review, "basis": "quality_review_sidecar"}
        else:
            quality = {"status": "pending", "reason": "quality_review_stale_text: current unit text differs from reviewed text",
                       "reviewer": None, "basis": "expired_quality_review", "previous_review": review}
    else:
        quality = {"status": "pending", "reason": "quality_not_reviewed", "reviewer": None, "basis": "not_reviewed"}
    quality["unit_text_sha256"] = text_sha
    if quality["status"] == "eligible" and any(not _resolved(document, unit.get("parts", {}).get(role, []))["exact_text"].strip()
                                               for role in ("question", "feedback")):
        raise ValueError("eligible case quality requires explicit original question and actual feedback text")
    return quality


def _classification(unit, case=False):
    topics = unit.get("topic_ids", [])
    known = {node["id"] for node in topic_nodes()}
    if not isinstance(topics, list) or any(not isinstance(topic, str) or topic not in known for topic in topics):
        raise ValueError("manual topic_ids must be a list of known taxonomy IDs")
    topics = list(dict.fromkeys(topics))
    roots = list(dict.fromkeys(topic.split("/")[0] for topic in topics))
    scope = "case" if case else unit.get("scope", "unknown")
    if scope not in ("common", "topic", "subtopic", "scene", "example", "unknown", "case"):
        raise ValueError("manual scope is not a supported classification scope")
    declared = "scope" in unit or "topic_ids" in unit
    return {"status": "manually_reviewed" if topics or scope not in ("case", "unknown") else "unknown",
            "scope": scope, "basis": "manual_slice_review" if declared else "not_annotated",
            "topic": roots[0] if roots else None, "topic_ids": topics, "roots": roots, "evidence": []}


def _offsets(document):
    """Global character offsets, used only to validate containment/role overlap."""
    offsets, offset = [], 0
    for line in document.lines:
        offsets.append(offset)
        offset += len(line) + 1
    return offsets


def _intervals(offsets, spans):
    return [(offsets[s["start_line"] - 1] + s["start_column"],
             offsets[s["end_line"] - 1] + s["end_column"]) for s in spans]


def _merge(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _contains(offsets, whole, part):
    outer = _merge(_intervals(offsets, whole["source_spans"]))
    return all(any(a <= start and end <= b for a, b in outer)
               for start, end in _intervals(offsets, part["source_spans"]))


def _inside(offsets, part, whole):
    if not _contains(offsets, whole, part):
        raise ValueError("case part or cast evidence falls outside the manual unit spans")


def _verified_cast(root, document, unit, cast, chart):
    verification = cast.get("verification", {})
    if verification.get("status") != "verified":
        return False
    if any(not isinstance(verification.get(key), str) or not verification[key].strip()
           for key in ("basis", "evidence", "evidence_sha256", "reviewer")):
        raise ValueError("verified cast requires basis, reviewer and hashed evidence")
    path = (root / verification["evidence"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("cast verification evidence path leaves project root")
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != verification["evidence_sha256"]:
        raise ValueError("cast verification evidence SHA-256 mismatch")
    evidence = json.loads(blob)
    records = [r for r in evidence["records"] if r["unit_id"] == unit["unit_id"]]
    expected = {"source_sha256": document.source_sha256, "chart_text_sha256": digest(chart["exact_text"]),
                "input_line_values": cast.get("line_values"), "month_branch": cast.get("month_branch"),
                "day_ganzhi": cast.get("day_ganzhi"), "status": "passed"}
    if len(records) != 1 or any(records[0].get(key) != value for key, value in expected.items()):
        raise ValueError("cast verification record does not match approved source, chart and inputs")
    return True


def _case(root, document, unit, whole, source):
    if set(unit.get("parts", {})) != set(PARTS):
        raise ValueError("case parts must explicitly include all six roles; use [] for absent roles")
    parts = {key: _resolved(document, unit["parts"][key]) for key in PARTS}
    offsets = _offsets(document)
    for part in parts.values():
        _inside(offsets, part, whole)
    for index, left in enumerate(PARTS):
        for right in PARTS[index + 1:]:
            if {left, right} == {"question", "background"}:
                continue
            if any(max(a, c) < min(b, d)
                   for a, b in _intervals(offsets, parts[left]["source_spans"])
                   for c, d in _intervals(offsets, parts[right]["source_spans"])):
                raise ValueError(f"case roles overlap: {left} / {right}")
    cast = dict(unit.get("cast") or {})
    fields = cast.pop("field_spans", {})
    cast_evidence = {key: _resolved(document, spans) for key, spans in fields.items()}
    if "source_spans" in cast:
        cast_evidence["cast"] = _resolved(document, cast.pop("source_spans"))
    for part in cast_evidence.values():
        _inside(offsets, part, whole)
    for field in ("line_values", "month_branch", "day_ganzhi", "year_ganzhi", "hour_ganzhi"):
        if cast.get(field) is not None and not (cast_evidence.get(field, {}).get("source_spans")
                                               or cast_evidence.get("cast", {}).get("source_spans")):
            raise ValueError(f"manual cast {field} requires explicit source evidence")
    values, month, day = (cast.get(key) for key in ("line_values", "month_branch", "day_ganzhi"))
    if values is not None and (not isinstance(values, list) or len(values) != 6
                              or any(type(v) is not int or v not in (0, 1, 2, 3) for v in values)):
        raise ValueError("manual line_values must be six bottom-to-top 0/1/2/3 integers")
    derived = build_chart(values, month_branch=month, day_ganzhi=day) if values is not None and month and day else None
    verified = _verified_cast(root, document, unit, cast, parts["chart"])
    validation = "calculated" if derived and verified else "not_run"
    issues = ["missing_" + key for key in ("line_values", "month_branch", "day_ganzhi") if cast.get(key) is None]
    if derived and not verified:
        issues.append("source_chart_not_independently_verified")
    question = parts["question"]["exact_text"]
    initial_background = _resolved(document, [span for span in unit["parts"]["background"]
                                              if span.get("eligible_for_initial_blind_input") is not False])
    withheld_background = _resolved(document, [span for span in unit["parts"]["background"]
                                               if span.get("eligible_for_initial_blind_input") is False])
    initial_spans = parts["question"]["source_spans"] + initial_background["source_spans"]
    if any(max(a, c) < min(b, d)
           for a, b in _intervals(offsets, withheld_background["source_spans"])
           for c, d in _intervals(offsets, initial_spans)):
        raise ValueError("late-disclosed background overlaps initial question or eligible background")
    background = initial_background["exact_text"]
    question_text = "\n".join(text for text in (question, background if background not in question else "") if text)
    if not question:
        issues.append("missing_question")
    classification = _classification(unit, case=True)
    author_yongshen = []
    for statement in unit.get("author_yongshen", []):
        if statement["relative"] not in ("父母", "兄弟", "子孙", "妻财", "官鬼"):
            raise ValueError("manual author_yongshen requires a six-relative name")
        evidence = _resolved(document, statement["spans"])
        if not evidence["exact_text"].strip():
            raise ValueError("manual author_yongshen requires an explicit author statement")
        _inside(offsets, evidence, parts["author_analysis"])
        author_yongshen.append({"relative": statement["relative"], **evidence,
                               "basis": "manual_author_statement"})
    reported_yongshen = list(dict.fromkeys(item["relative"] for item in author_yongshen)) or None
    features = dict(derived["features"]) if validation == "calculated" else {}
    features.update(topic=classification["topic"], chart_feature_status=validation,
                    yongshen_reported=reported_yongshen,
                    yongshen_basis="manual_author_statement" if author_yongshen else None)
    if validation == "calculated" and reported_yongshen:
        candidates = [("primary", line) for line in derived["lines"]]
        candidates += [("hidden", line["hidden"]) for line in derived["lines"] if line["hidden"]]
        candidates += [("changed", line["transformation"]) for line in derived["lines"] if line["transformation"]]
        features["yongshen_candidates"] = [
            {**{key: line[key] for key in ("position", "relative", "void", "month_break", "moving")},
             "scope": scope, "selection": "relative_match_not_author_line_selection"}
            for scope, line in candidates if line["relative"] in reported_yongshen]
    cast.update(line_values=values, month_branch=month, day_ganzhi=day,
                date=cast.get("date"), time=cast.get("time"), lines_order="bottom_to_top",
                line_values_basis="manual_transcription" if values is not None else None,
                calendar_basis="manual_transcription" if month or day else "unknown",
                evidence=cast_evidence)
    feedback = parts["feedback"]
    event_id = unit.get("event_id")
    if event_id is not None and (not isinstance(event_id, str) or not event_id.strip()):
        raise ValueError("manual event_id must be a nonempty string")
    interpretations = []
    for span in unit["parts"]["author_analysis"]:
        part = _resolved(document, [span])
        statements = [item for item in author_yongshen if _contains(offsets, part, item)]
        interpretations.append({"source_id": source["source_id"], "author": span.get("author"),
                                "method_hint": unit["method"],
                                "yongshen_reported": list(dict.fromkeys(item["relative"] for item in statements)) or None,
                                "yongshen_evidence": statements,
                                "cast_index": span.get("cast_index"),
                                "cast_attribution": "explicit" if span.get("cast_index") is not None else "unspecified",
                                "original_text": part["exact_text"], "source_spans": part["source_spans"],
                                "canonical_spans": part["canonical_spans"], "source_span_basis": "approved_manual_role"})
    return {"schema_version": VERSION, "case_id": unit["unit_id"], "title": unit["title"],
            "method": unit["method"], "review": unit["review"], "parts": parts,
            "related_case_ids": [], "duplicate_group": event_id or unit["unit_id"], "duplicate_candidates": [],
            "event_id": event_id, "duplicate_group_basis": "manual_event_id" if event_id else "single_manual_unit",
            "classification": classification,
            "question": {"raw": question_text, "question_only": question, "background": background,
                         "known_background": background,
                         "topic": classification["topic"],
                         "source_spans": parts["question"]["source_spans"],
                         "background_spans": initial_background["source_spans"]},
            "cast": cast, "derived": derived, "features": features, "author_yongshen": author_yongshen,
            "reported_chart": {"raw_header": parts["chart"]["exact_text"],
                               "primary": None, "changed": None, "void_raw": None,
                               "line_text": parts["chart"]["exact_text"].splitlines()},
            "interpretations": interpretations,
            "outcome": {"status": "reported_explicit" if feedback["exact_text"] else "none",
                        "quotes": [feedback["exact_text"]] if feedback["exact_text"] else [],
                        "source_spans": feedback["source_spans"], "canonical_spans": feedback["canonical_spans"],
                        "event_date": None, "event_timing": "unknown", "independently_verified": False},
            "post_feedback_analysis": parts["post_feedback_analysis"],
            "source": {"source_id": source["source_id"], "path": source["path"], "sha256": source["sha256"],
                       "source_sha256": document.source_sha256, "spans": whole["source_spans"],
                       "canonical_spans": whole["canonical_spans"], "original_text": whole["exact_text"],
                       "pdf_pages": sorted({s["page"] for s in whole["canonical_spans"] if s["page"] is not None}),
                       "raw_text_normalization": "canonical_lf"},
            "extraction": {"method": "approved_manual_slices", "pipeline_version": VERSION,
                           "status": "partial" if issues else "manually_reviewed", "issues": issues,
                           "chart_validation": validation,
                           "computed": derived is not None,
                           "chart_validation_basis": cast["verification"]["basis"] if verified else "source_verification_not_run",
                           "source_chart_independently_verified": verified}}


def _case_records(root, document, unit, whole, source):
    additional = unit.get("additional_casts", [])
    if not isinstance(additional, list) or any(not isinstance(cast, dict) for cast in additional):
        raise ValueError("additional_casts must be a list of manually located casts")
    casts = [unit.get("cast") or {}] + additional
    for statement in unit.get("author_yongshen", []):
        index = statement.get("cast_index")
        if (index is None and len(casts) > 1) or (index is not None and (type(index) is not int or not 0 <= index < len(casts))):
            raise ValueError("manual author_yongshen requires the applicable zero-based cast_index")
    if len(casts) > 1 and any("diagram_spans" not in cast or
                              (cast.get("line_values") is not None and not cast["diagram_spans"])
                              for cast in casts):
        raise ValueError("each cast in a multi-cast unit requires explicit diagram_spans")
    offsets = _offsets(document)
    for spans in unit.get("parts", {}).values():
        _inside(offsets, _resolved(document, spans), whole)
        for span in spans:
            index = span.get("cast_index")
            if index is not None and (type(index) is not int or not 0 <= index < len(casts)):
                raise ValueError("manual cast_index must be a zero-based index into this unit's casts")
    ids = [unit["unit_id"] if index == 0 else f"{unit['unit_id']}.cast{index + 1}" for index in range(len(casts))]
    records = []
    for index, cast in enumerate(casts):
        parts = dict(unit.get("parts", {}))
        if cast.get("diagram_spans") is not None:
            parts["chart"] = cast["diagram_spans"]
        for role in ("author_analysis", "post_feedback_analysis"):
            if role in parts:
                parts[role] = [span for span in parts[role] if span.get("cast_index") in (None, index)]
        statements = [item for item in unit.get("author_yongshen", []) if item.get("cast_index") in (None, index)]
        try:
            record = _case(root, document, {**unit, "unit_id": ids[index], "cast": cast, "parts": parts,
                                          "author_yongshen": statements}, whole, source)
        except ValueError as exc:
            raise ValueError(f"{ids[index]}: {exc}") from exc
        record.update(unit_id=unit["unit_id"], cast_index=index, additional_casts=additional,
                      related_case_ids=[eid for eid in ids if eid != ids[index]])
        if len(casts) > 1:
            record.update(event_id=unit.get("event_id") or unit["unit_id"],
                          duplicate_group=unit.get("event_id") or unit["unit_id"],
                          duplicate_group_basis="manual_event_id" if unit.get("event_id") else "same_manual_unit")
        records.append(record)
    sequence = [{"case_id": record["case_id"], "cast_index": index,
                 "relationship": casts[index].get("relationship", "unspecified"),
                 "chart_validation": record["extraction"]["chart_validation"]}
                for index, record in enumerate(records)]
    for record in records:
        record["cast_sequence"] = sequence
    return records


def _coverage(document, spans):
    intervals = defaultdict(list)
    for span in spans:
        for line in range(span["start_line"], span["end_line"] + 1):
            intervals[line].append((span["start_column"] if line == span["start_line"] else 0,
                                    span["end_column"] if line == span["end_line"] else len(document.lines[line - 1])))
    total = covered = 0
    uncovered = []
    for page, part in document.pages.items():
        for local_line, line in enumerate(part.lines, 1):
            global_line = local_line + part.line_offset
            merged = _merge(intervals[global_line])
            total += sum(not char.isspace() for char in line)
            covered += sum(not char.isspace() for a, b in merged for char in line[a:b])
            cursor = 0
            for start, end in merged + [(len(line), len(line))]:
                if line[cursor:start].strip():
                    uncovered.append({"page": page, "start_line": local_line, "end_line": local_line,
                                      "start_column": cursor, "end_column": start})
                cursor = max(cursor, end)
    return {"total_nonwhitespace_chars": total, "covered_nonwhitespace_chars": covered,
            "coverage_ratio": covered / total if total else 1.0, "uncovered_spans": uncovered}


def _manual_outline(source, chunks, cases):
    records = chunks + cases
    if not records:
        return []
    book_id = "manual_book:" + source["source_id"]
    book_path = [{"node_id": book_id, "title": source["title"]}]
    nodes = [{"node_id": book_id, "source_id": source["source_id"], "parent_id": None,
              "position": 0, "depth": 0, "node_type": "book", "title": source["title"],
              "title_basis": "source_manifest", "start_line": 1, "end_line": source["canonical_line_count"],
              "path": book_path, "intro_span": None, "scene_hints": []}]
    navigations = {}
    for record in records:
        case = "case_id" in record
        eid = record["case_id"] if case else record["id"]
        unit_id = record.get("unit_id", eid)
        if unit_id in navigations:
            record["outline"] = navigations[unit_id]
            continue
        spans = record["source"]["spans"] if case else record["source_spans"]
        canonical = record["source"]["canonical_spans"] if case else record["canonical_spans"]
        title = record["title"] if case else record["chapter"]
        node_id = "manual_unit:" + unit_id
        path = book_path + [{"node_id": node_id, "title": title}]
        nodes.append({"node_id": node_id, "source_id": source["source_id"], "parent_id": book_id,
                      "position": len(nodes), "depth": 1, "node_type": "manual_unit", "title": title,
                      "title_basis": "manual_unit_label", "start_line": min(s["start_line"] for s in spans),
                      "end_line": max(s["end_line"] for s in spans), "source_spans": spans,
                      "canonical_spans": canonical, "path": path, "intro_span": None, "scene_hints": []})
        record["outline"] = {"node_id": node_id, "path": path, "intro_refs": [], "scene_hints": [],
                             "title_basis": "manual_unit_label"}
        navigations[unit_id] = record["outline"]
    return nodes


def _page_records(document):
    for number, page in document.pages.items():
        if number is None:
            continue
        text = "\n".join(page.lines)
        provenance = page.provenance
        proof = provenance.get("proofread_metadata", {})
        visual = provenance.get("review_status") in ("visually_checked", "visually_reviewed")
        record = {"source_id": document.source["source_id"], "pdf_page": number,
                  "text_schema": "canonical-1", "canonical_text": text, "selected_text_sha256": digest(text),
                  "status": "visually_checked" if visual else "canonical_machine", "visual_reviewed": visual,
                  "pdf_sha256": document.source_sha256,
                  "original_sha256": proof.get("original_sha256", document.source.get("raw_ocr_sha256", document.source_sha256)),
                  "normalization": proof.get("normalization", "canonical_LF_with_explicit_columns"),
                  "review_method": proof.get("method", provenance.get("method")), "review_date": proof.get("review_date"),
                  "unclear": proof.get("unclear", []), "printed_page": proof.get("printed_page"),
                  "excluded_regions": proof.get("excluded_regions", []), "notes": proof.get("notes", []),
                  "provenance": provenance, "canonical_start_line": page.line_offset + 1,
                  "canonical_end_line": page.line_offset + len(page.lines)}
        if visual:
            record["reviewed_text"] = text
        yield record


def _parse(root, source):
    # Always load available canonical pages to produce a complete coverage report.
    document = load_document(root, source, allow_partial=True)
    source = {**document.source, "source_sha256": document.source_sha256,
              "original_sha256": document.source_sha256, "sha256": document.canonical_text_sha256,
              "canonical_text_sha256": document.canonical_text_sha256,
              "text_schema": "canonical-1", "canonical_line_count": len(document.lines),
              "text_status": "canonical_text", "original_mapping_status": "native_line_aligned"
              if source["source_type"] == "native_text" else "unavailable_old_ocr_lines"}
    path = root / "data/manual_slices" / f"{source['source_id']}.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    if manifest is not None and (manifest.get("schema_version") != "manual-slices-1"
                     or manifest.get("source_id") != source["source_id"]
                     or manifest.get("source_sha256") != document.source_sha256):
        raise ValueError(f"{source['source_id']}: manual manifest schema/source/hash mismatch")
    quality_reviews, quality_reviews_sha = _quality_reviews(root, document)
    chunks, cases, coverage_spans, unapproved, excluded = [], [], [], [], []
    for unit in (manifest or {}).get("units", []):
        if not _reviewed(unit):
            unapproved.append({"unit_id": unit.get("unit_id"), "review": unit.get("review"), "spans": unit.get("spans", [])})
            continue
        unit = {"method": "unknown", **unit}
        if unit.get("kind") not in ("rule", "case") or unit["method"] not in ("lifa", "xiangfa", "mixed", "unknown"):
            raise ValueError("approved manual unit requires rule/case kind and lifa/xiangfa/mixed/unknown method")
        if any(not isinstance(unit.get(key), str) or not unit[key].strip() for key in ("unit_id", "title")):
            raise ValueError("approved manual unit requires unit_id and title")
        whole = _resolved(document, unit.get("spans"))
        if not whole["exact_text"].strip():
            raise ValueError("approved manual unit requires nonempty exact source text")
        coverage_spans.extend(whole["source_spans"])
        if unit["kind"] == "case":
            quality = _case_quality(document, unit, whole, quality_reviews)
            records = _case_records(root, document, unit, whole, source)
            for record in records:
                record["quality"] = quality
            cases.extend(records)
            continue
        spans = whole["source_spans"]
        contexts = []
        for context_span in unit.get("context_spans", []):
            context = _resolved(document, [context_span])
            contexts.append({**context_span, **context, "text": context["exact_text"]})
        chunks.append({"id": unit["unit_id"], "source_id": source["source_id"], "kind": "passage",
                       "chapter": unit["title"], "chapter_start": spans[0]["start_line"],
                       "start_line": min(s["start_line"] for s in spans), "end_line": max(s["end_line"] for s in spans),
                       "source_spans": spans, "canonical_spans": whole["canonical_spans"],
                       "pages": sorted({s["page"] for s in whole["canonical_spans"] if s["page"] is not None}),
                       "text": whole["exact_text"], "required_contexts": contexts,
                       "method": unit["method"], "review": unit["review"],
                       "content_hash": digest(dumps([whole["exact_text"], *[c["text"] for c in contexts]])) if contexts else digest(whole["exact_text"]),
                       "content_role": "theory", "related_case_ids": [],
                       "classification": _classification(unit),
                       "extraction": {"method": "approved_manual_slices", "pipeline_version": VERSION}})
    for index, item in enumerate((manifest or {}).get("exclusions", [])):
        if not _reviewed(item):
            unapproved.append({"exclusion_index": index, **item})
            continue
        if not item.get("reason"):
            raise ValueError("manual exclusion requires an explicit reason")
        whole = _resolved(document, item.get("spans"))
        coverage_spans.extend(whole["source_spans"])
        excluded.append({"reason": item["reason"], "review": item["review"], **whole})
    case_units = len({case["unit_id"] for case in cases})
    offsets = _offsets(document)
    feedback_intervals = _intervals(offsets, [span for case in cases for span in case["parts"]["feedback"]["source_spans"]])
    for chunk in chunks:
        for context in chunk["required_contexts"]:
            if any(max(a, c) < min(b, d) for a, b in feedback_intervals
                   for c, d in _intervals(offsets, context["source_spans"])):
                raise ValueError("shared rule context overlaps case feedback")
    report = {"source_id": source["source_id"], "source_sha256": document.source_sha256,
              "canonical_text_sha256": document.canonical_text_sha256, "total_lines": len(document.lines),
              "manifest_missing": manifest is None, "manifest_sha256": digest(dumps(_portable(manifest))) if manifest else None,
              "chunks": len(chunks), "cases": len(cases), "case_units": case_units,
              "approved_units": len(chunks) + case_units,
              "unapproved_units": unapproved, "unapproved_count": len(unapproved), "excluded_ranges": excluded,
              "missing_pages": document.missing_pages, "page_review_status": dict(Counter(
                  page.provenance.get("review_status", "native_text") for page in document.pages.values())),
              "chart_validation": dict(Counter(case["extraction"]["chart_validation"] for case in cases)),
              "case_quality": dict(Counter(case["quality"]["status"] for case in cases)),
              "quality_reviews_sha256": quality_reviews_sha,
              "page_provenance_sha256": digest(dumps(_portable([
                  {"page": number, "text_sha256": digest("\n".join(page.lines)), "provenance": page.provenance}
                  for number, page in document.pages.items()]))),
              **_coverage(document, coverage_spans)}
    report["complete"] = not (report["manifest_missing"] or unapproved or document.missing_pages or report["uncovered_spans"])
    return source, document, chunks, cases, report


def build_database(root=None, out=None, allow_partial=False):
    """Atomically replace out with new approved units; never read an existing DB."""
    root = Path(root or project_root()).resolve()
    out = Path(out or root / "data/knowledge.sqlite").resolve()
    registry = root / "data/canonical/sources.jsonl"
    sources = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not sources or len({s["source_id"] for s in sources}) != len(sources):
        raise ValueError("canonical source registry must contain unique source IDs and cannot be empty")
    parsed = [_parse(root, source) for source in sources]
    groups = defaultdict(list)
    for _, _, _, cases, _ in parsed:
        for case in cases:
            groups[case["duplicate_group"]].append(case["case_id"])
    for _, _, _, cases, _ in parsed:
        for case in cases:
            case["duplicate_candidates"] = [eid for eid in groups[case["duplicate_group"]] if eid != case["case_id"]]
    reports = [item[4] for item in parsed]
    ids = [record.get("id", record.get("case_id")) for _, _, chunks, cases, _ in parsed for record in chunks + cases]
    if len(set(ids)) != len(ids):
        raise ValueError("manual unit IDs must be globally unique")
    implementation_hash = digest("".join(Path(__file__).with_name(name).read_text(encoding="utf-8")
                                         for name in ("manual_ingest.py", "canonical.py", "ingest.py", "chart.py", "common.py", "taxonomy.py", "patterns.py", "outline.py", "proofreading.py", "rule_references.py")))
    mapping = load_mapping(root)
    mapping_path = root / "data/manual_slices/rule_references.json"
    mapping_document = json.loads(mapping_path.read_text(encoding="utf-8")) if mapping_path.is_file() else {}
    report = {"mode": "manual-corpus", "parser_version": VERSION, "allow_partial": bool(allow_partial),
              "status": "complete" if all(r["complete"] for r in reports) else "incomplete",
              "implementation_hash": implementation_hash, "sources": reports,
              "total_chunks": sum(r["chunks"] for r in reports), "total_cases": sum(r["cases"] for r in reports),
              "total_case_units": sum(r["case_units"] for r in reports),
              "total_case_events": len(groups),
              "case_quality": dict(Counter(case["quality"]["status"] for _, _, _, cases, _ in parsed for case in cases)),
              "total_unapproved_units": sum(r["unapproved_count"] for r in reports),
              "rule_references_sha256": digest(dumps(_portable(mapping_document))), "total_rule_references": len(mapping),
              "limitations": ["Scope and topic labels use manual declarations only; missing declarations stay unknown.",
                              "Chart validation requires an explicit hashed independent source-chart audit; missing audits remain not_run.",
                              "Only quality=eligible cases enter retrieval; pending/noise cases remain archived and cannot count as validation evidence.",
                              "PDF canonical text has no line mapping to historical OCR."]}
    report["corpus_hash"] = digest(dumps(_portable(sources)) + dumps(_portable(reports)) + implementation_hash + report["rule_references_sha256"])
    if report["status"] != "complete" and not allow_partial:
        raise IncompleteCorpusError(report)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=out.stem + ".building-", suffix=".sqlite", dir=out.parent, delete=False) as handle:
        temp = Path(handle.name)
    try:
        with closing(sqlite3.connect(temp)) as db:
            db.executescript(SCHEMA)
            db.executemany("INSERT INTO topics VALUES(?,?,?)", ((n["id"], n["parent_id"], n["title"]) for n in topic_nodes()))
            for source, document, chunks, cases, _ in parsed:
                sid = source["source_id"]
                body = document.body
                outline = _manual_outline(source, chunks, cases)
                db.execute("INSERT INTO sources VALUES(?,?,?)", (sid, dumps(source), body))
                db.executemany("INSERT INTO ocr_pages VALUES(?,?,?)", ((sid, page["pdf_page"], dumps(page)) for page in _page_records(document)))
                if source["source_type"] == "native_text":
                    db.execute("INSERT INTO original_sources VALUES(?,?)", (sid, body))
                for chunk in chunks:
                    db.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?)", (chunk["id"], sid, chunk["kind"], chunk["method"], chunk["chapter"], chunk["start_line"], chunk["end_line"], chunk["content_hash"], dumps(chunk)))
                    text = "\n".join([chunk["chapter"], chunk["text"], *[context["text"] for context in chunk["required_contexts"]]])
                    db.execute("INSERT INTO search_index VALUES(?,?,?,?)", (chunk["id"], "rule", " ".join(tokens(chunk["chapter"])), " ".join(tokens(text))))
                for case in cases:
                    db.execute("INSERT INTO cases VALUES(?,?,?,?,?,?)", (case["case_id"], sid, case["question"]["topic"], case["method"], case["duplicate_group"], dumps(case)))
                    if case["quality"]["status"] == "eligible":
                        indexed = case if case["extraction"]["chart_validation"] == "calculated" else {**case, "derived": None}
                        db.execute("INSERT INTO search_index VALUES(?,?,?,?)", (case["case_id"], "case", " ".join(tokens(case["question"]["raw"])), " ".join(tokens(case_search_text(indexed)))))
                for record in chunks + cases:
                    kind = "case" if "case_id" in record else "rule"
                    eid = record["case_id"] if kind == "case" else record["id"]
                    store_search_metadata(db, kind, record, {**source, "method_hint": record["method"]})
                    classification = record["classification"]
                    db.execute("INSERT INTO evidence_classification VALUES(?,?,?)", (eid, classification["scope"], dumps(classification)))
                    db.executemany("INSERT INTO evidence_topics VALUES(?,?)", ((eid, topic) for topic in set(classification["topic_ids"]) | set(classification["roots"])))
                store_outline(db, outline, chunks, cases)
            store_mapping(db, root)
            if {row[0]: json.loads(row[1]) for row in db.execute("SELECT reference_id,payload FROM rule_references")} != mapping:
                raise ValueError("rule reference mapping changed during database build")
            info = {"mode": "manual-corpus", "parser_version": VERSION, "search_index_version": SEARCH_INDEX_VERSION,
                    "implementation_hash": implementation_hash, "corpus_hash": report["corpus_hash"],
                    "coverage_status": report["status"], "allow_partial": str(bool(allow_partial)).lower(),
                    "rule_references_sha256": report["rule_references_sha256"],
                    "coverage_report": dumps(report)}
            db.executemany("INSERT INTO build_info VALUES(?,?)", info.items())
            db.commit()
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Database integrity check failed")
        temp.replace(out)
    finally:
        temp.unlink(missing_ok=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=project_root())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-partial", action="store_true", help="build an explicitly incomplete development corpus")
    args = parser.parse_args()
    try:
        report = build_database(args.root, args.output, args.allow_partial)
    except IncompleteCorpusError as exc:
        print(json.dumps(exc.report, ensure_ascii=False, indent=2))
        parser.exit(2, "Manual corpus is incomplete; database was not replaced.\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
