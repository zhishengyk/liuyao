import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('prepare_corpus', Path(__file__).resolve().parents[1]/'scripts/prepare_corpus.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture_lock(tmp_path, files):
    assets = []
    for kind, entries in files.items():
        path = tmp_path/(kind+'.zip')
        with zipfile.ZipFile(path, 'w') as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        assets.append({'kind': kind, 'url': path.as_uri(), 'size': path.stat().st_size,
                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    lock = tmp_path/'lock.json'
    lock.write_text(json.dumps({'schema_version': 1, 'corpus_snapshot': 'fixture', 'assets': assets}))
    return lock


def test_pinned_restore_is_repeatable_and_reference_archive_is_optional(tmp_path):
    lock = fixture_lock(tmp_path, {'corpus': {'data/book.json': 'verified'},
                                   'reference': {'Markdown归档/notes.md': 'reference'}})
    dest, cache = tmp_path/'restored', tmp_path/'cache'
    assert module.prepare(lock, dest, cache)['restored_files'] == 1
    assert not (dest/'Markdown归档').exists()
    assert module.prepare(lock, dest, cache)['unchanged_files'] == 1
    result = module.prepare(lock, dest, cache, include_reference=True)
    assert result['restored_files'] == 1 and result['unchanged_files'] == 1
    assert (dest/'Markdown归档/notes.md').read_text() == 'reference'


def test_local_manual_edits_are_not_overwritten(tmp_path):
    lock = fixture_lock(tmp_path, {'corpus': {'data/book.json': 'source'}})
    dest = tmp_path/'restored'
    module.prepare(lock, dest, tmp_path/'cache')
    target = dest/'data/book.json'
    target.write_text('manual edit')
    with pytest.raises(ValueError, match='Local corpus file was modified'):
        module.prepare(lock, dest, tmp_path/'cache')
    assert target.read_text() == 'manual edit'


def test_bad_download_hash_and_escaping_paths_cannot_restore_files(tmp_path):
    lock = fixture_lock(tmp_path, {'corpus': {'data/book.json': 'source'}})
    manifest = json.loads(lock.read_text())
    manifest['assets'][0]['sha256'] = '0'*64
    lock.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='locked hash'):
        module.prepare(lock, tmp_path/'restored', tmp_path/'cache')
    assert not (tmp_path/'restored').exists()
    lock = fixture_lock(tmp_path, {'corpus': {'../escape.txt': 'outside'}})
    with pytest.raises(ValueError, match='outside the destination'):
        module.prepare(lock, tmp_path/'restored', tmp_path/'cache')
    assert not (tmp_path/'escape.txt').exists()
