import hashlib
import json
from pathlib import Path

import pytest

from liuyao_mcp.canonical import load_document, resolve_spans
from liuyao_mcp.manual_ingest import build_database
from liuyao_mcp.retrieval import get_source, search_knowledge


ROOT = Path(__file__).resolve().parents[1]
PAIRS = [
    ('liuyao_lifa_jinjie.manual.p0226_mother_health',
     'liuyao_xiangfa_jinjie_shang.manual.p0020_mother_health',
     'liuyao_lifa_jinjie.event.p0226_mother_health', '小孩身体', 2),
    ('liuyao_lifa_jinjie.manual.p0250_father_health',
     'liuyao_xiangfa_jinjie_shang.manual.p0087_father_health',
     'liuyao_lifa_jinjie.event.p0250_father_health', '孩子 病', 3),
]


@pytest.fixture(scope='module')
def grouped_database(tmp_path_factory):
    # Rebuild from the actual approved manifests, never the shared product DB.
    path = tmp_path_factory.mktemp('cross-book-event-groups') / 'knowledge.sqlite'
    build_database(ROOT, path)
    return path


@pytest.mark.parametrize('first,second,event_id,query,limit', PAIRS)
def test_cross_book_event_occupies_one_search_slot(grouped_database, first, second, event_id, query, limit):
    result = search_knowledge(query, kind='case', topic='health', subtopic='health/relative',
                              require_valid_chart=True, limit=limit, max_chars=30000,
                              retrieval_mode='bm25', db_path=grouped_database)
    selected = [item for item in result['items'] if item['evidence_id'] in (first, second)]
    assert len(selected) == 1
    for case_id in (first, second):
        case = get_source(case_id, db_path=grouped_database)['structured_case']
        assert case['duplicate_group'] == event_id
        assert case['duplicate_candidates'] == [second if case_id == first else first]


@pytest.mark.parametrize('first,second,event_id,query,limit', PAIRS)
@pytest.mark.parametrize('excluded_member', [0, 1])
def test_excluding_either_source_excludes_whole_event(grouped_database, first, second, event_id,
                                                     query, limit, excluded_member):
    result = search_knowledge('身体', kind='case', require_valid_chart=True,
                              outline_ids=['manual_unit:' + first, 'manual_unit:' + second],
                              exclude_case_ids=[(first, second)[excluded_member]],
                              limit=10, retrieval_mode='bm25', db_path=grouped_database)
    assert result['items'] == []


@pytest.mark.parametrize('first,second,event_id,query,limit', PAIRS)
def test_both_source_texts_charts_and_reviews_remain_accessible(grouped_database, first, second,
                                                              event_id, query, limit):
    registry = [json.loads(line) for line in (ROOT / 'data/canonical/sources.jsonl').read_text(encoding='utf8').splitlines()]
    for case_id in (first, second):
        source_id = case_id.split('.manual.')[0]
        manifest = json.loads((ROOT / f'data/manual_slices/{source_id}.json').read_text(encoding='utf8'))
        unit = next(unit for unit in manifest['units'] if unit['unit_id'] == case_id)
        document = load_document(ROOT, next(source for source in registry if source['source_id'] == source_id))
        original = resolve_spans(document, unit['spans'])
        source = get_source(case_id, max_chars=30000, db_path=grouped_database)
        case = source['structured_case']
        assert source['text'] == original['exact_text']
        assert source['source_spans'] == original['source_spans']
        assert source['source']['sha256'] == document.canonical_text_sha256
        assert case['cast']['line_values'] == unit['cast']['line_values']
        assert case['cast']['verification'] == unit['cast']['verification']
        assert case['extraction']['chart_validation'] == 'calculated'
        assert case['extraction']['source_chart_independently_verified'] is True
        assert case['quality']['status'] == 'eligible'
        assert unit['event_id'] == event_id
    upper = json.loads((ROOT / 'data/manual_slices/liuyao_xiangfa_jinjie_shang.json').read_text(encoding='utf8'))
    for part in upper['assembled_from']:
        if part['path'].endswith(('/0001-0040.json', '/0071-0091.json')):
            assert hashlib.sha256((ROOT / part['path']).read_bytes()).hexdigest() == part['sha256']
