import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'assemble_quality_reviews', Path(__file__).parents[1]/'scripts/assemble_quality_reviews.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf8')


def review(uid, status='eligible'):
    return {'unit_id': uid, 'unit_text_sha256': 'b'*64, 'status': status,
            'reason': 'Original question and reported outcome checked.', 'reviewer': 'test'}


def setup(root):
    write(root/'data/canonical/sources.jsonl', {'source_id': 'book', 'sha256': 'a'*64})
    folder = root/'data/manual_slices/quality_reviews'
    base = {'schema_version': 'case-quality-1', 'source_id': 'book', 'source_sha256': 'a'*64}
    return folder, base


def test_preserve_standalone_reviews_and_apply_completed_batches_idempotently(tmp_path):
    folder, base = setup(tmp_path)
    output = folder/'book.json'
    write(output, {**base, 'reviews': [review('old'), review('rechecked', 'pending')]})
    original = output.read_bytes()
    shard = folder/'shards/book/001.json'
    write(shard, {**base, 'reviews': [review('new'), review('rechecked')]})
    write(folder/'shards/book/draft.json', {'batch': {'status': 'draft'}})
    assert module.assemble(tmp_path) == [{'source_id': 'book', 'reviewed_units': 3, 'inputs': 2}]
    first = output.read_bytes()
    data = json.loads(first)
    assert {r['unit_id']: r['status'] for r in data['reviews']} == {
        'old': 'eligible', 'new': 'eligible', 'rechecked': 'eligible'}
    assert (folder/'seeds/book.json').read_bytes() == original
    for item in data['assembled_from']:
        assert hashlib.sha256((tmp_path/item['path']).read_bytes()).hexdigest() == item['sha256']
    module.assemble(tmp_path)
    assert output.read_bytes() == first


@pytest.mark.parametrize('bad', ['duplicate', 'source'])
def test_conflicting_batches_fail_without_overwriting_previous_aggregate(tmp_path, bad):
    folder, base = setup(tmp_path)
    write(folder/'book.json', {**base, 'reviews': [review('old')]})
    write(folder/'shards/book/001.json', {**base, 'reviews': [review('new')]})
    module.assemble(tmp_path)
    previous = (folder/'book.json').read_bytes()
    second = {**base, 'reviews': [review('new' if bad == 'duplicate' else 'other')]}
    if bad == 'source':
        second['source_sha256'] = 'c'*64
    write(folder/'shards/book/002.json', second)
    with pytest.raises(ValueError, match='Duplicate quality|source identity mismatch'):
        module.assemble(tmp_path)
    assert (folder/'book.json').read_bytes() == previous
