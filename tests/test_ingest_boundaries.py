"""Regression excerpts from local books; these fixtures are never corpus inputs."""
import hashlib
import json

from liuyao_mcp.common import project_root
from liuyao_mcp.ingest import import_source, native_row, ocr_primary_row, read_spans, reported_names, symbol_value


# 增删卜易.doc.md, original lines 4418-4450 (blank lines compacted).
MARRIAGE = """卯月乙丑日占求婚成否
子孙巳火′ 动 父母子水″应
妻财未土″世 动 妻财戌土′
官鬼酉金′ 动 官鬼申金″
妻财辰土″ 兄弟卯木″世
兄弟寅木″应 子孙巳火″
父母子水′ 动 妻财未土″

断曰：财爻持世化进神，巳火子动而生世，但因巳火化子水回头之克，必待午日冲去子水，午火又合世爻，其婚必成，果于午日允婚。
"""

# 王虎应增删卜易评释（dxj整理）.doc.md, original lines 3362-3398.
LAWSUIT = """例二，克处逢生
同日，妹占兄官事，同此一案，亦拟重罪，得天地否变天水讼。
卯月戊辰日
父母戌土′应
兄弟申金′
官鬼午火′
妻财卯木″世
官鬼巳火× 父母辰土
父母未土″

申金兄爻为用神，巳火鬼动，刑克申金，重罪定矣。幸喜辰日冲动戌土父母，暗动生申，克处逢生，若有父母可以救之，后因父年八旬，援例恩留免死。
"""

# External 001 DXJ整理版 六爻与股票.docx.md, lines 1066-1122.
STOCK = """出生年：年性别：男占事：2006.5测煤炭类股票走势
起卦方式：手工指定
公历时间：2006年5月23日14时7分星期二
干支：丙戌年癸巳月壬子日丁未时　(旬空：寅卯)
坤宫：地雷复（六合）
六神　伏神　【本卦】
白虎　▅▅　▅▅　子孙癸酉金
螣蛇　▅▅　▅▅　妻财癸亥水
勾陈　▅▅　▅▅　兄弟癸丑土　应
朱雀　▅▅　▅▅　兄弟庚辰土
青龙　父母乙巳火　▅▅　▅▅　官鬼庚寅木
玄武　▅▅▅▅▅　妻财庚子水　世
"""


def parse(tmp_path, text):
    blob = text.encode("utf8")
    (tmp_path / "book.md").write_bytes(blob)
    source = dict(source_id="test_book", path="book.md", title="原文格式回归", source_type="native_text",
                  method_hint="mixed", pdf_pages=None, sha256=hashlib.sha256(blob).hexdigest())
    return import_source(source, tmp_path)


def test_split_headers_prefix_symbols_and_hidden_line(tmp_path):
    _, text, _, cases, _ = parse(tmp_path, STOCK)
    assert len(cases) == 1
    case = cases[0]
    assert case["question"]["raw"] == "2006.5测煤炭类股票走势"
    assert case["cast"]["line_values"] == [1, 2, 2, 2, 2, 2]
    assert case["cast"]["month_branch"] == "巳" and case["cast"]["day_ganzhi"] == "壬子"
    assert case["reported_chart"]["primary"] == "复"
    assert case["extraction"]["chart_validation"] == "calculated"
    assert read_spans(text.splitlines(), case["source"]["spans"]) == case["source"]["original_text"]
    row, value = native_row("青龙　父母乙巳火　▅▅　▅▅　官鬼庚寅木", symbols_before=True)
    assert (row[1], row[2], value) == ("官鬼", "寅", 2)
    assert symbol_value("世O->") == 3 and symbol_value("X应") == 0
    assert native_row("青龙 ▄▄ ▄▄ 父母癸丑土")[1] == 2
    assert native_row("妻财子水、、应")[1] == 2
    assert native_row("兄弟戌土、 白虎")[1] == 1
    assert native_row("妻财木′") == (None, 1)


def test_adjacent_cases_do_not_share_rule_chunks_or_questions(tmp_path):
    _, _, chunks, cases, report = parse(tmp_path, MARRIAGE + "\n" + LAWSUIT + "\n反伏章第二十五\n卦有卦变，爻有爻变。\n")
    assert len(cases) == 2
    first, second = cases
    assert first["question"]["raw"] == "卯月乙丑日占求婚成否"
    assert first["cast"]["line_values"] == [3, 2, 2, 3, 0, 3]
    assert second["question"]["raw"] == "同日，妹占兄官事，同此一案，亦拟重罪"
    assert second["cast"]["day_ganzhi"] == "戊辰"
    assert second["reported_chart"]["primary"] == "否" and second["reported_chart"]["changed"] == "讼"
    assert "妹占兄官事" not in first["source"]["original_text"]
    assert "反伏章第二十五" not in second["source"]["original_text"]
    assert all(len(chunk["related_case_ids"]) <= 1 for chunk in chunks)
    assert chunks[-1]["content_role"] == "theory"
    assert report["covered_lines"] == report["total_lines"]
    assert all(not case["outcome"]["independently_verified"] for case in cases)
    _, _, _, quoted, _ = parse(tmp_path, "\n>\n".join("> " + line for line in MARRIAGE.splitlines()))
    assert len(quoted) == 1 and quoted[0]["cast"]["line_values"] == first["cast"]["line_values"]


def test_question_omits_theory_prefix_and_preserves_conflicts(tmp_path):
    # 增删卜易.doc.md line 3358 embeds this cast at the end of a theory paragraph.
    theory = "占功名者，用爻旺相，迁而又行往他处，去而仍复来。" * 9
    source = theory + "如卯月壬申日占随官府上任。得比之井\n" + "\n".join(MARRIAGE.splitlines()[1:])
    _, _, _, cases, _ = parse(tmp_path, source)
    assert len(cases) == 1
    case = cases[0]
    assert case["question"]["raw"] == "卯月壬申日占随官府上任"
    assert case["source"]["original_text"].startswith(theory)
    assert case["cast"]["line_values"] == [3, 2, 2, 3, 0, 3]
    assert case["extraction"]["chart_validation"] == "conflict"
    assert "reported_primary_conflicts_with_line_values" in case["extraction"]["issues"]
    assert "void_positions" not in case["features"]


def test_undated_following_cast_is_separate_and_only_explicit_same_day_inherits(tmp_path):
    rows = "\n".join(MARRIAGE.splitlines()[1:7])
    for header, month, day in [("占文书得泽火革", None, None),
                               ("旧存占验丙申日占文书", None, "丙申"),
                               ("同日，妹占文书得泽火革", "卯", "乙丑"),
                               ("例二，另占\n同日，妹占文书得泽火革", "卯", "乙丑")]:
        _, _, _, cases, _ = parse(tmp_path, MARRIAGE + "\n" + header + "\n" + rows + "\n断曰：以父母爻为用神。")
        assert len(cases) == 2
        first, second = cases
        assert "占文书" not in first["source"]["original_text"]
        assert first["features"]["yongshen_reported"] is None
        assert second["features"]["yongshen_reported"] == ["父母"]
        assert (second["cast"]["month_branch"], second["cast"]["day_ganzhi"]) == (month, day)
        if month is None:
            assert second["derived"] is None
            assert "missing_valid_month_or_day" in second["extraction"]["issues"]


def test_explicit_primary_markers_and_affirmative_shi_claims_flag_conflicts(tmp_path):
    bad_marker = MARRIAGE.replace("妻财未土″世 动", "妻财未土″应 动")
    _, _, _, cases, _ = parse(tmp_path, bad_marker)
    assert "reported_line_5_ying_conflicts_with_position" in cases[0]["extraction"]["issues"]
    assert cases[0]["extraction"]["chart_validation"] == "conflict"
    for claim, conflict in [("本卦世爻子孙酉金。", True), ("若本卦世爻子孙酉金，则另论。", False),
                            ("本卦世爻并非子孙。", False), ("变卦世爻子孙酉金。", False)]:
        _, _, _, cases, _ = parse(tmp_path, MARRIAGE + claim)
        assert ("reported_primary_shi_relative_conflicts_with_calculated_chart" in cases[0]["extraction"]["issues"]) is conflict
        if conflict:
            assert "shi_relative" not in cases[0]["features"]


def test_actual_ocr_boundaries_and_conflicting_transcription(monkeypatch):
    # Exercise the raw transcription independently of subsequently verified overlays.
    monkeypatch.setattr("liuyao_mcp.ingest.apply_corrections", lambda source, text, root: (source, text))
    root = project_root()
    source = next(json.loads(line) for line in (root / "data/sources.jsonl").read_text(encoding="utf8").splitlines()
                  if json.loads(line)["source_id"] == "liuyao_lifa_jinjie")
    _, _, chunks, cases, _ = import_source(source, root)
    by_case = {case["case_id"]: case for case in cases}
    previous_feedback = next(chunk for chunk in chunks if chunk["id"] == "rule_liuyao_lifa_jinjie_4994")
    assert previous_feedback["end_line"] == 4995
    assert previous_feedback["related_case_ids"] == ["case_liuyao_lifa_jinjie_4971"]
    assert "面试能否被录用" not in previous_feedback["text"]
    assert all(len(chunk["related_case_ids"]) <= 1 for chunk in chunks)
    spaced_date = by_case["case_liuyao_lifa_jinjie_5853"]
    assert spaced_date["cast"]["date"] == "2018-02-26"
    assert spaced_date["cast"]["time"] == "20:42:00"
    assert spaced_date["cast"]["day_ganzhi"] == "己丑"
    assert spaced_date["extraction"]["chart_validation"] == "conflict"
    assert "transcribed_diagram_conflicts_with_reported_chart" in spaced_date["extraction"]["issues"]
    assert spaced_date['cast']['line_values'] is None
    assert any('reported_hexagram_name_conflict' in c['conflicts'] for c in spaced_date['extraction']['diagram_match']['candidates'])
    assert "占盖房子" not in by_case["case_liuyao_lifa_jinjie_9475"]["source"]["original_text"]
    assert by_case["case_liuyao_lifa_jinjie_9522"]["question"]["raw"] == "占盖房子有政府部门的人来干涉吗"
    assert reported_names("主变卦。 洋天央 之 乾为天") == [None, "乾"]
    assert ocr_primary_row("朱雀 国国国 子孙目金 本国本国 子孙申金") is None
    uncorrected_shi = by_case["case_liuyao_lifa_jinjie_8561"]
    assert uncorrected_shi['cast']['line_values'] is None
    assert uncorrected_shi['extraction']['diagram_match']['status'] == 'insufficient_evidence'
    assert all(c['label_evidence_count'] == 0 for c in uncorrected_shi['extraction']['diagram_match']['candidates'])
    assert uncorrected_shi["extraction"]["chart_validation"] == "not_run"


def test_reviewed_cross_page_diagrams_follow_actual_chart_rows():
    root = project_root()
    source = next(json.loads(line) for line in (root / 'data/sources.jsonl').read_text(encoding='utf8').splitlines()
                  if json.loads(line)['source_id'] == 'liuyao_xiangfa_jinjie_shang')
    _, text, _, cases, _ = import_source(source, root)
    by_id = {c['case_id']: c for c in cases}
    # Independently PDF-checked tables on pages 145/146; first header ends page 145.
    for anchor, values, table_page, diagram_start in [
        (6432, [1, 2, 0, 1, 2, 1], 145, 6456),
        (6453, [2, 2, 0, 1, 1, 3], 146, 6500),
        (6490, [3, 1, 2, 1, 1, 1], 146, 6509),
    ]:
        case = by_id[f'case_liuyao_xiangfa_jinjie_shang_{anchor}']
        assert case['cast']['line_values'] == values
        assert case['extraction']['chart_validation'] == 'calculated'
        match = case['extraction']['diagram_match']
        assert match['status'] == 'matched' and match['table_pages'] == [table_page]
        compatible = [c for c in match['candidates'] if c['label_evidence_count'] and not c['conflicts']]
        assert [c['start_line'] for c in compatible] == [diagram_start]
        assert read_spans(text.splitlines(), case['source']['spans']) == case['source']['original_text']
    assert by_id['case_liuyao_xiangfa_jinjie_shang_6453']['derived']['shi_position'] == 3
    assert by_id['case_liuyao_xiangfa_jinjie_shang_6453']['derived']['ying_position'] == 6


def test_unreviewed_cross_page_graph_is_rejected_and_prefix_is_not_lost(monkeypatch):
    monkeypatch.setattr('liuyao_mcp.ingest.apply_corrections', lambda source, text, root: (source, text))
    root = project_root()
    source = next(json.loads(line) for line in (root / 'data/sources.jsonl').read_text(encoding='utf8').splitlines()
                  if json.loads(line)['source_id'] == 'liuyao_xiangfa_jinjie_shang')
    _, _, _, cases, _ = import_source(source, root)
    by_id = {c['case_id']: c for c in cases}
    assert 'case_liuyao_xiangfa_jinjie_shang_6432' in by_id
    case = by_id['case_liuyao_xiangfa_jinjie_shang_6453']
    assert case['cast']['line_values'] is None
    assert case['extraction']['chart_validation'] == 'conflict'
    assert case['extraction']['diagram_match']['table_pages'] == [146]
    assert all(c['start_line'] >= 6500 for c in case['extraction']['diagram_match']['candidates'])
    assert all('爻' not in row[:2] and '→' not in row for row in case['reported_chart']['line_text'])
    assert reported_names('” 主变卦 天地否 之 泽山咸') == ['否', '咸']


def test_equal_page_counts_do_not_assign_ambiguous_diagrams(tmp_path):
    table = '''玄武 ▅▅▅▅▅ 父母戌土 世
白虎 ▅▅▅▅▅ 兄弟申金
腾蛇 ▅▅▅▅▅ 官鬼午火
勾陈 ▅▅▅▅▅ 父母辰土 应
朱雀 ▅▅▅▅▅ 妻财寅木
青龙 ▅▅▅▅▅ 子孙子水
'''
    diagram = '【卦象结构化｜自上而下】\n' + '\n'.join(p+'爻 ━━━━━━ → ━━━━━━' for p in '上五四三二初')+'\n'
    text = '========== PDF 第 1 页 / 共 1 页 ==========\n'
    for n in (1, 2):
        text += f'求测人：{n}\n占问事宜：问工作\n子月甲子日\n” 主变卦 乾为天 之 乾为天\n{table}断曰：本例的说明。\n'
    text += diagram + diagram
    blob = text.encode('utf8');(tmp_path / 'book.md').write_bytes(blob)
    source = dict(source_id='test_book', path='book.md', title='配图归属测试', source_type='ocr_text',
                  method_hint='lifa', pdf_pages=1, sha256=hashlib.sha256(blob).hexdigest())
    cases = import_source(source, tmp_path)[3]
    assert len(cases) == 2
    assert all(c['cast']['line_values'] is None for c in cases)
    assert all(c['extraction']['diagram_match']['status'] == 'ambiguous' for c in cases)


def test_pdf_reviewed_corrections_repair_charts_without_verifying_outcomes():
    root = project_root()
    source = next(json.loads(line) for line in (root / "data/sources.jsonl").read_text(encoding="utf8").splitlines()
                  if json.loads(line)["source_id"] == "liuyao_lifa_jinjie")
    corrected, _, _, cases, _ = import_source(source, root)
    expected = {605: [1, 1, 1, 1, 1, 0], 5002: [2, 1, 1, 3, 2, 1], 4104: [1, 2, 3, 2, 2, 0],
                9475: [2, 0, 3, 2, 2, 2], 9020: [2, 1, 1, 3, 1, 1], 5853: [1, 1, 1, 2, 2, 1],
                8561: [1, 3, 1, 1, 1, 2]}
    by_id = {case["case_id"]: case for case in cases}
    assert corrected["original_sha256"] == source["sha256"] != corrected["sha256"]
    for anchor, values in expected.items():
        case = by_id[f"case_liuyao_lifa_jinjie_{anchor}"]
        assert case["cast"]["line_values"] == values
        assert case["extraction"]["chart_validation"] == "calculated"
        assert case["extraction"]["issues"] == []
        assert not case["outcome"]["independently_verified"]
    for anchor in (9020, 5853):
        assert by_id[f"case_liuyao_lifa_jinjie_{anchor}"]["outcome"]["status"] == "reported_explicit"
    assert by_id["case_liuyao_lifa_jinjie_8561"]["features"]["shi_relative"] == "子孙"
    assert by_id["case_liuyao_lifa_jinjie_8561"]["derived"]["shi_position"] == 5


def test_actual_partial_date_boundary_and_header_only_passage():
    root = project_root()
    sources = [json.loads(line) for line in (root / "data/sources.jsonl").read_text(encoding="utf8").splitlines()]
    _, text, _, cases, _ = import_source(next(s for s in sources if s["source_id"] == "zengshan_buyi"), root)
    by_id = {case["case_id"]: case for case in cases}
    first, second = by_id["case_zengshan_buyi_5950"], by_id["case_zengshan_buyi_5990"]
    assert "占文书" not in first["source"]["original_text"]
    assert first["features"]["yongshen_reported"] is None
    assert second["cast"]["day_ganzhi"] == "丙申" and second["cast"]["month_branch"] is None
    for case in (first, second):
        interpretation = case["interpretations"][0]
        assert read_spans(text.splitlines(), interpretation["source_spans"]).replace("\n", "") in interpretation["original_text"].replace("\n", "")
    _, _, chunks, cases, _ = import_source(next(s for s in sources if s["source_id"] == "liuyao_xiangfa_jinjie_xia"), root)
    header = next(c for c in chunks if c["id"] == "rule_liuyao_xiangfa_jinjie_xia_5016")
    assert header["content_role"] == "case_excerpt" and not header["has_case_analysis"]
    assert any(c["content_role"] == "theory" and not c["has_case_analysis"] for c in chunks)
    by_id = {c["case_id"]: c for c in cases}
    for anchor in (426, 6997):
        assert "reported_line_3_shi_conflicts_with_position" not in by_id[f"case_liuyao_xiangfa_jinjie_xia_{anchor}"]["extraction"]["issues"]
