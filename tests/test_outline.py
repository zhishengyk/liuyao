import json
import sqlite3

import pytest

from liuyao_mcp.common import database_path, dumps
from liuyao_mcp.ingest import read_spans
from liuyao_mcp.retrieval import get_outline, get_source, search_knowledge


def test_manual_directory_pagination_and_exact_original_text():
    books = get_outline()['items']
    with sqlite3.connect(database_path()) as db:
        sources = {sid: json.loads(meta) for sid, meta in db.execute('SELECT id,metadata FROM sources')}
    assert len(books) == len(sources) == 6
    assert {b['source_id'] for b in books} == set(sources)
    assert all(b['title_basis'] == 'source_manifest' for b in books)
    parent = next(b['node_id'] for b in books if b['source_id'] == 'liuyao_xiangfa_jinjie_xia')
    first = get_outline(parent_id=parent, limit=2)
    assert first['has_more'] and first['next_offset'] == 2
    second = get_outline(parent_id=parent, offset=2, limit=2)
    combined = get_outline(parent_id=parent, limit=4)['items']
    assert first['items'] + second['items'] == combined
    node = first['items'][0]
    assert node['title_basis'] == 'manual_unit_label'
    source = get_source(node['node_id'], max_chars=500000)
    with sqlite3.connect(database_path()) as db:
        body = db.execute('SELECT body FROM sources WHERE id=?', (node['source_id'],)).fetchone()[0]
    assert source['text'] == read_spans(body.split('\n'), node['source_spans'])
    assert source['source']['total_pdf_pages'] == 237


def test_manual_unit_bounds_and_all_evidence_links():
    with sqlite3.connect(database_path()) as db:
        nodes = {nid: json.loads(p) for nid, p in db.execute('SELECT id,payload FROM outline_nodes')}
        records = [json.loads(p) for p, in db.execute('SELECT payload FROM chunks UNION ALL SELECT payload FROM cases')]
        assert len(nodes) == 6 + len({r.get('unit_id', r.get('id')) for r in records})
        for record in records:
            case = 'case_id' in record
            eid = record['case_id'] if case else record['id']
            source = record['source'] if case else record
            node = nodes[record['outline']['node_id']]
            spans = source['spans'] if case else record['source_spans']
            assert node['source_id'] == source['source_id']
            assert all(node['start_line'] <= span['start_line'] <= span['end_line'] <= node['end_line'] for span in spans)
            linked = {r[0] for r in db.execute('SELECT node_id FROM evidence_outline WHERE evidence_id=?', (eid,))}
            assert linked == {p['node_id'] for p in record['outline']['path']}
            assert node['title_basis'] == 'manual_unit_label'


def test_rule_parent_contexts_and_cross_topic_scene_search():
    with sqlite3.connect(database_path()) as db:
        rules = [json.loads(p) for p, in db.execute('SELECT payload FROM chunks')]
        rule = next(r for r in rules if r['method'] == 'xiangfa' and r['required_contexts']
                    and len(r['text']) + sum(len(dumps(c)) for c in r['required_contexts']) > 1000)
        source_lines = db.execute('SELECT body FROM sources WHERE id=?', (rule['source_id'],)).fetchone()[0].split('\n')
    source = get_source(rule['id'], max_chars=500000)
    assert source['required_contexts'] == rule['required_contexts']
    for context in source['required_contexts']:
        assert context['text'] == read_spans(source_lines, context['source_spans'])
    small = get_source(rule['id'], max_chars=1000)
    assert len(small['text']) + sum(len(dumps(c)) for c in small['required_contexts']) <= 1000
    assert small['required_contexts_omitted'] and small['context_read_note']
    params = dict(query='工作 官鬼 求职', kind='case', method='xiangfa', limit=4, max_chars=100000)
    a = search_knowledge(**params, topic='job')
    b = search_knowledge(**params, topic='relationship')
    assert not a['topic_filter_applied'] and not b['topic_filter_applied']
    assert [i['evidence_id'] for i in a['items']] == [i['evidence_id'] for i in b['items']]


def test_directory_scope_browse_followup_and_validation():
    book = 'manual_book:liuyao_xiangfa_jinjie_xia'
    params = dict(query='', method='xiangfa', kind='case', outline_ids=[book], limit=3, max_chars=100000)
    first = search_knowledge(**params)
    ids = [i['evidence_id'] for i in first['items']]
    assert len(ids) == 3
    for item in first['items']:
        assert book in {p['node_id'] for p in item['outline']['path']}
        assert item['case']['quality']['status'] == 'eligible'
    second = search_knowledge(**params, exclude_case_ids=ids)
    assert not set(ids) & {i['evidence_id'] for i in second['items']}
    for item in second['items']:
        assert not set(ids) & set(item['related_cases']['case_ids'])
    with pytest.raises(ValueError, match='未知目录'):
        search_knowledge('', outline_ids=['missing'])
    with pytest.raises(ValueError, match='来源不符'):
        get_outline(source_id='liuyao_xiangfa_jinjie_shang', parent_id=book)
