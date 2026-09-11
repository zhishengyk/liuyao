import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('package_corpus', Path(__file__).parents[1]/'scripts/package_corpus.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def corpus(root):
    files = {
        'book.md': '原问题与原反馈。',
        'data/sources.jsonl': json.dumps({'path': 'book.md'}),
        'data/canonical/sources.jsonl': json.dumps({'path': 'book.md'}),
        'data/ocr_corrections.json': '{}', 'data/xiangfa_outline.json': '{}',
        'data/proofread_pages/book/0001.json': '{}',
        'data/manual_slices/shards/book/approved.json': '{"units":[]}',
        'data/manual_slices/shards/book/draft.json': '{"status":"draft"}',
        'data/manual_slices/audits/native-current.json': '{"records":[]}',
        'data/manual_slices/audits/native-old.json': '{}',
        'data/knowledge.sqlite': 'generated database',
        'data/semantic-index/model.cache': 'model weights',
    }
    shard = 'data/manual_slices/shards/book/approved.json'
    manifest = {'assembled_from': [{'path': shard, 'sha256': hashlib.sha256(files[shard].encode()).hexdigest()}],
                'units': [{'cast': {'verification': {'evidence': 'data/manual_slices/audits/native-current.json'}}}]}
    files['data/manual_slices/book.json'] = json.dumps(manifest)
    for name, content in files.items():
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode())
    return files


def test_untracked_corpus_packages_reproducibly_without_drafts_or_runtime_state(tmp_path):
    root = tmp_path/'source'
    files = corpus(root)
    output = tmp_path/'corpus.zip'
    first = module.package(root, output)
    assert module.package(root, output) == first
    excluded = {'data/manual_slices/shards/book/draft.json',
                'data/manual_slices/audits/native-old.json',
                'data/knowledge.sqlite', 'data/semantic-index/model.cache'}
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == set(files) - excluded
        for name in archive.namelist():
            assert archive.read(name) == files[name].encode()
    assert first['file_count'] == len(files) - len(excluded)
    assert first['sha256'] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_changed_shard_cannot_be_published_with_stale_aggregate(tmp_path):
    root = tmp_path/'source'
    corpus(root)
    (root/'data/manual_slices/shards/book/approved.json').write_text('{"units":["new"]}')
    with pytest.raises(ValueError, match='Shard changed since assembly'):
        module.package(root, tmp_path/'corpus.zip')
    assert not (tmp_path/'corpus.zip').exists()


def test_quality_batches_follow_assembled_hashes_without_publishing_pending_work(tmp_path):
    root = tmp_path/'source'
    corpus(root)
    folder = root/'data/manual_slices/quality_reviews'
    shard = folder/'shards/book/001.json'
    draft = shard.with_name('002.json')
    shard.parent.mkdir(parents=True)
    shard.write_text('{"reviews":[]}', encoding='utf8')
    draft.write_text('{"batch":{"status":"draft"}}', encoding='utf8')
    relative = shard.relative_to(root).as_posix()
    (folder/'book.json').write_text(json.dumps({'assembled_from': [
        {'path': relative, 'sha256': hashlib.sha256(shard.read_bytes()).hexdigest()}]}), encoding='utf8')
    output = tmp_path/'quality.zip'
    module.package(root, output)
    with zipfile.ZipFile(output) as archive:
        assert relative in archive.namelist()
        assert draft.relative_to(root).as_posix() not in archive.namelist()
    shard.write_text('{"reviews":["changed"]}', encoding='utf8')
    with pytest.raises(ValueError, match='Shard changed since assembly'):
        module.package(root, tmp_path/'stale.zip')
