"""Export unapproved chart candidates from existing canonical page-image caches."""
import argparse
import hashlib
import re
import json
import time
from pathlib import Path

import cv2
import numpy as np

VERSION = "geometry-candidates-v2.1"
ROOT = Path(__file__).resolve().parents[1]


def bounds(parts):
    return [min(p[0] for p in parts), min(p[1] for p in parts),
            max(p[0] + p[2] for p in parts), max(p[1] + p[3] for p in parts)]


def group_rows(parts, tolerance):
    groups = []
    for part in sorted(parts, key=lambda p: p[1]):
        if not groups or abs(part[1] - np.median([p[1] for p in groups[-1]])) > tolerance:
            groups.append([])
        groups[-1].append(part)
    return groups


def detect_symbol(binary, bar, spacing):
    x0, y0, x1, y1 = bar
    bw, bh = x1 - x0, y1 - y0
    # The marker is immediately after the main bar, above its visual centre.
    sx0, sx1 = x1 + 1, x1 + round(bw * .20)
    sy0, sy1 = round((y0 + y1) / 2 - spacing * .44), round((y0 + y1) / 2 + spacing * .30)
    evidence = {"roi": [sx0, sy0, sx1, sy1], "components": []}
    if sx0 < 0 or sy0 < 0 or sx1 > binary.shape[1] or sy1 > binary.shape[0]:
        evidence["reason"] = "symbol_region_outside_image"
        return "?", evidence
    roi = binary[sy0:sy1, sx0:sx1]
    count, labels, stats, _ = cv2.connectedComponentsWithStats(roi)
    parts = [(i, s) for i, s in enumerate(stats[1:], 1)
             if s[2] > bw * .07 and s[3] > bh * .60 and s[4] > 25]
    evidence["ink_pixels"] = int(np.count_nonzero(roi))
    if not parts:
        if evidence["ink_pixels"] > max(12, bw*bh*.008):
            evidence["reason"] = "unclassified_ink_in_symbol_region"
            return "?", evidence
        evidence["blank_region_observed"] = True
        return "", evidence
    for i, (x, y, w, h, area) in parts:
        mask = np.uint8(labels[y:y+h, x:x+w] == i) * 255
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        holes = sum(1 for j, entry in enumerate(hierarchy[0])
                    if entry[3] >= 0 and cv2.contourArea(contours[j]) > w*h*.15)
        yy, xx = np.where(mask > 0)
        xx, yy = xx / max(1, w-1), yy / max(1, h-1)
        diagonal_fraction = float(np.mean(np.minimum(abs(xx-yy), abs(xx+yy-1)) < .12))
        clipped = x == 0 or y == 0 or x+w >= roi.shape[1] or y+h >= roi.shape[0]
        symbol = "?"
        if not clipped and .7 < w/h < 1.3:
            if holes == 1:
                symbol = "○"
            elif holes == 0 and diagonal_fraction > .75:
                symbol = "×"
        evidence["components"].append({"box": [int(sx0+x), int(sy0+y), int(sx0+x+w), int(sy0+y+h)],
                                       "holes": holes, "diagonal_fraction": diagonal_fraction,
                                       "clipped": bool(clipped), "symbol": symbol})
    return evidence["components"][0]["symbol"] if len(parts) == 1 else "?", evidence


def extract(gray):
    height, width = gray.shape
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (width//95, width//170)))
    opened = cv2.morphologyEx(opened, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (width//230, 1)))
    _, _, stats, _ = cv2.connectedComponentsWithStats(opened)
    parts = [list(map(int, s[:4])) for s in stats[1:]
             if width*.03 < s[2] < width*.16 and width*.008 < s[3] < width*.03
             and s[2]/s[3] > 2.5 and s[4]/(s[2]*s[3]) > .65]
    rows = []
    for group in group_rows(parts, width*.006):
        bars = []
        for part in sorted(group):
            if not bars or part[0] - max(p[0]+p[2] for p in bars[-1]) > width*.05:
                bars.append([])
            bars[-1].append(part)
        if len(bars) in (1, 2):
            boxes = [bounds(bar) for bar in bars]
            if all(width*.10 < b[2]-b[0] < width*.16 for b in boxes):
                rows.append(boxes)
    candidates = []
    for start in range(len(rows)-5):
        six = rows[start:start+6]
        columns = len(six[0])
        if any(len(row) != columns for row in six):
            continue
        centers = [(b[0][1]+b[0][3])/2 for b in six]
        spacing = float(np.median(np.diff(centers)))
        if not width*.02 < spacing < width*.06:
            continue
        if max(abs(np.diff(centers)-spacing)) > spacing*.15:
            continue
        if any(np.ptp([row[column][0] for row in six]) > width*.01 for column in range(columns)):
            continue
        line_rows = []
        for position, row in enumerate(reversed(six), 1):
            bits, densities = [], []
            for x0, y0, x1, y1 in row:
                bw, bh = x1-x0, y1-y0
                centre = binary[y0+int(bh*.25):y0+int(bh*.75), x0+int(bw*.43):x0+int(bw*.57)]
                density = float(np.mean(centre > 0))
                bits.append(1 if density > .75 else 0 if density < .15 else None)
                densities.append(density)
            symbol, evidence = detect_symbol(binary, row[0], spacing)
            changed = bits[1] if columns == 2 else None
            expected = ("" if bits[0] == changed else "○" if bits[0] == 1 else "×") if columns == 2 else None
            marker_valid = (bits[0] in (0, 1) and symbol in ("", "○", "×") and
                            not (symbol == "○" and bits[0] != 1) and not (symbol == "×" and bits[0] != 0))
            cross_valid = symbol == expected if columns == 2 else None
            value = (3 if symbol == "○" else 0 if symbol == "×" else 1 if bits[0] else 2)
            if not marker_valid or cross_valid is False or (columns == 2 and changed not in (0, 1)):
                value = None
            line_rows.append({"position": position, "main_bit": bits[0], "changed_bit": changed,
                              "bar_boxes": row, "centre_density": densities,
                              "symbol": symbol, "symbol_evidence": evidence,
                              "symbol_matches_main_changed": cross_valid, "value_0123": value})
        reasons = ["primary_only_no_changed_cross_validation"] if columns == 1 else []
        if any(l["value_0123"] is None for l in line_rows):
            reasons.append("ambiguous_bits_or_symbol_conflict")
        candidates.append({"box": bounds([[b[0], b[1], b[2]-b[0], b[3]-b[1]] for row in six for b in row]),
                           "kind": "paired" if columns == 2 else "primary_only", "line_order": "bottom_to_top",
                           "main_bits": [l["main_bit"] for l in line_rows],
                           "changed_bits": [l["changed_bit"] for l in line_rows] if columns == 2 else None,
                           "line_values_0123": [l["value_0123"] for l in line_rows],
                           "row_spacing": spacing, "status": "needs_review" if reasons else "geometry_consistent",
                           "needs_review": bool(reasons), "review_reasons": reasons,
                           "changed_cross_validation_available": columns == 2, "approved": False,
                           "lines": line_rows})
    return candidates


def chart_signals(cache):
    ocr = cache.get("ocr")
    lines = [item["text"] for item in ocr["lines"]] if ocr else cache["canonical"]["text"].splitlines()
    spirits = ("青龙", "朱雀", "勾陈", "白虎", "玄武", "螣蛇", "腾蛇", "滕蛇")
    headings = [line for line in lines if re.search(r"主变卦|本卦|变卦", line)]
    spirit_lines = [line for line in lines if any(s in line for s in spirits)]
    relative_lines = [line for line in lines if re.search(r"(?:兄弟|子孙|妻财|官鬼|父母)[甲乙丙丁戊己庚辛壬癸]?[子丑寅卯辰巳已午未申酉戌亥][木火土金水]", line)]
    return {"basis": "raw_ocr_lines" if ocr else "canonical_page_text",
            "text_available": any(line.strip() for line in lines),
            "heading_count": len(headings), "spirit_line_count": len(spirit_lines),
            "relative_line_count": len(relative_lines),
            "has_chart_signal": bool(headings or len(spirit_lines) >= 3 or len(relative_lines) >= 4),
            "evidence": {"headings": headings, "spirit_lines": spirit_lines, "relative_lines": relative_lines}}


def review_reasons(candidates, signals):
    reasons = []
    if not candidates and not signals["text_available"]:
        reasons.append("zero_candidates_without_text_evidence")
    elif not candidates and signals["has_chart_signal"]:
        reasons.append("zero_candidates_with_chart_text_signals")
    elif len(candidates) < signals["heading_count"]:
        reasons.append("fewer_candidates_than_chart_heading_signals")
    if any(c["needs_review"] for c in candidates):
        reasons.append("candidate_requires_review")
    return reasons


def write_jsonl(path, records):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in records), encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT/".local/canonical-extraction")
    parser.add_argument("--output", type=Path, default=ROOT/"data/chart_candidates")
    parser.add_argument("--source", action="append", help="Restrict to source IDs; default: all cached sources")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    code_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    # Snapshot only completed image+JSON pairs. Rerun the same command to pick up later pages.
    selected = {d.name: sorted(p for p in d.glob("[0-9][0-9][0-9][0-9].png") if p.with_suffix(".json").exists())
                for d in sorted(args.cache.iterdir()) if d.is_dir() and (not args.source or d.name in args.source)}
    started = time.perf_counter()
    processed = skipped = 0
    for source, paths in selected.items():
        target = args.output/(source+".jsonl")
        records = {r["pdf_page"]: r for r in map(json.loads, target.read_text(encoding="utf-8").splitlines())} if target.exists() else {}
        for index, path in enumerate(paths, 1):
            page = int(path.stem)
            image_bytes = path.read_bytes()
            image_sha = hashlib.sha256(image_bytes).hexdigest()
            raw_cache = path.with_suffix(".json").read_bytes()
            cache_sha = hashlib.sha256(raw_cache).hexdigest()
            old = records.get(page, {})
            if old.get("error") is None and (old.get("algorithm_sha256"), old.get("image_sha256"), old.get("cache_sha256")) == (code_sha, image_sha, cache_sha):
                skipped += 1
                continue
            cache = json.loads(raw_cache)
            signals = chart_signals(cache)
            cache_matches = (cache["image"]["sha256"] == image_sha and
                             cache["canonical"]["source_id"] == source and cache["canonical"]["page"] == page)
            t = time.perf_counter()
            error = None
            try:
                if not cache_matches:
                    raise ValueError("cache_image_or_page_mismatch")
                gray = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                if gray is None:
                    raise ValueError("image_decode_failed")
                decoded = time.perf_counter()
                candidates = extract(gray)
                extracted = time.perf_counter()
                image_size = list(gray.shape[::-1])
            except (ValueError, cv2.error) as exc:
                candidates, image_size = [], None
                decoded = extracted = time.perf_counter()
                error = str(exc)
            reasons = review_reasons(candidates, signals)
            if error:
                reasons.append("extraction_error")
            if not cache_matches:
                reasons.append("cache_image_or_page_mismatch")
            for candidate_index, candidate in enumerate(candidates, 1):
                candidate.update(candidate_id=f"{source}:{page:04d}:{candidate_index}", source_id=source,
                                 pdf_page=page, image_sha256=image_sha)
            records[page] = {"source_id": source, "pdf_page": page, "image_path": str(path.resolve()),
                             "image_sha256": image_sha, "image_size": image_size, "cache_sha256": cache_sha,
                             "pdf_sha256": cache["canonical"]["provenance"].get("original_pdf_sha256") if cache_matches else None,
                             "cache_matches_image_and_page": cache_matches,
                             "algorithm_version": VERSION, "algorithm_sha256": code_sha,
                             "coordinate_system": "original_image_pixels_xyxy_top_left",
                             "approved": False, "needs_review": bool(reasons), "review_reasons": reasons,
                             "chart_text_signals": signals, "candidates": candidates, "error": error,
                             "decode_seconds": decoded-t, "geometry_seconds": extracted-decoded}
            processed += 1
            if index % 25 == 0:
                write_jsonl(target, [records[p] for p in sorted(records)])
                print(json.dumps({"source_id": source, "snapshot_pages": len(paths), "through_page": page,
                                  "processed_this_run": processed, "skipped_this_run": skipped}), flush=True)
        write_jsonl(target, [records[p] for p in sorted(records)])
    all_records = [json.loads(line) for p in args.output.glob("*.jsonl")
                   if p.name != "needs_review_pages.jsonl" for line in p.read_text(encoding="utf-8").splitlines()]
    reviews = [{"source_id": r["source_id"], "pdf_page": r["pdf_page"], "image_path": r["image_path"],
                "image_sha256": r["image_sha256"], "algorithm_sha256": r["algorithm_sha256"],
                "candidate_count": len(r["candidates"]), "review_reasons": r["review_reasons"],
                "chart_text_signals": r["chart_text_signals"]} for r in all_records if r["needs_review"]]
    write_jsonl(args.output/"needs_review_pages.jsonl", reviews)
    diagnostics = {"algorithm_version": VERSION, "algorithm_sha256": code_sha, "approved": False,
                   "snapshot_page_counts": {s: len(ps) for s, ps in selected.items()},
                   "processed_this_run": processed, "skipped_unchanged_this_run": skipped,
                   "stored_pages": len(all_records), "candidate_count": sum(len(r["candidates"]) for r in all_records),
                   "paired_count": sum(c["kind"] == "paired" for r in all_records for c in r["candidates"]),
                   "primary_only_count": sum(c["kind"] == "primary_only" for r in all_records for c in r["candidates"]),
                   "needs_review_pages": len(reviews),
                   "zero_candidate_signal_pages": sum("zero_candidates_with_chart_text_signals" in r["review_reasons"] for r in reviews),
                   "zero_candidate_without_text_pages": sum("zero_candidates_without_text_evidence" in r["review_reasons"] for r in reviews),
                   "cache_mismatch_pages": sum("cache_image_or_page_mismatch" in r["review_reasons"] for r in reviews),
                   "extraction_error_pages": sum(r["error"] is not None for r in all_records),
                   "stored_other_algorithm_pages": sum(r["algorithm_sha256"] != code_sha for r in all_records),
                   "run_seconds": time.perf_counter()-started,
                   "scope": "Machine candidates for visual review; no canonical text/DB edits or automatic acceptance. Rerun for new cached pages."}
    (args.output/"diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(diagnostics, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
