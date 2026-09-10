"""Source headings and literal evidence contracts; no evaluation-case fixtures."""
import hashlib
import json
import sqlite3

from liuyao_mcp.common import project_root
from liuyao_mcp.ingest import author_yongshen, chart_only, import_source, ingest, native_question, read_spans
from liuyao_mcp.retrieval import get_source


def parse(tmp_path, text):
    blob = text.encode('utf8')
    (tmp_path / 'book.md').write_bytes(blob)
    source = dict(source_id='test_book', path='book.md', title='结构测试', source_type='native_text',
                  method_hint='mixed', pdf_pages=None, sha256=hashlib.sha256(blob).hexdigest())
    return import_source(source, tmp_path)


def test_native_numbered_sections_keep_parent_context_and_exact_spans():
    root = project_root()
    source = next(json.loads(line) for line in (root / 'data/sources.jsonl').read_text(encoding='utf8').splitlines()
                  if json.loads(line)['source_id'] == 'liuyao_zixiu_dxj')
    _, text, chunks, _, report = import_source(source, root)
    # Verified training book headings: six-relative meanings, then six-spirit meanings.
    expected = {2136: '(一)父母含义', 2140: '(二)官鬼含义', 2144: '(三)兄弟爻含义',
                2148: '(四)妻财含义', 2152: '(五)子孙含义', 2188: '(一)青龙的含义',
                2192: '(二)朱雀的含义', 2196: '(三)勾陈的含义', 2200: '(四)呈蛇的含义',
                2204: '(五)白虎的含义', 2208: '(六)玄武的含义'}
    sections = {c['start_line']: c for c in chunks if c.get('section')}
    assert set(expected) <= sections.keys()
    for line, title in expected.items():
        chunk = sections[line]
        assert chunk['section']['title'] == title
        assert chunk['section']['title_basis'] == 'source_numbered_subsection'
        assert chunk['end_line'] == line
        assert read_spans(text.splitlines(), [{'start_line': line, 'end_line': line}]) == chunk['text']
        assert chunk['content_role'] == 'theory'
        assert chunk['classification']['scope'] == ('common' if line < 2156 else 'scene')
    assert sections[2152]['chapter'] == '## 第五节 六亲的含义 / (五)子孙含义'
    assert sections[2152]['section']['parent_start_line'] == 2128
    assert '动物' in sections[2152]['text']
    assert '(五)子孙含义' not in next(c for c in chunks if c['start_line'] == 2128)['text']
    assert report['covered_lines'] == report['total_lines']


def test_subsection_continuations_and_next_heading_are_separate(tmp_path):
    text = '## 第五节 六亲的含义\n总论。\n\n（一）父母含义：代表文书。\n补充原文。\n\n（二）子孙含义：代表晚辈。\n\n## 第六节 六亲的生克关系\n子孙生妻财。\n'
    _, _, chunks, _, report = parse(tmp_path, text)
    assert len(chunks) == 4
    assert chunks[1]['text'] == '（一）父母含义：代表文书。\n补充原文。'
    assert chunks[2]['section']['parent_title'] == chunks[1]['section']['parent_title']
    assert 'section' not in chunks[-1]
    assert chunks[-1]['chapter'] == '## 第六节 六亲的生克关系'
    assert report['covered_lines'] == report['total_lines']


def test_relative_definition_titles_split_numbered_and_unnumbered_sources():
    root = project_root()
    sources = [json.loads(line) for line in (root / 'data/sources.jsonl').read_text(encoding='utf8').splitlines()]
    expected = {'zengshan_pingshi_dxj': [(2558, '1、父母爻'), (2566, '2、官鬼爻'), (2574, '3、兄弟爻'),
                                       (2590, '4、妻财爻'), (2598, '5、子孙爻')],
                'zengshan_buyi': [(1998, '父母爻'), (2002, '官鬼爻'), (2006, '兄弟爻'),
                                  (2010, '妻财爻'), (2014, '子孙爻')]}
    for source_id, headings in expected.items():
        _, text, chunks, _, report = import_source(next(s for s in sources if s['source_id'] == source_id), root)
        by_start = {c['start_line']: c for c in chunks}
        for i, (line, title) in enumerate(headings):
            chunk = by_start[line]
            assert chunk['section']['title'] == title
            assert chunk['section']['title_basis'] == 'source_relative_definition'
            assert '用神章第八' in chunk['section']['parent_title']
            assert chunk['classification']['scope'] == 'common'
            assert chunk['content_role'] == 'theory' and not chunk['related_case_ids']
            assert chunk['text'] == read_spans(text.splitlines(), [{'start_line': line, 'end_line': chunk['end_line']}])
            if i+1 < len(headings):
                assert chunk['end_line'] < headings[i+1][0]
        assert '六畜' in by_start[headings[-1][0]]['text']
        assert report['total_lines'] == report['covered_lines']


def test_relative_definition_titles_do_not_split_chart_or_case_analysis(tmp_path):
    text = '''用神章第八
一、父母爻：占文书。
二、子孙爻；占六畜。
卯月乙丑日占求婚成否
子孙巳火′
妻财未土″
官鬼酉金′
妻财辰土″
兄弟寅木″
父母子水′
父母爻：本卦这一爻的说明。
子孙爻；本卦另一爻的说明。
'''
    _, parsed, chunks, cases, _ = parse(tmp_path, text)
    assert len(cases) == 1
    theory = [c for c in chunks if c['content_role'] == 'theory']
    assert [c.get('section', {}).get('title') for c in theory] == [None, '一、父母爻', '二、子孙爻']
    assert all(c.get('section', {}).get('start_line', 0) < 4 for c in chunks)
    assert '父母爻：本卦' in cases[0]['interpretations'][0]['original_text']
    assert '子孙爻；本卦' in cases[0]['interpretations'][0]['original_text']
    assert cases[0]['source']['original_text'] == read_spans(parsed.splitlines(), cases[0]['source']['spans'])


def test_background_is_structural_and_remains_source_accessible(tmp_path):
    text = '序 言\n本书介绍预测方法。\n\n学员感悟 〈一)\n学习之后，我对前言有新的理解。\n\n# 第一章 六爻预测和我们的生活\n生活中的预测故事。\n\n# 第二章 用神\n父母为用神。\n在此讨论学员感悟中提到的取用。\n'
    source, _, chunks, _, _ = parse(tmp_path, text)
    assert [c['content_role'] for c in chunks] == ['background', 'background', 'background', 'theory']
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/sources.jsonl').write_text(json.dumps(source, ensure_ascii=False)+'\n', encoding='utf8')
    db_path = tmp_path / 'separate/knowledge.sqlite'
    ingest(tmp_path, db_path)
    for chunk in chunks:
        retrieved = get_source(chunk['id'], db_path=db_path)
        assert retrieved['text'] == chunk['text']
    with sqlite3.connect(db_path) as db:
        assert db.execute('SELECT body FROM sources').fetchone()[0] == text


def test_literal_yongshen_keeps_offsets_and_multiple_choices():
    lines = ['断曰：兄弟申金为用神。以子孙亥水为用神；用神为父母。',
             '取妻财丁未土爻作为用神，妻财爻为用。',
             '不以官鬼为用神。反馈：子孙亥水为用神。']
    relatives, evidence = author_yongshen(lines, range(len(lines)))
    assert relatives == ['兄弟', '子孙', '父母', '妻财']
    assert [e['quote'] for e in evidence] == ['兄弟申金为用神', '以子孙亥水为用神', '用神为父母',
                                           '取妻财丁未土爻作为用神', '妻财爻为用']
    for item in evidence:
        span = item['source_spans'][0]
        assert span['start_line'] == span['end_line']
        assert lines[span['start_line']-1][item['start_char']:item['end_char']] == item['quote']
    relatives, evidence = author_yongshen(['以子孙妻财为用神。'], [0])
    assert relatives == ['子孙', '妻财']
    assert {e['quote'] for e in evidence} == {'以子孙妻财为用神'}


def test_yongshen_complements_are_not_author_choices():
    for suffix in ('墓库', '之墓库', '的墓库', '之墓', '之元神', '的元神', '元神', '的忌神', '之仇神'):
        assert author_yongshen([f'兄弟戌土为用神{suffix}。'], [0]) == ([], [])
    assert author_yongshen(['用神为父母的元神。'], [0]) == ([], [])
    for text in ('以父母爻为用神的理由如下。', '以父母爻为用神，兄弟戌土为用神墓库。',
                 '父母爻为用神墓于戌。'):
        relatives, evidence = author_yongshen([text], [0])
        assert relatives == ['父母']
        assert evidence[0]['quote'] in text
    root = project_root()
    source = next(json.loads(line) for line in (root / 'data/sources.jsonl').read_text(encoding='utf8').splitlines()
                  if json.loads(line)['source_id'] == 'liuyao_zixiu_dxj')
    _, text, _, cases, _ = import_source(source, root)
    case = next(c for c in cases if c['case_id'] == 'case_liuyao_zixiu_dxj_10180')
    assert case['features']['yongshen_reported'] == ['父母']
    assert '兄弟戌土为用神墓库' in case['interpretations'][0]['original_text']
    for evidence in case['interpretations'][0]['yongshen_evidence']:
        assert evidence['relative'] == '父母'
        line = text.splitlines()[evidence['source_spans'][0]['start_line']-1]
        assert line[evidence['start_char']:evidence['end_char']] == evidence['quote']


def test_chart_only_units_keep_source_but_are_not_searchable(tmp_path):
    diagram = '【卦象结构化 1｜按原图自上而下：上爻→初爻】\n爻位 本卦 动爻 变卦\n'
    diagram += '\n'.join(p+'爻 ━━━━━━ → ━━━━━━' for p in '上五四三二初')
    assert chart_only(diagram)
    assert chart_only('| 六神 | 本卦 |\n| --- | --- |\n| 青龙 | 父母子水′世 |')
    for rule in ('用神旺相为吉。', '父母子水′生世', '阳爻：━━━━━━', diagram+'\n父母发动生世。',
                 diagram+'\n主变卦均为六冲'):
        assert not chart_only(rule)
    text = diagram+'\n========== PDF 第 2 页 / 共 2 页 ==========\n用神旺相为吉。\n'
    source, _, chunks, _, _ = parse(tmp_path, text)
    assert [c['content_role'] for c in chunks] == ['chart_only', 'theory']
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/sources.jsonl').write_text(json.dumps(source, ensure_ascii=False)+'\n', encoding='utf8')
    output = tmp_path / 'isolated/knowledge.sqlite'
    ingest(tmp_path, output)
    with sqlite3.connect(output) as db:
        assert [r[0] for r in db.execute('SELECT searchable FROM evidence_metadata ORDER BY start_line')] == [0, 1]
    assert get_source(chunks[0]['id'], db_path=output)['text'] == diagram
    root = project_root()
    source = next(json.loads(line) for line in (root / 'data/sources.jsonl').read_text(encoding='utf8').splitlines()
                  if json.loads(line)['source_id'] == 'liuyao_lifa_jinjie')
    chunk = next(c for c in import_source(source, root)[2] if c['id'] == 'rule_liuyao_lifa_jinjie_8226')
    assert chunk['content_role'] == 'chart_only'


def test_chapter_fallback_preserves_root_without_claiming_subtopic(tmp_path):
    rows = '\n'.join(['父母戌土′应', '兄弟申金′', '官鬼午火′', '妻财卯木″世', '官鬼巳火″', '父母未土″'])
    for question, basis, paths in [('占此事', 'chapter_only', ['travel']),
                                    ('占行人何时回家', 'question_only', None)]:
        text = '行人章第九十四\n卯月乙丑日'+question+'\n'+rows+'\n断曰：此例说明。\n'
        cases = parse(tmp_path, text)[3]
        assert len(cases) == 1
        classification = cases[0]['classification']
        assert classification['basis'] == basis
        if paths is not None:
            assert classification['topic_ids'] == paths
            assert classification['chapter_evidence'] == '行人章第九十四'
            assert all('/' not in e['id'] for e in classification['evidence'])
        else:
            assert 'travel/return' in classification['topic_ids']


def test_yongshen_stays_inside_analysis_and_candidates_remain_ambiguous(tmp_path):
    # Six original chart rows from the training book 增删卜易, lines 4418-4450.
    text = '''卯月乙丑日占求婚成否，兄弟申金为用神？
子孙巳火′ 动 父母子水″应
妻财未土″世 动 妻财戌土′
官鬼酉金′ 动 官鬼申金″
妻财辰土″ 兄弟卯木″世
兄弟寅木″应 子孙巳火″
父母子水′ 动 妻财未土″

========== PDF 第 1 页 / 共 1 页 ==========
断曰：以妻财未土为用神。用神为子孙。
反馈：父母为用神。
'''
    _, parsed, chunks, cases, _ = parse(tmp_path, text)
    assert len(cases) == 1
    case = cases[0]
    assert case['features']['yongshen_reported'] == ['妻财', '子孙']
    choices = case['features']['yongshen_candidates']
    wives = [c for c in choices if c['relative'] == '妻财']
    assert {(c['scope'], c['position']) for c in wives} == {
        ('primary', 3), ('primary', 5), ('changed', 1), ('changed', 5)}
    assert all(c['moving'] is None for c in choices if c['scope'] == 'changed')
    assert all(c['selection'] == 'relative_match_not_author_line_selection' for c in choices)
    interpretation = case['interpretations'][0]
    for item in interpretation['yongshen_evidence']:
        assert item['source_spans'][0]['start_line'] > 7
        assert item['quote'] in read_spans(parsed.splitlines(), item['source_spans'])
    header = chunks[0]
    assert header['content_role'] == 'case_excerpt' and not header['has_case_analysis']
    assert any(c['has_case_analysis'] for c in chunks)


def test_unreadable_chart_keeps_explicit_author_choice_without_inventing_features(tmp_path):
    text = '''卯月乙丑日占求婚成否
子孙巳火′
妻财未土″
官鬼酉金′
妻财辰土″
兄弟寅木″

断曰：以妻财为用神。
'''
    _, _, _, cases, _ = parse(tmp_path, text)
    assert len(cases) == 1
    case = cases[0]
    assert case['features']['yongshen_reported'] == ['妻财']
    assert case['features']['chart_feature_status'] == 'not_run'
    assert 'yongshen_candidates' not in case['features']
    assert case['interpretations'][0]['source_span_basis'] == 'unresolved_chart_end'
    assert case['interpretations'][0]['yongshen_evidence'][0]['source_spans'] == [{'start_line': 8, 'end_line': 8}]


def test_native_question_skips_generic_preface_and_stops_at_real_hexagram():
    # Training-source 王虎应增删卜易评释 line 24130, then independent header contracts.
    text = '例，一易友为某人预测得一例。亥月庚申日，一男测去西南求财如何？得临之比。'
    assert native_question([text], text) == '亥月庚申日，一男测去西南求财如何'
    for header, expected in [
        ('例，来人请我预测。其中有个人要测官运，得家人之蹇卦。', '其中有个人要测官运'),
        ('某女补考后放心不下。于是测考试能及格否？于亥月己酉日，得雷火丰卦。', '于是测考试能及格否'),
        ('某人问，将来官至方面否？巳月乙卯日，占得雷山小过。', '某人问，将来官至方面否'),
        ('例三、午月乙酉日，从日本寄的书何日到？得天雷无妄卦。', '例三、午月乙酉日，从日本寄的书何日到'),
        ('卯月乙丑日，测收到赠品能否得益？得山雷颐。', '卯月乙丑日，测收到赠品能否得益'),
        ('例一，我得验之卦。酉月丁丑日，女占单位同事病，得地天泰变雷泽归妹卦。', '酉月丁丑日，女占单位同事病'),
        ('例，一男曾得有肝硬化二十余年已好，问自己寿命如何？得艮之乾。', '例，一男曾得有肝硬化二十余年已好，问自己寿命如何'),
        ('如卯月甲寅日占风水得雷风恒变天山遁。', '如卯月甲寅日占风水'),
        ('如卯月壬辰日占候文书何日得领，得山火贲卦。', '如卯月壬辰日占候文书何日得领'),
    ]:
        assert native_question([header], header) == expected
    for header in [['测考试能否通过', '亥月己酉日'], ['亥月己酉日', '测考试能否通过']]:
        assert native_question(header, '亥月己酉日') == '测考试能否通过'
    assert native_question(['古法是否皆可应用？命之再占一卦。得离卦。'], '古法是否皆可应用？命之再占一卦。得离卦。') is None
