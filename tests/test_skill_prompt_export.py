"""Verbatim, complete range/context routing and deterministic regeneration."""
import importlib.util
import json
from pathlib import Path
import sqlite3

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
        'supplemental_ids': {'objects': ['b']}, 'selection_policy': 'verbatim'}), encoding='utf-8')
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
