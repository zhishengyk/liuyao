"""Verbatim, complete range/context routing and deterministic regeneration."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess

import pytest


def exporter():
    path = Path(__file__).resolve().parents[1] / 'scripts/build_skill_prompts.py'
    spec = importlib.util.spec_from_file_location('skill_prompt_export', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(tmp_path):
    database = tmp_path / 'knowledge.sqlite'
    db = sqlite3.connect(database)
    db.executescript('CREATE TABLE sources(id TEXT,metadata TEXT,body TEXT);'
                     'CREATE TABLE chunks(id TEXT,payload TEXT);'
                     'CREATE TABLE ocr_pages(source_id TEXT,pdf_page INT,payload TEXT);')
    db.execute('INSERT INTO sources VALUES(?,?,?)', ('book_a', json.dumps({'title': '甲书', 'author': '甲'}),
               '章首\n前提\n不可省略的例外\n原注结论\n共同导语\n另例\n末行'))
    db.execute('INSERT INTO sources VALUES(?,?,?)', ('book_b', json.dumps({'title': '乙书', 'author': '乙'}),
               '另一作者不同意见\n```原文保留```\n页末'))
    units = [
        {'id': 'a', 'source_id': 'book_a', 'source_spans': [{'start_line': 2, 'end_line': 2}, {'start_line': 4, 'end_line': 4}],
         'classification': {'scope': 'topic', 'roots': ['study']},
         'required_contexts': [{'source_spans': [{'start_line': 5, 'end_line': 5}]}]},
        {'id': 'b', 'source_id': 'book_b', 'source_spans': [{'start_line': 1, 'end_line': 2}],
         'classification': {'scope': 'common', 'roots': []}},
        {'id': 'c', 'source_id': 'book_a', 'source_spans': [{'start_line': 6, 'end_line': 6}],
         'classification': {'scope': 'scene', 'roots': []}},
    ]
    db.executemany('INSERT INTO chunks VALUES(?,?)', [(u['id'], json.dumps(u)) for u in units])
    db.execute('INSERT INTO ocr_pages VALUES(?,?,?)', ('book_b', 1, json.dumps({
        'canonical_start_line': 1, 'canonical_end_line': 3, 'status': 'canonical_machine',
        'visual_reviewed': False, 'unclear': ['字形待核']})))
    db.commit()
    db.close()
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'domains': {'study': {'title': '学习', 'questions': ['当前行为', '考试']},
                                          'objects': {'title': '物品', 'questions': ['质量']}},
        'supplemental_spans': [{'bucket': 'study', 'source_id': 'book_a', 'start_line': 1, 'end_line': 2, 'reason': '完整章首'}],
        'supplemental_pages': [{'bucket': 'global', 'source_id': 'book_b', 'pages': [1]}],
        'supplemental_ids': {'objects': ['b']},
        'workflow': [{'step': 1, 'title': '先定原问', 'route': '先核对对象和时限。',
                      'evidence_ids': ['a', 'b']}],
        'selection_policy': 'verbatim'}), encoding='utf-8')
    return database, plan


def test_preserves_intermediate_lines_context_author_scope_and_regenerates(tmp_path):
    module = exporter()
    database, plan = fixture(tmp_path)
    before = database.read_bytes()
    output = tmp_path / 'prompts'
    result = module.build(database, output, plan)
    assert result['all_theory_units_accounted'] and result['theory_units'] == 3
    assert result['database_only_evidence_ids'] == ['c']
    original = '章首\n前提\n不可省略的例外\n原注结论\n共同导语'
    assert original in (output / 'study/book_a.md').read_text(encoding='utf-8')
    assert (output / 'study/book_a.md').read_text(encoding='utf-8').count('共同导语') == 1
    assert '另一作者不同意见\n```原文保留```\n页末' in (output / 'global/book_b.md').read_text(encoding='utf-8')
    global_prompt = (output / 'GLOBAL.md').read_text(encoding='utf-8')
    assert '本步执行：先核对对象和时限。' in global_prompt
    assert '前提\n不可省略的例外\n原注结论' in global_prompt
    assert '共同导语' in global_prompt
    assert '另一作者不同意见\n```原文保留```' in global_prompt
    assert 'FLOW.md' not in result['files_sha256']
    assert any(section['file'] == 'GLOBAL.md' and section['source_id'] == 'book_a'
               for section in result['sections'])
    page = next(s for s in result['sections'] if s['file'] == 'global/book_b.md')['pages'][0]
    assert page['visual_reviewed'] is False and page['unclear'] == ['字形待核']
    assert '没有直接分类的理论条目' in (output / 'objects/PROMPT.md').read_text(encoding='utf-8')
    assert result['evidence_by_bucket']['objects'] == ['b']
    assert 'b' not in result['database_only_evidence_ids']
    hashes = dict(result['files_sha256'])
    assert module.build(database, output, plan)['files_sha256'] == hashes
    assert database.read_bytes() == before
    # Only generator-listed obsolete files are removed; unrelated local notes survive.
    (output / 'obsolete.md').write_text('old', encoding='utf-8')
    (output / 'keep.note').write_text('local', encoding='utf-8')
    result['files_sha256']['obsolete.md'] = 'old'
    (output / 'manifest.json').write_text(json.dumps(result), encoding='utf-8')
    module.build(database, output, plan)
    assert not (output / 'obsolete.md').exists() and (output / 'keep.note').exists()


def test_bad_source_range_stops_without_changing_existing_prompt(tmp_path):
    module = exporter()
    database, plan = fixture(tmp_path)
    output = tmp_path / 'prompts'
    module.build(database, output, plan)
    before = (output / 'GLOBAL.md').read_bytes()
    config = json.loads(plan.read_text(encoding='utf-8'))
    config['supplemental_spans'][0]['end_line'] = 100
    plan.write_text(json.dumps(config), encoding='utf-8')
    with pytest.raises(ValueError, match='Invalid source lines'):
        module.build(database, output, plan)
    assert (output / 'GLOBAL.md').read_bytes() == before


def test_public_source_reader_paginates_verbatim_and_rejects_stale_or_unlisted_files(tmp_path):
    from liuyao_mcp.retrieval import get_source

    database, plan = fixture(tmp_path)
    output = tmp_path / 'source-prompts'
    exporter().build(database, output, plan)
    original = (output / 'GLOBAL.md').read_text(encoding='utf-8')
    parts, offset = [], 0
    while True:
        result = get_source('prompt:GLOBAL.md', offset=offset, max_chars=1000, db_path=database)
        assert result['kind'] == 'skill_prompt'
        parts.append(result['text'])
        if not result['has_more']:
            break
        assert result['next_offset'] > offset
        offset = result['next_offset']
    assert ''.join(parts) == original
    flow = get_source('prompt:GLOBAL.md', offset=0, max_chars=1000, db_path=database)
    assert flow['kind'] == 'skill_prompt' and flow['prompt_path'] == 'GLOBAL.md'
    assert flow['source_sections']
    for bad in ['prompt:../secret.md', 'prompt:/GLOBAL.md', 'prompt:unknown.md']:
        with pytest.raises(ValueError):
            get_source(bad, db_path=database)
    with pytest.raises(ValueError, match='original'):
        get_source('prompt:GLOBAL.md', text_version='original', db_path=database)
    page = output / 'GLOBAL.md'
    page.write_text(original + 'unexpected edit', encoding='utf-8')
    with pytest.raises(ValueError, match='文件校验失败'):
        get_source('prompt:GLOBAL.md', db_path=database)
    page.write_bytes(original.encode('utf-8'))
    with sqlite3.connect(database) as db:
        db.execute("UPDATE sources SET body=body||'变化' WHERE id='book_a'")
    with pytest.raises(ValueError, match='语料内容不一致'):
        get_source('prompt:GLOBAL.md', db_path=database)


def test_production_source_filter_keeps_compare_only_theory_out_of_prompts(tmp_path):
    module = exporter()
    database, plan = fixture(tmp_path)
    with sqlite3.connect(database) as db:
        row = db.execute("SELECT payload FROM chunks WHERE id='b'").fetchone()
        payload = json.loads(row[0])
        payload['classification'] = {'scope': 'topic', 'roots': ['study']}
        db.execute("UPDATE chunks SET payload=? WHERE id='b'", (json.dumps(payload),))
        db.commit()

    config = json.loads(plan.read_text(encoding='utf-8'))
    config['production_source_ids'] = ['book_a']
    config['supplemental_pages'] = []
    config['supplemental_ids'] = {}
    config['workflow'][0]['evidence_ids'] = ['a']
    plan.write_text(json.dumps(config), encoding='utf-8')

    output = tmp_path / 'prompts'
    result = module.build(database, output, plan)

    assert result['schema_version'] == 2
    assert result['production_source_ids'] == ['book_a']
    assert 'b' in result['compare_only_evidence_ids']
    assert not (output / 'study/book_b.md').exists()
    assert not (output / 'global/book_b.md').exists()
    assert '另一作者不同意见' not in (output / 'GLOBAL.md').read_text(encoding='utf-8')
    assert result['all_theory_units_accounted']


def test_workflow_rejects_nonproduction_source(tmp_path):
    module = exporter()
    database, plan = fixture(tmp_path)
    config = json.loads(plan.read_text(encoding='utf-8'))
    config['production_source_ids'] = ['book_a']
    config['supplemental_pages'] = []
    config['supplemental_ids'] = {}
    plan.write_text(json.dumps(config), encoding='utf-8')

    with pytest.raises(ValueError, match='Workflow evidence is not an allowed production source'):
        module.build(database, tmp_path / 'prompts', plan)


def test_prompt_manifest_preserves_span_author_annotations(tmp_path):
    module = exporter()
    database, plan = fixture(tmp_path)
    with sqlite3.connect(database) as db:
        row = db.execute("SELECT payload FROM chunks WHERE id='a'").fetchone()
        payload = json.loads(row[0])
        for span in payload['source_spans']:
            span['author'] = '王虎应'
        payload['required_contexts'][0]['source_spans'][0]['author'] = '原作者'
        db.execute("UPDATE chunks SET payload=? WHERE id='a'", (json.dumps(payload),))
        db.commit()

    output = tmp_path / 'prompts'
    result = module.build(database, output, plan)

    a_selections = [s for s in result['selections'] if s['label'] == 'a']
    assert a_selections and a_selections[0]['authors'] == ['王虎应']
    section = next(s for s in result['sections']
                   if s['file'] == 'study/book_a.md' and s['start_line'] <= 2 <= s['end_line'])
    assert '王虎应' in section['authors']


def test_wang_archive_corpus_is_pinned_deduplicated_and_readable(tmp_path):
    module = exporter()
    database, plan = fixture(tmp_path)
    archive = tmp_path / 'archive'
    archive.mkdir()
    subprocess.run(['git', 'init'], cwd=archive, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=archive, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=archive, check=True)
    (archive / '王虎应：六爻预测自修宝典.doc.md').write_text('王虎应全文甲\n第二行\n', encoding='utf-8')
    (archive / '王老师工作问答录.doc.md').write_text('求职问答全文\n', encoding='utf-8')
    (archive / 'sub').mkdir()
    (archive / 'sub/王虎应副本.doc.md').write_text('王虎应全文甲\n第二行\n', encoding='utf-8')
    (archive / '刘虹言《点评王虎应化解密传》.pdf.md').write_text('第三方点评\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=archive, check=True)
    subprocess.run(['git', 'commit', '-m', 'archive'], cwd=archive, check=True, capture_output=True)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=archive, text=True).strip()

    archive_manifest = tmp_path / 'wang.json'
    archive_manifest.write_text(json.dumps({
        'schema_version': 1,
        'archive_branch': 'test',
        'archive_commit_sha': head,
        'archive_root': 'test',
        'selection_policy': 'test',
        'basename_contains': ['王虎应', '王老师'],
        'exact_paths': [],
        'exclude_globs': ['**/*点评王虎应*.md'],
        'authority_overrides': [
            {'glob': '**/*六爻预测自修宝典*.md', 'authority_tier': 'wang_direct'},
            {'glob': '**/*问答录*.md', 'authority_tier': 'wang_case_specific'},
        ],
        'default_authority_tier': 'wang_case_specific',
        'domain_rules': [{'contains': ['工作'], 'domains': ['job']},
                         {'contains': ['自修宝典'], 'domains': ['*']}],
    }, ensure_ascii=False), encoding='utf-8')

    output = tmp_path / 'source-prompts'
    result = module.build(database, output, plan,
                          wang_archive_root=archive,
                          wang_archive_manifest=archive_manifest)

    archive_meta = result['wang_huying_archive']
    assert archive_meta['archive_head_verified'] == head
    assert archive_meta['matched_files'] == 3
    assert archive_meta['canonical_files'] == 2
    assert (output / 'wang-huying-corpus/INDEX.md').exists()
    assert (output / 'wang-huying-corpus/domains/job.md').exists()
    corpus_files = list((output / 'wang-huying-corpus').glob('wha-*.md'))
    assert len(corpus_files) == 2
    assert any(record['duplicate_of'] for record in archive_meta['records'])

    from liuyao_mcp.retrieval import get_source
    index = get_source('prompt:wang-huying-corpus/INDEX.md', db_path=database)
    assert index['kind'] == 'skill_prompt'
    assert '王虎应六爻原文全集索引' in index['text']


def test_wang_archive_commit_mismatch_fails_closed(tmp_path):
    module = exporter()
    database, plan = fixture(tmp_path)
    archive = tmp_path / 'archive'
    archive.mkdir()
    subprocess.run(['git', 'init'], cwd=archive, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=archive, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=archive, check=True)
    (archive / '王虎应资料.md').write_text('正文\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=archive, check=True)
    subprocess.run(['git', 'commit', '-m', 'archive'], cwd=archive, check=True, capture_output=True)

    archive_manifest = tmp_path / 'wang.json'
    archive_manifest.write_text(json.dumps({
        'schema_version': 1,
        'archive_commit_sha': '0' * 40,
        'basename_contains': ['王虎应'],
        'exact_paths': [],
        'exclude_globs': [],
        'authority_overrides': [],
        'default_authority_tier': 'wang_case_specific',
        'domain_rules': [],
    }, ensure_ascii=False), encoding='utf-8')

    with pytest.raises(ValueError, match='archive commit mismatch'):
        module.build(database, tmp_path / 'prompts', plan,
                     wang_archive_root=archive,
                     wang_archive_manifest=archive_manifest)


def test_wang_archive_authority_most_specific_override_wins(tmp_path):
    module = exporter()
    config = {
        'default_authority_tier': 'wang_case_specific',
        'authority_overrides': [
            {'glob': '09_卦例/正式著作.md', 'authority_tier': 'wang_direct'},
            {'glob': '09_卦例/*', 'authority_tier': 'wang_case_specific'},
            {'glob': '11_讲义记录/*', 'authority_tier': 'mixed_requires_attribution'},
            {'glob': '11_讲义记录/学员笔记.md', 'authority_tier': 'compare_only'},
            {'glob': '90_他人整理/*', 'authority_tier': 'mixed_requires_attribution'},
            {'glob': '90_他人整理/王虎应增删卜易评释(整理).md', 'authority_tier': 'wang_direct'},
        ],
    }

    assert module.archive_authority('09_卦例/正式著作.md', config) == 'wang_direct'
    assert module.archive_authority('09_卦例/普通卦例.md', config) == 'wang_case_specific'
    assert module.archive_authority('11_讲义记录/学员笔记.md', config) == 'compare_only'
    assert module.archive_authority('11_讲义记录/普通讲课.md', config) == 'mixed_requires_attribution'
    assert module.archive_authority(
        '90_他人整理/王虎应增删卜易评释(整理).md', config) == 'wang_direct'


def test_author_scoped_archive_manifest_includes_all_nonempty_markdown(tmp_path):
    module = exporter()
    database, plan = fixture(tmp_path)
    archive = tmp_path / 'archive'
    (archive / '01_核心著作').mkdir(parents=True)
    (archive / '09_卦例').mkdir()
    (archive / '90_他人整理').mkdir()
    subprocess.run(['git', 'init'], cwd=archive, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=archive, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=archive, check=True)
    (archive / '01_核心著作/六爻疑惑指迷.md').write_text('正式著作正文\n', encoding='utf-8')
    (archive / '09_卦例/007六爻卦例说真.md').write_text('本人卦例正文\n', encoding='utf-8')
    (archive / '90_他人整理/整理版.md').write_text('整理版正文\n', encoding='utf-8')
    (archive / '09_卦例/空占位.md').write_text('', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=archive, check=True)
    subprocess.run(['git', 'commit', '-m', 'archive'], cwd=archive, check=True, capture_output=True)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=archive, text=True).strip()

    archive_manifest = tmp_path / 'wang.json'
    archive_manifest.write_text(json.dumps({
        'schema_version': 1,
        'archive_branch': 'test',
        'archive_commit_sha': head,
        'archive_root': '书籍/六爻/王虎应',
        'selection_policy': 'author scoped',
        'include_all_markdown_under_root': True,
        'skip_empty_files': True,
        'basename_contains': [],
        'exact_paths': [],
        'exclude_globs': [],
        'authority_overrides': [
            {'glob': '01_核心著作/*', 'authority_tier': 'wang_direct'},
            {'glob': '09_卦例/*', 'authority_tier': 'wang_case_specific'},
            {'glob': '90_他人整理/*', 'authority_tier': 'mixed_requires_attribution'},
        ],
        'default_authority_tier': 'wang_case_specific',
        'domain_rules': [
            {'contains': ['01_核心著作/'], 'domains': ['*']},
            {'contains': ['卦例'], 'domains': ['affairs']},
        ],
        'all_domains': ['affairs', 'job'],
    }, ensure_ascii=False), encoding='utf-8')

    output = tmp_path / 'source-prompts'
    result = module.build(database, output, plan,
                          wang_archive_root=archive,
                          wang_archive_manifest=archive_manifest)

    meta = result['wang_huying_archive']
    assert meta['matched_files'] == 3
    assert meta['canonical_files'] == 3
    assert not any(record['archive_path'].endswith('空占位.md') for record in meta['records'])
    authority = {record['archive_path']: record['authority_tier'] for record in meta['records']}
    assert authority['01_核心著作/六爻疑惑指迷.md'] == 'wang_direct'
    assert authority['09_卦例/007六爻卦例说真.md'] == 'wang_case_specific'
    assert authority['90_他人整理/整理版.md'] == 'mixed_requires_attribution'
    assert (output / 'wang-huying-corpus/domains/job.md').exists()


def test_global_rule_groups_render_by_title_and_keep_unclassified_rules(tmp_path):
    module = exporter()
    database, plan = fixture(tmp_path)
    config = json.loads(plan.read_text(encoding='utf-8'))
    config['global_case_rules'] = [
        '【原问中心】先回答原问。',
        '【新增规则】这条尚未归类。',
    ]
    config['global_rule_groups'] = [{
        'title': '原问与取用',
        'purpose': '先定问题。',
        'rule_titles': ['原问中心'],
    }]
    plan.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')

    output = tmp_path / 'prompts'
    module.build(database, output, plan)
    prompt = (output / 'GLOBAL.md').read_text(encoding='utf-8')

    assert '### 原问与取用' in prompt
    assert prompt.count('【原问中心】先回答原问。') == 1
    assert '### 新增待归类规则' in prompt
    assert prompt.count('【新增规则】这条尚未归类。') == 1

def test_domain_prompt_overlays_global_pipeline_without_leaking_rules(tmp_path):
    module = exporter()
    database, plan = fixture(tmp_path)
    config = json.loads(plan.read_text(encoding='utf-8'))
    config['domains']['study']['case_rules'] = ['【考试专属】只在study领域加载。']
    plan.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')

    output = tmp_path / 'prompts'
    module.build(database, output, plan)

    global_prompt = (output / 'GLOBAL.md').read_text(encoding='utf-8')
    study_prompt = (output / 'study/PROMPT.md').read_text(encoding='utf-8')

    assert '【考试专属】只在study领域加载。' not in global_prompt
    assert '【考试专属】只在study领域加载。' in study_prompt
    assert '识别本领域后，必须在执行取用、现实角色、事项特例和应期等对应步骤之前加载本领域规则' in study_prompt
    assert '不得先跑完整个GLOBAL后再用领域规则事后改答案' in study_prompt

def test_repository_prompt_plan_global_group_titles_are_total_and_unique():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / 'scripts/skill_prompt_plan.json').read_text(encoding='utf-8'))

    titles = []
    for rule in config['global_case_rules']:
        assert rule.startswith('【') and '】' in rule
        titles.append(rule[1:rule.index('】')])

    refs = [
        title
        for group in config['global_rule_groups']
        for title in group.get('rule_titles', [])
    ]

    assert len(titles) == len(set(titles))
    assert len(refs) == len(set(refs))
    assert set(refs) == set(titles)

