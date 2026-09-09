"""Deterministic source import. Uncertain extraction remains visible in JSON."""
import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .chart import BRANCHES, STEMS, HEXAGRAMS, build_chart, calendar_values
from .common import case_search_text, digest, dumps, normalized, plain, project_root, tokens, topic_of

PARSER_VERSION = "source-parser-0.1"
PAGE = re.compile(r"=+ PDF 第 (\d+) 页 / 共 (\d+) 页 =+")
DATE = re.compile(rf"([{BRANCHES}])月.{{0,10}}?([{STEMS}][{BRANCHES}])日")
ROW = re.compile(r"(父母|兄弟|子孙|妻财|官鬼)([子丑寅卯辰巳午未申酉戌亥])[木火土金水]?")
CHAPTER = re.compile(r"^(?:#{1,6}\s+|第[一二三四五六七八九十百\d]+[章节]\s*|[一二三四五六七八九十]+、)")
OUTCOME = re.compile(r"(?:卦主反馈|反馈\s*[:：，,]|(?:^|[。！？])\s*(?:结果|果于|果然|后果|后验))")
NO_FEEDBACK = re.compile(r"(?:暂无|尚无|没有|未收到|尚未收到|未有|未见)反馈|反馈\s*[:：]\s*(?:暂无|没有|尚无|待补|未提供)|(?:尚未|暂未|未)反馈")
AUTHORS = {"liuyao_zixiu_dxj": "王虎应", "zengshan_pingshi_dxj": "王虎应（含原注）", "zengshan_buyi": "野鹤老人等（整理版）"}


def spans_of(indices):
    spans = []
    for i in sorted(set(indices)):
        if spans and spans[-1]["end_line"] == i:
            spans[-1]["end_line"] = i + 1
        else:
            spans.append({"start_line": i + 1, "end_line": i + 1})
    return spans


def read_spans(lines, spans):
    return "\n".join("\n".join(lines[s["start_line"]-1:s["end_line"]]) for s in spans)


def symbol_value(text):
    if "×" in text or "Ｘ" in text:
        return 6
    if "○" in text or "Ｏ" in text or re.search(r"\bO\b", text):
        return 9
    if re.search(r"━━\s+━━|▅▅\s+▅▅|″|〃", text):
        return 8
    if "━━━━" in text or "▅▅▅▅▅" in text or "′" in text:
        return 7
    return None


def name_in(text):
    matches = [(text.find(h["full_name"]), h["name"]) for h in HEXAGRAMS.values() if h["full_name"] in text]
    for match in re.finditer(r"(?:得|变|之)[“\"「]?([乾兑离震巽坎艮坤])卦", text):
        matches.append((match.start(1), match[1]))
    # Some classics use short names: 得复之震. Restrict to explicit quoted names.
    if not matches:
        m = re.search(r"得[“\"「]?([\u4e00-\u9fff]{1,3})[”\"」]?之", text)
        if m and m[1] in {h["name"] for h in HEXAGRAMS.values()}:
            matches = [(m.start(1), m[1])]
    return [name for _, name in sorted(set(matches))]


def native_row(row):
    """Choose the symbol-bearing main line, excluding a preceding hidden line."""
    matches = list(ROW.finditer(row))
    for i, m in enumerate(matches):
        suffix = row[m.end():matches[i+1].start() if i+1<len(matches) else len(row)]
        value = symbol_value(suffix)
        if value is not None:
            if "动" in suffix and value in (7, 8):
                value = 9 if value == 7 else 6
            return m, value
    return None, None


def extract_cases(source, lines, pages, cutoff):
    diagrams, all_diagram_lines = defaultdict(list), set()
    for i, line in enumerate(lines[:cutoff]):
        if "【卦象结构化" not in line:
            continue
        rows = [(j, lines[j]) for j in range(i+1, min(i+12, cutoff)) if re.match(r"^(?:上|五|四|三|二|初)爻\s", lines[j])][:6]
        positions = [re.match(r"^(上|五|四|三|二|初)爻", row)[1] for _, row in rows]
        values = [symbol_value(row.split("→")[0]) for _, row in rows]
        end = rows[-1][0] + 1 if rows else i+1
        all_diagram_lines.update(range(i, end))
        diagrams[pages[i]].append({"start": i, "end": end, "values": list(reversed(values)) if positions == list("上五四三二初") and all(v is not None for v in values) else None})

    anchors = []
    for i, line in enumerate(lines[:cutoff]):
        if "主变卦" in line or (DATE.search(plain(line)) and re.search(r"[占测].*(?:得|之)|得.*卦", plain(line))):
            # Generic theory without a nearby six-line display is not an event.
            nearby = [l for l in lines[i+1:min(i+65, cutoff)] if l.strip()]
            if "主变卦" in line or sum(bool(ROW.search(l)) and symbol_value(l) is not None for l in nearby[:15]) >= 5:
                anchors.append(i)
    anchors = sorted(set(anchors))
    by_page = defaultdict(list)
    for a in anchors:
        by_page[pages[a]].append(a)
    assigned = {}
    for page, ds in diagrams.items():
        aa = by_page[page]
        if len(aa) == len(ds):
            assigned.update(zip(aa, ds))
        else:
            # Never attach a page-tail diagram to the nearest question blindly.
            for d in ds:
                if d["values"]:
                    bits = sum((v % 2) << i for i, v in enumerate(d["values"]))
                    matches = [a for a in aa if HEXAGRAMS[bits]["name"] in name_in(lines[a])]
                    if len(matches) == 1 and matches[0] not in assigned:
                        assigned[matches[0]] = d

    starts = []
    for ai, a in enumerate(anchors):
        floor = anchors[ai-1]+1 if ai else 0
        metadata = [i for i in range(max(floor, a-30), a+1) if re.match(r"^求测人", lines[i].strip())]
        start = metadata[-1] if metadata else a
        if not metadata:
            for i in range(max(floor, a-8), a):
                if re.match(r"^\**例[一二三四五六七八九十\d]", lines[i].strip()):
                    start = i
                    break
        starts.append(start)

    cases = []
    protected_lines = set(all_diagram_lines)
    for ai, (a, start) in enumerate(zip(anchors, starts)):
        next_start = starts[ai+1] if ai+1 < len(starts) else cutoff
        heading = next((i for i in range(a+1, next_start) if CHAPTER.match(lines[i].strip()) and not lines[i].startswith("【")), next_start)
        end = min(next_start, heading, a+220)
        ds = assigned.get(a)
        indices = [i for i in range(start, end) if i not in all_diagram_lines]
        if ds:
            indices += list(range(ds["start"], ds["end"]))
        spans = spans_of(indices)
        raw = read_spans(lines, spans)
        narrative = "\n".join(lines[i] for i in range(start, end) if i not in all_diagram_lines and not PAGE.search(lines[i]))
        header_lines = lines[start:a+1]
        question = next((re.sub(r"^.*?占问事宜[\s:：;；，,]*", "", line).strip() for line in header_lines if "占问事宜" in line), plain(lines[a]))
        if not question or question.startswith("主变卦"):
            question = next((plain(line) for line in header_lines if "占" in line or "测" in line), None)
        header = "\n".join(header_lines)
        date_match = DATE.search(plain(header))
        day_match = re.search(rf"([{STEMS}][{BRANCHES}])日", header)
        month_match = re.search(rf"([{BRANCHES}])月", header)
        date = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", header)
        date_text = f"{int(date[1]):04}-{int(date[2]):02}-{int(date[3]):02}" if date else None
        time_match = re.search(r"日\s*(\d{1,2})时\s*(\d{1,2})\s*分", header)
        time_text = f"{int(time_match[1]):02}:{int(time_match[2]):02}:00" if time_match else None
        values = ds["values"] if ds else None
        pan_rows = []
        for i in range(a+1, min(a+55, end)):
            row = lines[i].strip()
            if not row:
                continue
            ocr_row = source["source_type"] == "ocr_text" and len(row)<140 and re.search(r"图|国|田|轿|轩|[▅━]|青龙|朱[雀徐党逢]|勾陈|[腾螣]蛇|白虎|玄武", row) and not re.match(r"^(?:测|本卦|反馈|在此|这是|所以|说明)", row)
            if ocr_row or (source["source_type"] == "native_text" and native_row(row)[1] is not None):
                pan_rows.append((i, row))
                if len(pan_rows) == 6:
                    break
            elif pan_rows or len(row) > 120:
                break
        if values is None and source["source_type"] == "native_text" and len(pan_rows) == 6:
            vals = [native_row(row)[1] for _, row in pan_rows]
            if all(v is not None for v in vals):
                values = list(reversed(vals))
                protected_lines.update(range(pan_rows[0][0], pan_rows[-1][0]+1))
        names = name_in(lines[a])
        void = re.search(r"空亡[:：\s]*([^\]\n]+)", header)
        issues, calculated = [], None
        month = date_match[1] if date_match else month_match[1] if month_match else None
        day = date_match[2] if date_match else day_match[1] if day_match else None
        calendar_basis = "reported_ganzhi"
        if date_text and time_text:
            try:
                calendar = calendar_values(date_text+"T"+time_text)
                if (month and month != calendar["month_branch"]) or (day and day != calendar["day_ganzhi"]):
                    issues.append("reported_calendar_conflicts_with_civil_time")
                if not month or not day:
                    month = month or calendar["month_branch"]
                    day = day or calendar["day_ganzhi"]
                    calendar_basis = "civil_time_with_AsiaShanghai_convention"
            except ValueError:
                issues.append("invalid_reported_civil_time")
        validation = "not_run"
        if values and month and day:
            try:
                calculated = build_chart(values, month_branch=month, day_ganzhi=day)
                validation = "calculated"
                if names and names[0] != calculated["primary"]["name"]:
                    issues.append("reported_primary_conflicts_with_line_values")
                if len(names) > 1 and names[1] != calculated["changed"]["name"]:
                    issues.append("reported_changed_conflicts_with_line_values")
                for position, (_, row) in enumerate(reversed(pan_rows if len(pan_rows) == 6 else []), 1):
                    m = native_row(row)[0] if source["source_type"] == "native_text" else ROW.search(row)
                    if m and position <= 6 and (m[1], m[2]) != (calculated["lines"][position-1]["relative"], calculated["lines"][position-1]["branch"]):
                        issues.append(f"reported_line_{position}_conflicts_with_najia")
                if issues:
                    validation = "conflict"
            except ValueError as exc:
                issues.append(str(exc))
        if not values:
            issues.append("missing_or_ambiguous_six_lines")
        if not question:
            issues.append("missing_question")
        if not month or not day:
            issues.append("missing_valid_month_or_day")
        if void and any(c not in BRANCHES for c in re.findall(r"[\u4e00-\u9fff]", void[1])):
            issues.append("invalid_character_in_reported_void")
        if end == a+220:
            issues.append("case_narrative_boundary_limited")
        analysis_start = pan_rows[-1][0]+1 if len(pan_rows) == 6 else a+1
        analysis = "\n".join(lines[i] for i in range(analysis_start, end) if i not in all_diagram_lines and not PAGE.search(lines[i])).strip()
        feedback_lines = analysis.splitlines()
        outcomes = []
        for i, line in enumerate(feedback_lines):
            if OUTCOME.search(line) and not NO_FEEDBACK.search(line) and not re.search(r"结果(?:会|可能|将)", line):
                quote = [line]
                for next_line in feedback_lines[i+1:i+6]:
                    if not next_line.strip() or re.match(r"^求测|^例|^第", next_line):
                        break
                    quote.append(next_line)
                outcomes.append("\n".join(quote))
        yongshen = list(dict.fromkeys(re.findall(r"(父母|兄弟|子孙|妻财|官鬼)(?:爻)?(?:为用神|为用|作[为]?用神)", plain(analysis))))
        features = dict(calculated["features"]) if calculated and validation != "conflict" else {}
        features.update({"topic": topic_of(question or ""), "yongshen_reported": yongshen or None, "yongshen_basis": "author_text" if yongshen else None, "chart_feature_status": validation})
        if calculated and validation != "conflict" and yongshen:
            features["yongshen_candidates"] = [{"position": line["position"], "relative": line["relative"], "void": line["void"], "month_break": line["month_break"], "moving": line["moving"], "selection": "relative_match_not_author_line_selection"} for line in calculated["lines"] if line["relative"] in yongshen]
        case_id = f"case_{source['source_id']}_{a+1}"
        cases.append({
            "schema_version": "0.1", "case_id": case_id, "related_case_ids": [],
            "question": {"raw": question, "topic": features["topic"]},
            "cast": {"date": date_text, "time": time_text, "timezone": None, "calendar_basis": calendar_basis, "month_branch": month, "day_ganzhi": day, "line_values": values, "lines_order": "bottom_to_top", "line_values_basis": "transcribed_diagram" if ds else "native_line_symbols" if values else None},
            "reported_chart": {"raw_header": lines[a], "primary": names[0] if names else None, "changed": names[1] if len(names)>1 else None, "void_raw": void[1] if void else None, "line_text": [row for _, row in pan_rows]},
            "derived": calculated, "features": features,
            "interpretations": [{"source_id": source["source_id"], "author": source.get("author"), "method_hint": source["method_hint"], "yongshen_reported": yongshen or None, "original_text": analysis}],
            "outcome": {"status": "reported_explicit" if outcomes else "none", "quotes": outcomes, "event_date": None, "event_timing": "before_or_at_cast" if outcomes and re.search(r"已经发生|现状|过去.*发生", analysis) else "unknown", "independently_verified": False},
            "source": {"source_id": source["source_id"], "path": source["path"], "sha256": source["sha256"], "pdf_pages": sorted({pages[i] for i in indices if pages[i] is not None}), "spans": spans, "original_text": raw, "raw_text_normalization": "python_universal_newlines"},
            "extraction": {"method": "deterministic_parser", "pipeline_version": PARSER_VERSION, "status": "partial" if issues else "parsed", "issues": issues, "chart_validation": validation},
        })
    return cases, protected_lines


def assign_duplicate_groups(cases):
    """Conservative possible-duplicate groups; keep every source record intact."""
    parent = {c["case_id"]: c["case_id"] for c in cases}
    buckets = defaultdict(list)
    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key
    for case in cases:
        cast = case["cast"]
        primary = case["reported_chart"]["primary"]
        q = normalized(case["question"]["raw"] or "")
        if not all((primary, cast["month_branch"], cast["day_ganzhi"], q)):
            continue
        bucket = (primary, cast["month_branch"], cast["day_ganzhi"])
        for other, oq in buckets[bucket]:
            other_date = other["cast"]["date"]
            if cast["date"] and other_date and cast["date"] != other_date:
                continue
            threshold = 0.85 if cast["date"] and cast["date"] == other_date else 0.97
            if SequenceMatcher(None,q,oq,autojunk=False).ratio() >= threshold:
                roots = sorted((find(case["case_id"]),find(other["case_id"])))
                parent[roots[1]] = roots[0]
        buckets[bucket].append((case,q))
    members = defaultdict(list)
    for case in cases:
        members[find(case["case_id"])].append(case["case_id"])
    for case in cases:
        group = find(case["case_id"])
        case["duplicate_group"] = group
        case["duplicate_candidates"] = [c for c in members[group] if c != case["case_id"]]
        case["duplicate_group_basis"] = "calendar_primary_and_similar_question_candidate" if len(members[group])>1 else "single_source_record"


def import_source(source, root):
    path = (root / source["path"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Source path leaves project root")
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != source["sha256"]:
        raise ValueError(f"Source hash changed: {source['source_id']}; update manifest intentionally")
    text = blob.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    source = {**source, "author": source.get("author", AUTHORS.get(source["source_id"]))}
    cutoff = next((i for i, l in enumerate(lines) if l.startswith("## 原文逐段校核副本")), len(lines))
    page, pages, page_anchors = None, [], []
    for i, line in enumerate(lines):
        m = PAGE.search(line)
        if m:
            page = int(m[1])
            page_anchors.append({"page": page, "total": int(m[2]), "line": i+1})
        pages.append(page)
    if source["pdf_pages"] and ([p["page"] for p in page_anchors] != list(range(1, source["pdf_pages"]+1)) or any(p["total"] != source["pdf_pages"] for p in page_anchors)):
        raise ValueError(f"OCR page sequence mismatch: {source['source_id']}")
    cases, diagram_lines = extract_cases(source, lines, pages, cutoff)
    reasons, chunks, pending = {}, [], []
    chapter = source["title"]
    chapter_start = 0
    def flush():
        if not pending:
            return
        start, end = pending[0], pending[-1]+1
        body = "\n".join(lines[start:end])
        method = source["method_hint"]
        if method == "mixed":
            method = "xiangfa" if re.search(r"象法|取象|类象|六神", chapter) else "lifa"
        chunks.append({"id": f"rule_{source['source_id']}_{start+1}", "source_id": source["source_id"], "kind": "passage", "chapter": chapter, "chapter_start": chapter_start+1, "start_line": start+1, "end_line": end, "pages": sorted({pages[i] for i in pending if pages[i] is not None}), "text": body, "method": method, "content_hash": digest(normalized(body))})
        pending.clear()
    for i, line in enumerate(lines):
        stripped = line.strip()
        reason = None
        if i >= cutoff:
            reason = "validation_copy"
        elif not stripped:
            reason = "blank"
        elif PAGE.search(line):
            reason = "page_anchor"
        elif stripped.startswith("```") or stripped.startswith("> 原文件") or stripped.startswith("> 转换方式"):
            reason = "format_metadata"
        elif stripped.isdigit():
            reason = "printed_page_number"
        elif re.match(r"^!\[.*\]\(.*\)$", stripped):
            reason = "image_placeholder"
        elif re.match(r"^\[.*\]\(#.*\)$", stripped) or "请加助理" in stripped:
            reason = "toc_or_advertisement"
        if reason:
            reasons[i] = reason
            if reason not in ("blank",):
                flush()
            continue
        if CHAPTER.match(stripped) and len(plain(stripped)) < 110:
            flush()
            chapter, chapter_start = plain(stripped), i
        # Don't split a six-line diagram, or a single long paragraph, for size alone.
        if pending and sum(len(lines[j]) for j in pending) >= 1100 and i not in diagram_lines and (i == 0 or not lines[i-1].strip()):
            flush()
        pending.append(i)
    flush()
    coverage = set(reasons)
    for chunk in chunks:
        coverage.update(range(chunk["start_line"]-1, chunk["end_line"]))
    if len(coverage) != len(lines):
        raise AssertionError("Unaccounted source lines")
    report = {"source_id": source["source_id"], "sha256": source["sha256"], "total_lines": len(lines), "covered_lines": len(coverage), "page_anchors": page_anchors, "chunks": len(chunks), "cases": len(cases), "case_status": dict(Counter(c["extraction"]["status"] for c in cases)), "chart_validation": dict(Counter(c["extraction"]["chart_validation"] for c in cases)), "excluded_ranges": [{"reason": reason, **span} for reason in sorted(set(reasons.values())) for span in spans_of(i for i, r in reasons.items() if r == reason)]}
    return source, text, chunks, cases, report


SCHEMA = """
CREATE TABLE sources(id TEXT PRIMARY KEY, metadata TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE chunks(id TEXT PRIMARY KEY, source_id TEXT NOT NULL, kind TEXT NOT NULL, method TEXT NOT NULL, chapter TEXT NOT NULL, start_line INT, end_line INT, content_hash TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE cases(id TEXT PRIMARY KEY, source_id TEXT NOT NULL, topic TEXT, method TEXT, duplicate_group TEXT, payload TEXT NOT NULL);
CREATE TABLE eval_items(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE build_info(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE VIRTUAL TABLE search_index USING fts5(evidence_id UNINDEXED, kind UNINDEXED, body, tokenize='unicode61');
"""


def ingest(root=None, output=None):
    root = Path(root or project_root()).resolve()
    out = Path(output or root / "data/knowledge.sqlite").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest = [json.loads(line) for line in (root / "data/sources.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if len({s["source_id"] for s in manifest}) != len(manifest):
        raise ValueError("Duplicate source IDs")
    parsed = [import_source(source, root) for source in manifest]
    assign_duplicate_groups([case for _,_,_,cases,_ in parsed for case in cases])
    temp = out.with_suffix(".building.sqlite")
    if temp.exists():
        temp.unlink()
    connection = sqlite3.connect(temp)
    reports, all_cases = [], []
    try:
        connection.executescript(SCHEMA)
        for source, text, chunks, cases, report in parsed:
            sid = source["source_id"]
            connection.execute("INSERT INTO sources VALUES(?,?,?)", (sid, dumps(source), text))
            for chunk in chunks:
                connection.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?)", (chunk["id"], sid, chunk["kind"], chunk["method"], chunk["chapter"], chunk["start_line"], chunk["end_line"], chunk["content_hash"], dumps(chunk)))
                connection.execute("INSERT INTO search_index VALUES(?,?,?)", (chunk["id"], "rule", " ".join(tokens(chunk["chapter"] + " " + chunk["text"]))))
            for case in cases:
                group = case["duplicate_group"]
                connection.execute("INSERT INTO cases VALUES(?,?,?,?,?,?)", (case["case_id"], sid, case["question"]["topic"], source["method_hint"], group, dumps(case)))
                # Author judgement/outcome are returned AFTER retrieval, never indexed here.
                search_text = case_search_text(case)
                connection.execute("INSERT INTO search_index VALUES(?,?,?)", (case["case_id"], "case", " ".join(tokens(search_text))))
            reports.append(report)
            all_cases.extend(cases)
        implementation_hash = digest("".join(Path(__file__).with_name(name).read_text(encoding="utf-8") for name in ("ingest.py", "chart.py", "common.py")))
        corpus_hash = digest(dumps(manifest) + PARSER_VERSION + implementation_hash)
        connection.execute("INSERT INTO build_info VALUES('corpus_hash',?)", (corpus_hash,))
        connection.execute("INSERT INTO build_info VALUES('parser_version',?)", (PARSER_VERSION,))
        connection.execute("INSERT INTO build_info VALUES('implementation_hash',?)", (implementation_hash,))
        connection.commit()
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Database integrity check failed")
    finally:
        connection.close()
    temp.replace(out)
    report = {"parser_version": PARSER_VERSION, "implementation_hash": implementation_hash, "corpus_hash": corpus_hash, "sources": reports, "total_chunks": sum(r["chunks"] for r in reports), "total_cases": len(all_cases), "total_ocr_pages": sum(len(r["page_anchors"]) for r in reports), "limitations": ["OCR correctness unverified", "semantic fields may be partial", "duplicate grouping is conservative and may miss rewrites"]}
    (out.parent / "cases.jsonl").write_text("".join(dumps(c)+"\n" for c in all_cases), encoding="utf-8")
    (out.parent / "ingest_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=project_root())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = ingest(args.root, args.output)
    print(dumps({k: v for k, v in report.items() if k != "sources"}))


if __name__ == "__main__":
    main()
