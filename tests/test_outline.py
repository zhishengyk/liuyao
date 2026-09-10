import json
import sqlite3

import pytest

from liuyao_mcp.common import database_path
from liuyao_mcp.retrieval import get_outline, get_source, search_knowledge


def test_pdf_verified_directory_and_original_text():
    books = get_outline()['items']
    assert {b['node_id'] for b in books} == {'xf_shang', 'xf_xia'}
    assert {b['pdf_verification']['pages'] for b in books} == {317, 237}
    children = get_outline(parent_id='xf_shang_c01')['items']
    assert len(children) == 7
    assert children[3]['title'] == '第四节 螣蛇'
    assert children[3]['pdf_pages'][0] == 91
    assert children[3]['toc_printed_page'] == 86
    source = get_source('xf_xia_c09', max_chars=1000)
    assert source['outline_node']['title'] == '第九章 隔山化爻'
    assert '隔山化区' in source['text']  # PDF titles must not overwrite quoted OCR.
    vacancy = get_source('xf_xia_c06_u03', max_chars=1000)['outline_node']
    assert vacancy['toc_printed_page'] == 82 and vacancy['pdf_pages'][0] == 83
    page = get_outline(parent_id='xf_shang_c01', limit=2)
    assert page['has_more'] and page['next_offset'] == 2
    assert get_outline(parent_id='xf_shang_c01', offset=2, limit=2)['items'][1]['node_id'] == 'xf_shang_c01_s04'


def test_corrected_boundaries_and_all_evidence_links():
    with sqlite3.connect(database_path()) as db:
        nodes = {nid: json.loads(p) for nid, p in db.execute('SELECT id,payload FROM outline_nodes')}
        assert len(nodes) == 121
        for sid, line, expected in [('liuyao_xiangfa_jinjie_shang', 3882, 'xf_shang_c01_s04_u01'),
                                    ('liuyao_xiangfa_jinjie_shang', 12126, 'xf_shang_c03_s05_u01'),
                                    ('liuyao_xiangfa_jinjie_xia', 9611, 'xf_xia_c11_s07')]:
            row = db.execute('SELECT payload FROM chunks WHERE source_id=? AND start_line<=? AND end_line>=?',
                             (sid, line, line)).fetchone()
            assert json.loads(row[0])['outline']['node_id'] == expected
        for eid, sid, start, end, payload in db.execute('SELECT id,source_id,start_line,end_line,payload FROM chunks'):
            chunk = json.loads(payload)
            if 'outline' not in chunk:
                continue
            node = nodes[chunk['outline']['node_id']]
            assert node['source_id'] == sid
            assert node['start_line'] <= start <= end <= node['end_line']
            assert start >= nodes[chunk['outline']['path'][0]['node_id']]['body_start_line']
            linked = {r[0] for r in db.execute('SELECT node_id FROM evidence_outline WHERE evidence_id=?', (eid,))}
            assert linked == {p['node_id'] for p in chunk['outline']['path']}


def test_scene_search_contexts_and_cross_topic_cases():
    found = search_knowledge('材料审核', method='xiangfa', limit=5)
    target = next(i for i in found['items'] if i['outline']['node_id'] == 'xf_shang_c01_s02_u03')
    assert target['related_cases']['total_cases'] > 0
    source = get_source(target['evidence_id'], max_chars=10000)
    assert 'xf_shang_c01_s02' in {c['node_id'] for c in source['outline_context']}
    with sqlite3.connect(database_path()) as db:
        original = db.execute('SELECT body FROM sources WHERE id=?', (target['source_id'],)).fetchone()[0].splitlines()
    for context in source['outline_context']:
        assert context['text'] == '\n'.join(original[context['start_line']-1:context['end_line']])
    small = get_source(target['evidence_id'], max_chars=1000)
    assert len(small['text']) + sum(len(c['text']) for c in small['outline_context']) <= 1000
    assert small['outline_context_omitted']
    params = dict(query='工作 官鬼 求职', kind='case', method='xiangfa', limit=4, max_chars=100000)
    a = search_knowledge(**params, topic='job')
    b = search_knowledge(**params, topic='relationship')
    assert not a['topic_filter_applied'] and not b['topic_filter_applied']
    assert [i['evidence_id'] for i in a['items']] == [i['evidence_id'] for i in b['items']]


def test_directory_scope_browse_followup_and_validation():
    params = dict(query='', method='xiangfa', kind='case', outline_ids=['xf_shang_c01_s02'], limit=3, max_chars=100000)
    first = search_knowledge(**params)
    ids = [i['evidence_id'] for i in first['items']]
    assert len(ids) == 3
    for item in first['items']:
        assert 'xf_shang_c01_s02' in {p['node_id'] for p in item['outline']['path']}
    second = search_knowledge(**params, exclude_case_ids=ids)
    assert not set(ids) & {i['evidence_id'] for i in second['items']}
    for item in second['items']:
        assert not set(ids) & set(item['related_cases']['case_ids'])
    with pytest.raises(ValueError, match='未知目录'):
        search_knowledge('', outline_ids=['missing'])
    with pytest.raises(ValueError, match='来源不符'):
        get_outline(source_id='liuyao_xiangfa_jinjie_xia', parent_id='xf_shang_c01')
