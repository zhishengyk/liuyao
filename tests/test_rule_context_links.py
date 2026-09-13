import copy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from liuyao_mcp.canonical import load_document, resolve_spans
from liuyao_mcp.common import digest
from liuyao_mcp.manual_ingest import build_database
from liuyao_mcp.retrieval import get_source, search_knowledge


LINKS = [
    ('zengshan_pingshi_dxj-l8974-effective-tomb', 'zengshan_pingshi_dxj-l8982-tomb-topic-applications', 8982, 8982, '功名'),
    ('liuyao_zixiu_dxj.full.l9140.rule', 'liuyao_zixiu_dxj.full.l9168.rule', 9168, 9184, '落选'),
    ('liuyao_zixiu_dxj.full.l9168.rule', 'liuyao_zixiu_dxj.full.l9140.rule', 9140, 9164, '通知书'),
]


@pytest.fixture(scope='module')
def context_database(tmp_path_factory):
    repository = Path(__file__).resolve().parents[1]
    root = tmp_path_factory.mktemp('rule-context-links')
    ids = {unit for link in LINKS for unit in link[:2]}
    sources, units, documents = [], {}, {}
    registry = repository/'data/canonical/sources.jsonl'
    for source in map(json.loads, registry.read_text(encoding='utf8').splitlines()):
        if source['source_id'] not in ('zengshan_pingshi_dxj', 'liuyao_zixiu_dxj'):
            continue
        manifest = json.loads((repository/'data/manual_slices'/f"{source['source_id']}.json").read_text(encoding='utf8'))
        chosen = [unit for unit in manifest['units'] if unit['unit_id'] in ids]
        for entry in manifest['assembled_from']:
            shard_path = repository/entry['path']
            shard = json.loads(shard_path.read_text(encoding='utf8'))
            relevant = [unit for unit in shard['units'] if unit['unit_id'] in ids]
            if relevant:
                assert hashlib.sha256(shard_path.read_bytes()).hexdigest() == entry['sha256']
                assert all(unit == next(item for item in chosen if item['unit_id'] == unit['unit_id']) for unit in relevant)
        units.update({unit['unit_id']: unit for unit in chosen})
        documents[source['source_id']] = load_document(repository, source)
        target = root/source['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository/source['path'], target)
        destination = root/'data/manual_slices'/f"{source['source_id']}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        isolated = {key: manifest[key] for key in ('schema_version', 'source_id', 'source_sha256')}
        isolated['units'] = copy.deepcopy(chosen)
        destination.write_text(json.dumps(isolated, ensure_ascii=False), encoding='utf8')
        sources.append(source)
    registry = root/'data/canonical/sources.jsonl'
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text('\n'.join(json.dumps(source, ensure_ascii=False) for source in sources), encoding='utf8')
    shared = repository/'data/knowledge.sqlite'
    before = hashlib.sha256(shared.read_bytes()).hexdigest()
    database = root/'contexts.sqlite'
    build_database(root, database, allow_partial=True)
    assert hashlib.sha256(shared.read_bytes()).hexdigest() == before
    return database, units, documents


@pytest.mark.parametrize('target,donor,start,end,context_query', LINKS)
def test_linked_rules_return_and_index_the_complete_canonical_conditions(context_database, target, donor, start, end, context_query):
    database, units, documents = context_database
    source_id = 'zengshan_pingshi_dxj' if target.startswith('zengshan_') else 'liuyao_zixiu_dxj'
    document = documents[source_id]
    expected = resolve_spans(document, units[donor]['spans'])['exact_text']
    primary = resolve_spans(document, units[target]['spans'])['exact_text']
    assert units[donor]['kind'] == 'rule' and len(units[target]['context_spans']) == 1
    source = get_source(target, db_path=database, max_chars=50000)
    assert source['text'] == primary and not source['has_more']
    assert not source['required_contexts_omitted'] and 'structured_case' not in source
    context = source['required_contexts'][0]
    assert context['text'] == context['exact_text'] == expected
    assert context['quote_sha256'] == digest(expected)
    assert [(span['start_line'], span['end_line']) for span in context['canonical_spans']] == [(start, end)]
    assert context['author'] == ('李文辉（觉子）' if source_id.startswith('zengshan_') else '王虎应')
    assert '新评释' not in context['text']
    assert context_query not in primary and context_query in expected
    found = search_knowledge(context_query, kind='rule', outline_ids=['manual_unit:'+target],
                             limit=1, max_chars=50000, retrieval_mode='bm25', db_path=database)
    assert found['items'][0]['evidence_id'] == target
    assert found['items'][0]['quote'] == primary
    assert found['items'][0]['required_contexts'][0]['text'] == expected
    assert found['items'][0]['content_role'] == 'theory'


@pytest.mark.parametrize('target,donor,start,end,context_query', LINKS)
def test_small_budgets_report_missing_conditions_instead_of_silently_dropping_them(context_database, target, donor, start, end, context_query):
    database, _, _ = context_database
    source = get_source(target, db_path=database, max_chars=1000)
    assert source['text'] and not source['has_more']
    assert source['required_contexts'] == [] and source['required_contexts_omitted']
    assert '未完整返回' in source['context_read_note']
    found = search_knowledge(context_query, kind='rule', outline_ids=['manual_unit:'+target],
                             limit=1, max_chars=1000, retrieval_mode='bm25', db_path=database)
    assert not found['items'] and found['has_more']
    assert [item['evidence_id'] for item in found['budget_skipped']] == [target]
