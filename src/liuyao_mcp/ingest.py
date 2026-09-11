"""Deterministic source import. Uncertain extraction remains visible in JSON."""
import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .chart import BRANCHES, STEMS, HEXAGRAMS, PALACES, PALACE_ELEMENT, line_data, build_chart, calendar_values
from .common import case_search_text, digest, dumps, normalized, plain, project_root, tokens, topic_of
from .outline import OUTLINE_SCHEMA, build_outline, catalog_text, evidence_navigation, index_text, node_at, store_outline
from .taxonomy import SCHEMA as TAXONOMY_SCHEMA, classify, classify_rule, nodes as topic_nodes
from .proofreading import SCHEMA as PROOFREADING_SCHEMA, apply as apply_corrections, correction_text, store as store_corrections

PARSER_VERSION = "source-parser-0.7"
SEARCH_INDEX_VERSION = 'manual-quality-1'
PAGE = re.compile(r"=+ PDF 第 (\d+) 页 / 共 (\d+) 页 =+")
DATE = re.compile(rf"([{BRANCHES}])月.{{0,10}}?([{STEMS}][{BRANCHES}])日")
ROW = re.compile(rf"(父母|兄弟|子孙|妻财|官鬼)[{STEMS}]?([{BRANCHES}])[木火土金水]?")
GRAPHIC = re.compile(r"[▅▄━]{2,}(?:[ \t　]+[▅▄━]{2,})?")
CHART_HEADER = re.compile(r"^[\s>“”‘’\"'「」『』:：,，。．·、]*(主变)")
CHAPTER = re.compile(r"^(?:#{1,6}\s+|第[一二三四五六七八九十百\d]+[章节]\s*|[一二三四五六七八九十]+、|.{1,35}[章节]第[一二三四五六七八九十百\d—]+$)")
SUBSECTION = re.compile(
    r"^([（(][一二三四五六七八九十百\d]+[)）]\s*[^：:。；;！？\n]{1,35}(?=[:：]|$)"
    r"|(?:[一二三四五六七八九十百\d]+[、.．]\s*)?(?:父母|官鬼|兄弟|妻财|子孙)(?:爻(?:的?含义)?|的?含义)(?=[:：；;]))")
CAST_NAMES = '|'.join(sorted({h[key] for h in HEXAGRAMS.values() for key in ('name', 'full_name')}, key=lambda name: (-len(name), name)))
FULL_CAST_NAMES = '|'.join(sorted({h['full_name'] for h in HEXAGRAMS.values()}, key=lambda name: (-len(name), name)))
NATIVE_CAST = re.compile(
    rf"(?:占得|得)(?:到|出)?[“\"「]?(?:(?:{CAST_NAMES}|[天地水火山泽雷风]{{2}}[\u4e00-\u9fff]{{1,3}})[”\"」]?(?:卦|之|变|化|(?=[，,。；;：:]|$))"
    rf"|(?![一此本某]卦)(?:(?!得|之|变|化)[\u4e00-\u9fff]){{1,3}}[”\"」]?(?:卦|(?:之|变|化)(?=[“\"「]?(?:{CAST_NAMES}))))"
    rf"|(?:{FULL_CAST_NAMES})(?:之|变|化)")
QUESTION_DATE = re.compile(rf"[{BRANCHES}]月.{{0,10}}?(?:[{STEMS}]?[{BRANCHES}]日|[{STEMS}][{BRANCHES}](?=[占测问]))")
RELATIVES = r"父母|兄弟|子孙|妻财|官鬼"
YONGSHEN_LABEL = rf"(?:{RELATIVES})(?:爻)?(?:[{STEMS}]?[{BRANCHES}][木火土金水]?)?(?:爻)?"
YONGSHEN_SELECTION = rf"{YONGSHEN_LABEL}(?:(?:、|和|及|与|或)?{YONGSHEN_LABEL})*"
YONGSHEN = re.compile(rf"(?:以|取)?({YONGSHEN_SELECTION})(?:为用神|为用|作(?:为)?用神)|用神(?:为|是)({YONGSHEN_SELECTION})")
YONGSHEN_COMPLEMENT = re.compile(r"\s*(?:(?:[之的]\s*)?(?:墓库|墓地|元神|原神|忌神|仇神)|[之的]\s*墓)")
OUTCOME = re.compile(r"(?:卦主反馈|反馈\s*[:：，,]|(?:^|[。！？])\s*(?:结果|果于|果然|后果|后验))")
NO_FEEDBACK = re.compile(r"(?:暂无|尚无|没有|未收到|尚未收到|未有|未见)反馈|反馈\s*[:：]\s*(?:(?:暂无|没有|尚无)(?:反馈)?(?=$|[。；;，,\s])|待补|未提供)|(?:尚未|暂未|未)反馈")
AUTHORS = {"liuyao_zixiu_dxj": "王虎应", "zengshan_pingshi_dxj": "王虎应（含原注）", "zengshan_buyi": "野鹤老人等（整理版）"}


def background_heading(title):
    title = re.sub(r"\s+", "", plain(title).lstrip("# "))
    title = re.sub(r"^第[一二三四五六七八九十百\d]+[章节]", "", title)
    # Only explicit section titles establish this role, never topic words in prose.
    return bool(re.fullmatch(r"序言|前言|自序|后记|六爻预测和我们的生活|知微易学会六爻段位表|学员感悟[〈《（(]*[一二三四五六七八九十\d]*[)）〉》]*", title))


def author_yongshen(lines, indices):
    """Literal author choices with exact offsets; never choose a line from outcomes."""
    evidence = []
    for i in indices:
        for sentence in re.finditer(r"[^。！？；;]+[。！？；;]?", lines[i]):
            text = sentence[0]
            if OUTCOME.search(text):
                continue
            for match in YONGSHEN.finditer(text):
                if re.search(r"(?:不|非|未|莫)\s*$", text[:match.start()]):
                    continue
                if YONGSHEN_COMPLEMENT.match(text, match.end()):
                    continue
                for relative in dict.fromkeys(re.findall(RELATIVES, match[1] or match[2])):
                    evidence.append({"relative": relative, "quote": match[0],
                                     "source_spans": [{"start_line": i+1, "end_line": i+1}],
                                     "start_char": sentence.start()+match.start(),
                                     "end_char": sentence.start()+match.end()})
    return list(dict.fromkeys(e["relative"] for e in evidence)), evidence


def chart_only(text):
    """Only explicit chart cells qualify; any narrative keeps the unit searchable."""
    has_row = False
    for line in text.splitlines():
        row = plain(line).strip('> ')
        if not row:
            continue
        if re.fullmatch(r'【卦象结构化[^】]*】', row):
            continue
        if CHART_HEADER.match(row):
            cells = re.sub(CAST_NAMES, '', CHART_HEADER.sub('', row))
            cells = re.sub(r'本宫|游魂|归魂|六冲|六合|空亡|旬空|卦|宫|之|变', '', cells)
            if re.fullmatch(rf'[\W\d{STEMS}{BRANCHES}一二三四五六]*', cells):
                continue
        if re.fullmatch(r'[|: +\-]+', row) or re.fullmatch(r'\|?\s*(?:爻位|六神|伏神|本卦|主卦|动爻|变卦)(?:[\s|]+(?:爻位|六神|伏神|本卦|主卦|动爻|变卦))*[\s|]*', row):
            continue
        if re.fullmatch(r'(?:上|五|四|三|二|初)爻\s+[━▅▄○Ｏ×ＸXOxo′″〃→\s]+', row):
            has_row = True
            continue
        cells = re.sub(rf'青龙|朱雀|勾陈|[腾螣呈]蛇|白虎|玄武|伏神|{RELATIVES}|[{STEMS}{BRANCHES}木火土金水世应伏动爻]', '', row)
        if ROW.search(row) and symbol_value(row) is not None and re.fullmatch(r'[\s|:：()（）\[\]、━▅▄○Ｏ×ＸXOxo′″〃→\-]*', cells):
            has_row = True
            continue
        return False
    return has_row


def spans_of(indices):
    spans = []
    for i in sorted(set(indices)):
        if spans and spans[-1]["end_line"] == i:
            spans[-1]["end_line"] = i + 1
        else:
            spans.append({"start_line": i + 1, "end_line": i + 1})
    return spans


def read_spans(lines, spans):
    parts = []
    for span in spans:
        selected = lines[span['start_line']-1:span['end_line']]
        if selected:
            start, end = span.get('start_column', 0), span.get('end_column')
            if len(selected) == 1:
                selected[0] = selected[0][start:end]
            else:
                selected[0] = selected[0][start:]
                selected[-1] = selected[-1][:end]
        parts.append('\n'.join(selected))
    return '\n'.join(parts)


def symbol_value(text):
    if "×" in text or "Ｘ" in text or re.search(r"(?<![A-Za-z])[Xx](?![A-Za-z])", text):
        return 0
    if "○" in text or "Ｏ" in text or re.search(r"(?<![A-Za-z])O(?![A-Za-z])", text):
        return 3
    if re.search(r"━━\s+━━|[▅▄]{2}\s+[▅▄]{2}|″|〃", text):
        return 2
    if "━━━━" in text or "▅▅▅▅▅" in text or "▄▄▄▄▄" in text or "′" in text:
        return 1
    return None


def name_in(text):
    matches = [(text.find(h["full_name"]), h["name"]) for h in HEXAGRAMS.values() if h["full_name"] in text]
    for match in re.finditer(r"(?:得|变|之)[“\"「]?([乾兑离震巽坎艮坤])卦", text):
        matches.append((match.start(1), match[1]))
    # Some classics use short names: 得复之震. Restrict to explicit quoted names.
    if not matches:
        m = re.search(r"得[“\"「]?([\u4e00-\u9fff]{1,3})[”\"」]?(?:之|变)[“\"「]?([\u4e00-\u9fff]{1,3})", text)
        if m:
            names = {h["name"] for h in HEXAGRAMS.values()}
            matches = [(m.start(i), m[i].removesuffix("卦")) for i in (1, 2) if m[i].removesuffix("卦") in names]
    return [name for _, name in sorted(set(matches))]


def reported_names(header):
    chart_header = next((re.sub(r"^.*?主变.", "", line) for line in header.splitlines() if CHART_HEADER.match(plain(line))), None)
    if chart_header is not None:
        parts = re.split(r"[之变]", chart_header, maxsplit=1)
        # An unreadable primary name must not shift the recognized changed name left.
        return [next(iter(name_in(part)), None) for part in parts]
    return name_in(header)


def ocr_primary_row(row):
    if GRAPHIC.search(row):
        return native_row(row, symbols_before=True)[0]
    first = re.search(r"父母|兄弟|子孙|妻财|官鬼", row)
    if first and first.start() < len(row)/2:
        return ROW.match(row, first.start())
    return None


def native_row(row, symbols_before=None):
    """Choose the symbol-bearing main line, excluding a preceding hidden line."""
    matches = list(ROW.finditer(row))
    graphics = list(GRAPHIC.finditer(row))
    if symbols_before is None:
        symbols_before = bool(graphics and matches and graphics[0].start() < matches[0].start())
    if symbols_before and graphics:
        segment_end = graphics[1].start() if len(graphics) > 1 else len(row)
        m = ROW.search(row, graphics[0].end(), segment_end)
        if m:
            return m, symbol_value(row[graphics[0].start():segment_end])
    for i, m in enumerate(matches):
        suffix = row[m.end():matches[i+1].start() if i+1<len(matches) else len(row)]
        value = symbol_value(suffix)
        if value is None:
            dots = re.match(r"[\s*]*(、、|、)", suffix)
            if dots:
                value = 2 if dots[1] == "、、" else 1
        if value is not None:
            if "动" in suffix and value in (1, 2):
                value = 3 if value == 1 else 0
            return m, value
    # A missing branch label does not erase an explicitly printed yin/yang symbol.
    short = re.fullmatch(r"\s*(?:父母|兄弟|子孙|妻财|官鬼)[木火土金水]?([′″○×XO])\s*", plain(row))
    return None, symbol_value(short[1]) if short else None


def native_panels(lines, cutoff):
    """Six adjacent source rows establish a display, even with split headers."""
    panels, pending = [], []
    def flush():
        if len(pending) in (5, 6):
            before = sum(bool(GRAPHIC.search(row) and ROW.search(row)) and GRAPHIC.search(row).start() < ROW.search(row).start()
                         for _, row in pending) >= 3
            panels.append((list(pending), before))
        pending.clear()
    for i, line in enumerate(lines[:cutoff]):
        row = plain(line).lstrip("> ")
        if not row or PAGE.search(row) or re.fullmatch(r"[|: +\-]+", row):
            continue
        if len(row) < 160 and (native_row(row)[1] is not None or
                              (ROW.search(row) and not re.search(r"[，。；：！？]", row))):
            pending.append((i, line.strip()))
        else:
            flush()
    flush()
    return panels


def ocr_chart_rows(lines, start, end, diagram_lines):
    rows = []
    for i in range(start, min(start+55, end)):
        row = lines[i].strip()
        if i in diagram_lines or not row or PAGE.search(row) or row.isdigit():
            continue
        if CHART_HEADER.match(plain(row)) or re.match(r'^求测人|^占问事宜', row):
            break
        if len(row) < 140 and re.search(r"图|国|田|轿|轩|[▅━]|青龙|朱[雀徐党逢]|勾陈|[腾螣]蛇|白虎|玄武", row) and not re.match(r"^(?:测|本卦|反馈|在此|这是|所以|说明)", row):
            rows.append((i, row))
            if len(rows) == 6:
                break
        elif rows or len(row) > 120:
            break
    return rows


def diagram_evidence(values, names, rows):
    """Compare only printed names/labels; no calendar is invented for matching."""
    bits = sum((v % 2) << i for i, v in enumerate(values))
    changed = bits ^ sum(1 << i for i, v in enumerate(values) if v in (0, 3))
    palace, shi, _ = PALACES[bits]
    primary = line_data(bits, PALACE_ELEMENT[palace])
    changed_lines = line_data(changed, PALACE_ELEMENT[palace])
    issues, evidence = [], 0
    for reported, actual in zip(names, (HEXAGRAMS[bits]['name'], HEXAGRAMS[changed]['name'])):
        if reported:
            evidence += 1
            if reported != actual:
                issues.append('reported_hexagram_name_conflict')
    for position, (_, row) in enumerate(reversed(rows if len(rows) == 6 else []), 1):
        match = ocr_primary_row(row)
        if match:
            evidence += 1
            if (match[1], match[2]) != (primary[position-1]['relative'], primary[position-1]['branch']):
                issues.append(f'reported_line_{position}_najia_conflict')
            marker = re.match(r"[\s′″〃○Ｏ×ＸXxOo━▅▄、*“”\"']*(世|应)", row[match.end():])
            if marker and position != (shi if marker[1] == '世' else (shi+2) % 6+1):
                issues.append(f'reported_line_{position}_shi_ying_conflict')
            right = ROW.search(row, match.end())
            if right and ROW.search(row, right.end()) is None:
                evidence += 1
                if (right[1], right[2]) != (changed_lines[position-1]['relative'], changed_lines[position-1]['branch']):
                    issues.append(f'reported_changed_line_{position}_najia_conflict')
    return evidence, issues


def native_question(header_lines, anchor):
    """Keep the question sentence; long theory and reported results stay in source."""
    for line in header_lines:
        explicit = re.search(r"(?:占问事宜|占事|求测内容|所占事宜)[\s:：;；，,]+(.*)", plain(line))
        if explicit:
            return explicit[1].strip() or None
    candidates = [plain(line) for line in header_lines if re.search(r"占|测|问|[?？]", plain(line))
                  and not re.match(r"^(?:起卦方式|六神|主变卦|神煞)", plain(line))]
    # The final question before the display is more specific than an earlier preface.
    question = candidates[-1] if candidates else plain(anchor)
    same_header = plain(anchor) in candidates
    long_header = len(question) > 180
    cast = NATIVE_CAST.search(question)
    if cast:
        question = question[:cast.start()]
    sentences = re.findall(r"[^。！？?]+[。！？?]?", question)
    concrete = [s for s in sentences if re.search(r"(?:占|测|判断)(?!得|之|者|一卦|卦|[，,。；;：:\s]|$).|问[：:,，]?(?![。；;\s]|$).", s.rstrip('。'))]
    dated = [s for s in sentences if QUESTION_DATE.search(s) and (s in concrete or re.search(r'[?？]', s))]
    question = (dated[-1] if same_header and dated else concrete[0] if same_header and concrete else sentences[0] if sentences else '')
    date = QUESTION_DATE.search(question)
    if long_header and date and re.search(r'[占测问]', question[date.end():]):
        question = question[date.start():]
    explicit_question = bool(date and re.search(r'[?？]', question))
    question = question.strip().rstrip(" ，,。；;：:！？?")
    return question if explicit_question or re.search(r"占|测|问|判断|病|股票|大盘", question) else None


def extract_cases(source, lines, pages, cutoff, outline_boundaries=None):
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
        chart_header = bool(CHART_HEADER.match(plain(line)))
        if chart_header or (DATE.search(plain(line)) and re.search(r"[占测].*(?:得|之)|得.*卦", plain(line))):
            # Generic theory without a nearby six-line display is not an event.
            nearby = [l for l in lines[i+1:min(i+65, cutoff)] if l.strip()]
            if chart_header or sum(bool(ROW.search(l)) and symbol_value(l) is not None for l in nearby[:15]) >= 5:
                anchors.append(i)
    native_displays, native_starts = {}, {}
    if source["source_type"] == "native_text":
        legacy_anchors = set(anchors)
        anchors = []
        previous_end = 0
        for rows, before in native_panels(lines, cutoff):
            first = rows[0][0]
            context = [i for i in range(max(previous_end, first-70), first) if lines[i].strip()][-16:]
            last_heading = next((i for i in reversed(context) if CHAPTER.match(lines[i].strip()) and len(plain(lines[i])) < 110), None)
            if last_heading is not None:
                context = [i for i in context if i > last_heading]
            candidates = [i for i in context if i in legacy_anchors or DATE.search(plain(lines[i]))
                          or re.search(rf"[{STEMS}][{BRANCHES}]日.*[占测问]|[占测问].*得[^。；;]+|^同日.*[占测问]", plain(lines[i]))]
            if candidates:
                old = [i for i in candidates if i in legacy_anchors]
                a = old[-1] if old else candidates[-1]
                anchors.append(a)
                native_displays[a] = (rows, before)
                earlier = [i for i in context if i <= a and re.search(r"占问事宜|占事|求测内容|[占测问]|[?？]", plain(lines[i]))
                           and (i == a or len(plain(lines[i])) < 250) and not OUTCOME.search(lines[i])]
                native_starts[a] = earlier[-1] if earlier else a
            previous_end = rows[-1][0] + 1
    anchors = sorted(set(anchors))
    ocr_displays = {a: ocr_chart_rows(lines, a+1, anchors[i+1] if i+1 < len(anchors) else cutoff, all_diagram_lines)
                    for i, a in enumerate(anchors)} if source['source_type'] == 'ocr_text' else {}
    assigned, diagram_matches = {}, {}
    for a, rows in ocr_displays.items():
        table_pages = sorted({pages[i] for i, _ in rows if pages[i] is not None})
        candidates = diagrams.get(table_pages[0], []) if len(table_pages) == 1 else []
        checked, compatible = [], []
        for d in candidates:
            evidence, conflicts = diagram_evidence(d['values'], reported_names(lines[a]), rows) if d['values'] else (0, ['unreadable_diagram'])
            checked.append({'start_line': d['start']+1, 'end_line': d['end'], 'label_evidence_count': evidence, 'conflicts': conflicts})
            if evidence and not conflicts:
                compatible.append(d)
        if len(compatible) == 1:
            assigned[a] = compatible[0]
        diagram_matches[a] = {'basis': 'actual_chart_rows_pdf_page_and_explicit_labels', 'table_pages': table_pages,
                              'candidates': checked, 'status': 'matched' if a in assigned else 'ambiguous' if compatible else 'conflict' if any(c['conflicts'] for c in checked) else 'insufficient_evidence' if checked else 'missing'}
    uses = Counter(d['start'] for d in assigned.values())
    for a, d in list(assigned.items()):
        if uses[d['start']] > 1:
            del assigned[a]
            diagram_matches[a]['status'] = 'ambiguous'

    starts = []
    for ai, a in enumerate(anchors):
        floor = anchors[ai-1]+1 if ai else 0
        metadata = [i for i in range(max(floor, a-30), a+1) if re.match(r"^求测人", lines[i].strip())]
        start = metadata[-1] if metadata else a
        start = min(start, native_starts.get(a, a))
        if not metadata:
            for i in range(max(floor, a-8), a):
                if re.match(r"^\**例[一二三四五六七八九十\d]", lines[i].strip()):
                    start = i
                    break
            if start == a:
                questions = [i for i in range(max(floor, a-12), a) if "占问事宜" in lines[i]]
                if questions:
                    start = questions[-1]
        starts.append(start)

    cases = []
    protected_lines = set(all_diagram_lines)
    for ai, (a, start) in enumerate(zip(anchors, starts)):
        next_start = starts[ai+1] if ai+1 < len(starts) else cutoff
        next_start = next((i for i in range(a+1, next_start) if re.match(r"^求测人", lines[i].strip())), next_start)
        heading = next((i for i in range(a+1, next_start) if
                        (i in outline_boundaries if outline_boundaries is not None else
                         CHAPTER.match(lines[i].strip()) and not lines[i].startswith("【"))), next_start)
        end = min(next_start, heading, a+220)
        ds = assigned.get(a)
        indices = [i for i in range(start, end) if i not in all_diagram_lines]
        if ds:
            indices += list(range(ds["start"], ds["end"]))
        spans = spans_of(indices)
        raw = read_spans(lines, spans)
        narrative = "\n".join(lines[i] for i in range(start, end) if i not in all_diagram_lines and not PAGE.search(lines[i]))
        native_display = native_displays.get(a)
        header_end = native_display[0][0][0] if native_display else a+1
        header_lines = lines[start:header_end]
        question = next((re.sub(r"^.*?占问事宜[\s:：;；，,]*", "", line).strip() for line in header_lines if "占问事宜" in line), plain(lines[a]))
        if not question or CHART_HEADER.match(question):
            question = next((plain(line) for line in header_lines if "占" in line or "测" in line), None)
        if source["source_type"] == "native_text":
            question = native_question(header_lines, lines[a])
        header = "\n".join(header_lines)
        date_match = DATE.search(plain(header))
        day_match = re.search(rf"([{STEMS}][{BRANCHES}])日", header)
        month_match = re.search(rf"([{BRANCHES}])月", header)
        date = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", header)
        date_text = f"{int(date[1]):04}-{int(date[2]):02}-{int(date[3]):02}" if date else None
        time_match = re.search(r"日\s*(\d{1,2})\s*时\s*(\d{1,2})\s*分", header)
        time_text = f"{int(time_match[1]):02}:{int(time_match[2]):02}:00" if time_match else None
        values = ds["values"] if ds else None
        pan_rows = list(native_display[0]) if native_display else ocr_displays.get(a, [])
        symbols_before = native_display[1] if native_display else None
        if native_display:
            protected_lines.update(range(pan_rows[0][0], pan_rows[-1][0]+1))
        for i in range(a+1, min(a+55, end)) if not native_display and source['source_type'] != 'ocr_text' else ():
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
            vals = [native_row(row, symbols_before)[1] for _, row in pan_rows]
            if all(v is not None for v in vals):
                values = list(reversed(vals))
                protected_lines.update(range(pan_rows[0][0], pan_rows[-1][0]+1))
        names = reported_names(header)
        void = re.search(r"(?:空亡|旬空)[:：\s]*([^\]）)\n]+)", header)
        issues, calculated = [], None
        month = date_match[1] if date_match else month_match[1] if month_match else None
        day = date_match[2] if date_match else day_match[1] if day_match else None
        calendar_basis = "reported_ganzhi" if month or day else "unknown"
        if any(re.search(r"(?:^|[。；;])\s*同日[，,、]?", plain(line)) for line in header_lines) and cases and (not month or not day):
            month = month or cases[-1]["cast"]["month_branch"]
            day = day or cases[-1]["cast"]["day_ganzhi"]
            calendar_basis = "explicit_same_day_previous_case"
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
        if a in diagram_matches and diagram_matches[a]['status'] == 'conflict':
            issues.append('transcribed_diagram_conflicts_with_reported_chart')
            validation = 'conflict'
        if values and month and day:
            try:
                calculated = build_chart(values, month_branch=month, day_ganzhi=day)
                validation = "calculated"
                if source['source_type'] == 'ocr_text' and len(pan_rows) != 6:
                    issues.append('incomplete_reported_chart_rows')
                if names and names[0] and names[0] != calculated["primary"]["name"]:
                    issues.append("reported_primary_conflicts_with_line_values")
                if len(names) > 1 and names[1] and names[1] != calculated["changed"]["name"]:
                    issues.append("reported_changed_conflicts_with_line_values")
                for position, (_, row) in enumerate(reversed(pan_rows if len(pan_rows) == 6 else []), 1):
                    m = native_row(row, symbols_before)[0] if source["source_type"] == "native_text" else ocr_primary_row(row)
                    if m is None and source["source_type"] == "ocr_text":
                        issues.append(f"unreadable_reported_line_{position}_primary_label")
                    if m and position <= 6 and (m[1], m[2]) != (calculated["lines"][position-1]["relative"], calculated["lines"][position-1]["branch"]):
                        issues.append(f"reported_line_{position}_conflicts_with_najia")
                    # Only an adjacent primary marker is evidence; changed labels may be unreadable.
                    marker = re.match(r"[\s′″〃○Ｏ×ＸXxOo━▅▄、*“”\"']*(世|应)", row[m.end():]) if m else None
                    if marker:
                        role = "shi" if marker[1] == "世" else "ying"
                        if position != calculated[f"{role}_position"]:
                            issues.append(f"reported_line_{position}_{role}_conflicts_with_position")
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
        analysis_indices = [i for i in range(analysis_start, end) if i not in all_diagram_lines and not PAGE.search(lines[i])]
        analysis = "\n".join(lines[i] for i in analysis_indices).strip()
        analysis_spans = spans_of(i for i in analysis_indices if lines[i].strip() and not lines[i].strip().isdigit()) if len(pan_rows) == 6 else []
        if calculated:
            reported_shi = re.findall(r"(?:^|[。；;！？])\s*本卦世爻\s*(父母|兄弟|子孙|妻财|官鬼)", plain(analysis))
            if any(relative != calculated["features"]["shi_relative"] for relative in reported_shi):
                issues.append("reported_primary_shi_relative_conflicts_with_calculated_chart")
                validation = "conflict"
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
        # Damaged chart rows do not erase a literal choice in subsequent author prose.
        yongshen_indices = [i for i in analysis_indices if pan_rows and i > pan_rows[-1][0]]
        yongshen, yongshen_evidence = author_yongshen(lines, yongshen_indices)
        features = dict(calculated["features"]) if calculated and validation != "conflict" else {}
        features.update({"topic": topic_of(question or ""), "yongshen_reported": yongshen or None, "yongshen_basis": "author_text" if yongshen else None, "chart_feature_status": validation})
        if calculated and validation != "conflict" and yongshen:
            candidates = [('primary', line) for line in calculated['lines']]
            candidates += [('hidden', line['hidden']) for line in calculated['lines'] if line['hidden']]
            candidates += [('changed', line['transformation']) for line in calculated['lines'] if line['transformation']]
            features['yongshen_candidates'] = [
                {**{key:line[key] for key in ('position','relative','void','month_break','moving')},
                 'scope':scope, 'selection':'relative_match_not_author_line_selection'}
                for scope,line in candidates if line['relative'] in yongshen]
        case_id = f"case_{source['source_id']}_{a+1}"
        cases.append({
            "schema_version": "0.2", "case_id": case_id, "related_case_ids": [],
            "question": {"raw": question, "topic": features["topic"]},
            "cast": {"date": date_text, "time": time_text, "timezone": None, "calendar_basis": calendar_basis, "month_branch": month, "day_ganzhi": day, "line_values": values, "lines_order": "bottom_to_top", "line_values_basis": "transcribed_diagram" if ds else "native_line_symbols" if values else None},
            "reported_chart": {"raw_header": lines[a], "primary": names[0] if names else None, "changed": names[1] if len(names)>1 else None, "void_raw": void[1] if void else None, "line_text": [row for _, row in pan_rows]},
            "derived": calculated, "features": features,
            "interpretations": [{"source_id": source["source_id"], "author": source.get("author"), "method_hint": source["method_hint"], "yongshen_reported": yongshen or None, "yongshen_evidence": yongshen_evidence, "original_text": analysis, "source_spans": analysis_spans, "source_span_basis": "text_after_six_chart_rows" if len(pan_rows) == 6 else "unresolved_chart_end"}],
            "outcome": {"status": "reported_explicit" if outcomes else "none", "quotes": outcomes, "event_date": None, "event_timing": "before_or_at_cast" if outcomes and re.search(r"已经发生|现状|过去.*发生", analysis) else "unknown", "independently_verified": False},
            "source": {"source_id": source["source_id"], "path": source["path"], "sha256": source["sha256"], "pdf_pages": sorted({pages[i] for i in indices if pages[i] is not None}), "spans": spans, "original_text": raw, "raw_text_normalization": "python_universal_newlines"},
            "extraction": {"method": "deterministic_parser", "pipeline_version": PARSER_VERSION, "status": "partial" if issues else "parsed", "issues": issues, "chart_validation": validation, **({'diagram_match': diagram_matches[a]} if a in diagram_matches else {})},
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
    outline_nodes = build_outline(source, lines, pages, root)
    original_body = text
    source, text = apply_corrections(source, text, root)
    lines = text.splitlines()
    boundaries = {n['start_line']-1: n for n in outline_nodes if n['node_type'] not in ('book', 'front_matter')}
    cases, diagram_lines = extract_cases(source, lines, pages, cutoff, set(boundaries) if outline_nodes else None)
    case_boundaries = {edge for case in cases for span in case['source']['spans']
                       for edge in (span['start_line']-1, span['end_line'])}
    case_source_lines = {i for case in cases for span in case['source']['spans']
                         for i in range(span['start_line']-1, span['end_line'])}
    if outline_nodes:
        for case in cases:
            node = node_at(outline_nodes, int(case['case_id'].rsplit('_', 1)[1]))
            case['outline'] = evidence_navigation(node, outline_nodes)
    reasons, chunks, pending = {}, [], []
    heading_lines = set()
    chapter = source["title"]
    chapter_start = 0
    section = None
    def flush():
        if not pending:
            return
        start, end = pending[0], pending[-1]+1
        body = "\n".join(lines[start:end])
        method = source["method_hint"]
        if method == "mixed":
            method = "xiangfa" if re.search(r"象法|取象|类象|六神", chapter) else "lifa"
        chunk = {"id": f"rule_{source['source_id']}_{start+1}", "source_id": source["source_id"], "kind": "passage", "chapter": chapter, "chapter_start": chapter_start+1, "start_line": start+1, "end_line": end, "pages": sorted({pages[i] for i in pending if pages[i] is not None}), "text": body, "method": method, "content_hash": digest(normalized(body))}
        if section:
            chunk['section'] = section
            chunk['chapter'] = chapter + ' / ' + section['title']
        if outline_nodes:
            node = node_at(outline_nodes, start+1)
            chunk['outline'] = evidence_navigation(node, outline_nodes)
            chunk['chapter'] = ' / '.join(p['title'] for p in node['path'][1:])
            chunk['chapter_start'] = node['start_line']
        chunks.append(chunk)
        pending.clear()
    for i, line in enumerate(lines):
        if i in case_boundaries:
            flush()
        stripped = line.strip()
        reason = None
        if i >= cutoff:
            reason = "validation_copy"
        elif outline_nodes and i+1 < outline_nodes[0]['body_start_line']:
            reason = 'front_matter'
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
        is_background = background_heading(stripped)
        is_heading = i in boundaries if outline_nodes else (CHAPTER.match(stripped) and len(plain(stripped)) < 110) or is_background
        subsection = SUBSECTION.match(plain(stripped)) if source['source_type'] == 'native_text' and i not in case_source_lines else None
        if is_heading and not subsection:
            flush()
            chapter, chapter_start = plain(stripped), i
            section = None
            if CHAPTER.match(stripped) and not re.search(r'[，,。！？!?]|\.$|[:：；;]\s*\S', chapter):
                heading_lines.add(i)
        elif subsection:
            flush()
            section = {'title': subsection[1], 'start_line': i+1,
                       'parent_title': chapter, 'parent_start_line': chapter_start+1,
                       'title_basis': 'source_numbered_subsection' if subsection[1].startswith(('(', '（')) else 'source_relative_definition'}
            if not plain(stripped)[subsection.end():].strip(' :：；;'):
                heading_lines.add(i)
        # Don't split a six-line diagram, or a single long paragraph, for size alone.
        if pending and sum(len(lines[j]) for j in pending) >= 1100 and i not in diagram_lines and (i == 0 or not lines[i-1].strip()):
            flush()
        pending.append(i)
    flush()
    case_lines, case_analysis_lines = set(), set()
    for case in cases:
        classification = classify(case['question']['raw'] or '')
        classification.update(scope='case',basis='question_only')
        if not classification['roots'] and source['method_hint']!='xiangfa':
            anchor=int(case['case_id'].rsplit('_',1)[1])
            chapter=next((c['chapter'] for c in chunks if c['start_line']<=anchor<=c['end_line']), '')
            inherited=classify(chapter)
            if inherited['roots']:
                classification={**inherited, 'topic_ids': list(inherited['roots']),
                                'evidence': [e for e in inherited['evidence'] if '/' not in e['id']],
                                'scope':'case','basis':'chapter_only','chapter_evidence':chapter}
        case['classification'] = classification
        case['question']['topic'] = classification['topic']
        case['features']['topic'] = classification['topic']
        for span in case['source']['spans']:
            case_lines.update(range(span['start_line'],span['end_line']+1))
        for interpretation in case['interpretations']:
            for span in interpretation['source_spans']:
                case_analysis_lines.update(range(span['start_line'], span['end_line']+1))
    for chunk in chunks:
        theory = '\n'.join(lines[i-1] for i in range(chunk['start_line'],chunk['end_line']+1) if i not in case_lines)
        related = [c for c in cases if any(s['start_line'] <= chunk['end_line'] and s['end_line'] >= chunk['start_line']
                                          for s in c['source']['spans'])]
        nearby = [c['question']['raw'] or '' for c in related]
        chunk['content_role'] = 'case_excerpt' if related else 'theory'
        if not related and background_heading(chunk['chapter']):
            chunk['content_role'] = 'background'
        if chart_only(chunk['text']):
            chunk['content_role'] = 'chart_only'
        if chunk['content_role'] == 'theory' and all(i in heading_lines for i in range(chunk['start_line']-1, chunk['end_line']) if lines[i].strip()):
            chunk['content_role'] = 'heading_only'
        chunk['related_case_ids'] = [c['case_id'] for c in related]
        chunk['has_case_analysis'] = any(i in case_analysis_lines for i in range(chunk['start_line'], chunk['end_line']+1))
        classification_chapter = chunk.get('section', {}).get('parent_title', chunk['chapter'])
        chunk['classification'] = classify_rule(classification_chapter,theory,nearby,chunk['method'])
    coverage = set(reasons)
    for chunk in chunks:
        coverage.update(range(chunk["start_line"]-1, chunk["end_line"]))
    if len(coverage) != len(lines):
        raise AssertionError("Unaccounted source lines")
    report = {"source_id": source["source_id"], "sha256": source["sha256"], "total_lines": len(lines), "covered_lines": len(coverage), "page_anchors": page_anchors, "chunks": len(chunks), "cases": len(cases), "case_status": dict(Counter(c["extraction"]["status"] for c in cases)), "chart_validation": dict(Counter(c["extraction"]["chart_validation"] for c in cases)), "excluded_ranges": [{"reason": reason, **span} for reason in sorted(set(reasons.values())) for span in spans_of(i for i, r in reasons.items() if r == reason)]}
    report['outline_nodes'] = outline_nodes
    report['_original_body'] = original_body
    return source, text, chunks, cases, report


SCHEMA = """
CREATE TABLE sources(id TEXT PRIMARY KEY, metadata TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE chunks(id TEXT PRIMARY KEY, source_id TEXT NOT NULL, kind TEXT NOT NULL, method TEXT NOT NULL, chapter TEXT NOT NULL, start_line INT, end_line INT, content_hash TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE cases(id TEXT PRIMARY KEY, source_id TEXT NOT NULL, topic TEXT, method TEXT, duplicate_group TEXT, payload TEXT NOT NULL);
CREATE INDEX case_duplicate_group ON cases(duplicate_group,id);
CREATE TABLE evidence_metadata(
    evidence_id TEXT PRIMARY KEY, kind TEXT NOT NULL, source_id TEXT NOT NULL,
    method TEXT, author TEXT NOT NULL, scope TEXT NOT NULL, root_count INT NOT NULL,
    searchable INT NOT NULL, chart_valid INT NOT NULL, start_line INT, end_line INT,
    group_id TEXT NOT NULL);
CREATE INDEX evidence_scope ON evidence_metadata(kind,scope,root_count,searchable,chart_valid);
CREATE INDEX evidence_group ON evidence_metadata(kind,group_id,evidence_id);
CREATE TABLE case_spans(evidence_id TEXT NOT NULL,source_id TEXT NOT NULL,start_line INT,end_line INT);
CREATE INDEX case_span_evidence ON case_spans(evidence_id);
CREATE INDEX case_span_source ON case_spans(source_id,start_line,end_line);
CREATE TABLE case_features(evidence_id TEXT NOT NULL,key TEXT NOT NULL,selector TEXT NOT NULL,value TEXT NOT NULL,
    PRIMARY KEY(evidence_id,key,selector));
CREATE INDEX feature_cases ON case_features(key,selector,evidence_id);
CREATE TABLE eval_items(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE build_info(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE VIRTUAL TABLE search_index USING fts5(evidence_id UNINDEXED, kind UNINDEXED, focus, body, tokenize='unicode61');
""" + OUTLINE_SCHEMA + TAXONOMY_SCHEMA + PROOFREADING_SCHEMA


def store_search_metadata(connection, kind, record, source):
    """Materialize filters and small feature cells once; source payloads stay intact."""
    case = kind == 'case'
    eid = record['case_id'] if case else record['id']
    classification = record['classification']
    spans = record['source']['spans'] if case else [record]
    quality_eligible = not case or record.get('quality', {}).get('status') == 'eligible'
    searchable = quality_eligible and bool(case_search_text(record).strip()) if case else (
        record.get('content_role') not in ('background', 'chart_only', 'heading_only') and not (
            record.get('content_role') == 'case_excerpt' and record.get('has_case_analysis') is False))
    connection.execute('INSERT INTO evidence_metadata VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (
        eid, kind, source['source_id'], source['method_hint'] if case else record['method'],
        source.get('author') or '', classification['scope'], len(classification['roots']),
        searchable, case and record['extraction']['chart_validation'] == 'calculated',
        spans[0]['start_line'], spans[-1]['end_line'],
        record['duplicate_group'] if case else record['content_hash']))
    if not case:
        return
    connection.executemany('INSERT INTO case_spans VALUES(?,?,?,?)', (
        (eid,source['source_id'],s['start_line'],s['end_line']) for s in spans))
    if not quality_eligible:
        connection.execute("DELETE FROM search_index WHERE evidence_id=? AND kind='case'", (eid,))
        return
    features = dict(record['features'])
    features['yongshen_relative'] = features.get('yongshen_reported')
    special = ('yongshen_void','yongshen_moving','yongshen_month_break','yongshen_scope')
    values = [(eid,key,'',dumps(value)) for key,value in features.items()
              if value is not None and key not in special]
    candidates = features.get('yongshen_candidates', [])
    for selector in {''} | {c['relative'] for c in candidates}:
        related = [c for c in candidates if not selector or c['relative'] == selector]
        if related and all(c.get('scope') for c in related):
            values.append((eid,'yongshen_scope',selector,dumps(sorted({c['scope'] for c in related}))))
        for scope in ('','primary','hidden','changed'):
            selected = [c for c in related if not scope or c.get('scope')==scope]
            if len(selected) == 1:
                scoped_selector = dumps([selector,scope]) if scope else selector
                values.extend((eid,key,scoped_selector,dumps(selected[0][key.removeprefix('yongshen_')]))
                              for key in special if key!='yongshen_scope' and selected[0].get(key.removeprefix('yongshen_')) is not None)
    connection.executemany('INSERT INTO case_features VALUES(?,?,?,?)', values)


def ingest_legacy(root=None, output=None):
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
        connection.executemany('INSERT INTO topics VALUES(?,?,?)',((n['id'],n['parent_id'],n['title']) for n in topic_nodes()))
        for source, text, chunks, cases, report in parsed:
            sid = source["source_id"]
            connection.execute('INSERT INTO original_sources VALUES(?,?)',(sid,report.pop('_original_body')))
            connection.execute("INSERT INTO sources VALUES(?,?,?)", (sid, dumps(source), text))
            for chunk in chunks:
                connection.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?)", (chunk["id"], sid, chunk["kind"], chunk["method"], chunk["chapter"], chunk["start_line"], chunk["end_line"], chunk["content_hash"], dumps(chunk)))
                connection.execute("INSERT INTO search_index VALUES(?,?,?,?)", (chunk["id"], "rule", " ".join(tokens(chunk["chapter"])), " ".join(tokens(chunk["chapter"] + " " + chunk["text"] + ' ' + index_text(chunk.get('outline', {}))))))
            for case in cases:
                group = case["duplicate_group"]
                connection.execute("INSERT INTO cases VALUES(?,?,?,?,?,?)", (case["case_id"], sid, case["question"]["topic"], source["method_hint"], group, dumps(case)))
                # Author judgement/outcome are returned AFTER retrieval, never indexed here.
                search_text = case_search_text(case) + ' ' + index_text(case.get('outline', {}))
                connection.execute("INSERT INTO search_index VALUES(?,?,?,?)", (case["case_id"], "case", " ".join(tokens(case["question"]["raw"] or "")), " ".join(tokens(search_text))))
            store_outline(connection, report['outline_nodes'], chunks, cases)
            for eid,record in [(c['id'],c) for c in chunks]+[(c['case_id'],c) for c in cases]:
                store_search_metadata(connection, 'case' if 'case_id' in record else 'rule', record, source)
                classification=record['classification']
                connection.execute('INSERT INTO evidence_classification VALUES(?,?,?)',
                                   (eid,classification['scope'],dumps(classification)))
                ids=set(classification['topic_ids'])|set(classification['roots'])
                connection.executemany('INSERT INTO evidence_topics VALUES(?,?)',((eid,t) for t in ids))
            reports.append(report)
            all_cases.extend(cases)
        store_corrections(connection,root)
        implementation_hash = digest("".join(Path(__file__).with_name(name).read_text(encoding="utf-8") for name in ("ingest.py", "chart.py", "common.py", "outline.py", "taxonomy.py", "patterns.py", "proofreading.py")) + dumps(json.loads(catalog_text(root))) + dumps(json.loads(correction_text(root))))
        corpus_hash = digest(dumps(manifest) + PARSER_VERSION + implementation_hash)
        connection.execute("INSERT INTO build_info VALUES('corpus_hash',?)", (corpus_hash,))
        connection.execute("INSERT INTO build_info VALUES('parser_version',?)", (PARSER_VERSION,))
        connection.execute("INSERT INTO build_info VALUES('search_index_version',?)",(SEARCH_INDEX_VERSION,))
        connection.execute("INSERT INTO build_info VALUES('implementation_hash',?)", (implementation_hash,))
        connection.commit()
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Database integrity check failed")
    finally:
        connection.close()
    temp.replace(out)
    report = {"parser_version": PARSER_VERSION, "implementation_hash": implementation_hash, "corpus_hash": corpus_hash, "sources": reports, "total_chunks": sum(r["chunks"] for r in reports), "total_cases": len(all_cases), "total_ocr_pages": sum(len(r["page_anchors"]) for r in reports), "limitations": ["OCR correctness unverified", "semantic fields may be partial", "duplicate grouping is conservative and may miss rewrites"]}
    review=json.loads(correction_text(root))
    report['ocr_review']={key:review.get(key,0) for key in ('machine_compared_pages','visually_checked_pages')}
    report['classification']={'topic_roots':sum(n['parent_id'] is None for n in topic_nodes()),
                              'subtopics':sum(n['parent_id'] is not None for n in topic_nodes()),
                              'classified_cases':sum(bool(c['classification']['roots']) for c in all_cases),
                              'unclassified_cases':sum(not c['classification']['roots'] for c in all_cases),
                              'status':'automatic_labels_not_manually_verified'}
    (out.parent / "cases.jsonl").write_text("".join(dumps(c)+"\n" for c in all_cases), encoding="utf-8")
    (out.parent / "ingest_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def ingest(root=None, output=None, *, allow_partial=False):
    """Build exclusively from canonical documents and approved manual slices."""
    from .manual_ingest import build_database
    return build_database(root, output, allow_partial=allow_partial)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=project_root())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-partial", action="store_true", help="Build an explicitly incomplete development corpus")
    args = parser.parse_args()
    report = ingest(args.root, args.output, allow_partial=args.allow_partial)
    print(dumps({k: v for k, v in report.items() if k != "sources"}))


if __name__ == "__main__":
    main()
