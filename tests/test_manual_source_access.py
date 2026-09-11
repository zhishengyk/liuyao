import hashlib
import json

from liuyao_mcp.ingest import read_spans
from liuyao_mcp.manual_ingest import build_database
from liuyao_mcp.retrieval import get_source, search_knowledge


def test_manual_quotes_keep_columns_and_inferred_topics_do_not_filter(tmp_path):
    text = '用神受伤是论述术语。\n作者说甲。反馈说乙。\n'
    (tmp_path/'book.md').write_bytes(text.encode('utf8'))
    sha = hashlib.sha256(text.encode()).hexdigest()
    source = {'source_id': 'manual', 'title': '手动切片例', 'path': 'book.md',
              'source_type': 'native_text', 'method_hint': 'lifa', 'sha256': sha,
              'pdf_pages': None}
    (tmp_path/'data/canonical').mkdir(parents=True)
    (tmp_path/'data/canonical/sources.jsonl').write_text(json.dumps(source), encoding='utf8')
    (tmp_path/'data/manual_slices').mkdir()
    review = {'status': 'approved', 'basis': 'direct_source_read', 'reviewer': 'test'}
    units = [{'unit_id': 'manual.rule1', 'kind': 'rule', 'title': '术语', 'method': 'lifa',
              'scope': 'common', 'spans': [{'page': None, 'start_line': 1, 'end_line': 1}], 'review': review},
             {'unit_id': 'manual.rule2', 'kind': 'rule', 'title': '作者断语', 'method': 'lifa',
              'scope': 'common', 'spans': [{'page': None, 'start_line': 2, 'end_line': 2,
                                           'start_column': 0, 'end_column': 5}], 'review': review}]
    manifest = {'schema_version': 'manual-slices-1', 'source_id': 'manual',
                'source_sha256': sha, 'units': units}
    (tmp_path/'data/manual_slices/manual.json').write_text(json.dumps(manifest), encoding='utf8')
    database = tmp_path/'knowledge.sqlite'
    build_database(tmp_path, database, allow_partial=True)
    found = search_knowledge('用神受伤', kind='rule', db_path=database, retrieval_mode='bm25')
    assert not found['topic_filter_applied'] and found['topic'] is None
    assert 'health' in found['inferred_topic_hints']
    assert any(item['evidence_id'] == 'manual.rule1' for item in found['items'])
    source = get_source('manual.rule2', db_path=database)
    assert source['text'] == '作者说甲。'
    assert source['source_spans'][0]['end_column'] == 5
    assert source['review']['status'] == 'approved'
    context = get_source('manual.rule2', context_lines=1, db_path=database)
    assert '反馈说乙。' in context['text']
    assert 'canonical_unit_spans' in context and 'canonical_spans' not in context


def test_column_slices_are_consistent_across_lines():
    lines = ['前缀甲', '乙中间', '丙后缀']
    assert read_spans(lines, [{'start_line': 1, 'end_line': 3, 'start_column': 2, 'end_column': 1}]) == '甲\n乙中间\n丙'
    assert read_spans(lines, [{'start_line': 2, 'end_line': 2}]) == '乙中间'
