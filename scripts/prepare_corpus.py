"""Restore hash-pinned corpus assets from GitHub Releases for local builds."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import urllib.request
import zipfile


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(lock_path, destination, cache, include_reference=False):
    lock = json.loads(Path(lock_path).read_text(encoding='utf8'))
    if lock['schema_version'] != 1:
        raise ValueError('Unsupported corpus lock version')
    destination, cache = Path(destination).resolve(), Path(cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    restored = existing = 0
    selected = [a for a in lock['assets'] if a['kind'] == 'corpus' or include_reference]
    for asset in selected:
        archive_path = cache/(asset['sha256']+'.zip')
        if not archive_path.is_file() or sha256(archive_path) != asset['sha256']:
            temporary = archive_path.with_suffix('.download')
            request = urllib.request.Request(asset['url'], headers={'Accept': 'application/octet-stream',
                                                                   'User-Agent': 'liuyao-corpus/1'})
            with urllib.request.urlopen(request, timeout=60) as source, temporary.open('wb') as output:
                shutil.copyfileobj(source, output)
            if temporary.stat().st_size != asset['size'] or sha256(temporary) != asset['sha256']:
                temporary.unlink()
                raise ValueError('Downloaded corpus does not match its locked hash')
            temporary.replace(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            entries = []
            for name in archive.namelist():
                parts = PurePosixPath(name)
                target = (destination/name).resolve()
                if parts.is_absolute() or '..' in parts.parts or not target.is_relative_to(destination):
                    raise ValueError('Corpus archive contains a path outside the destination')
                if name.endswith('/'):
                    continue
                content = archive.read(name)
                if target.exists() and target.read_bytes() != content:
                    raise ValueError(f'Local corpus file was modified: {name}; restore into a clean directory')
                entries.append((target, content))
            for target, content in entries:
                if target.exists():
                    existing += 1
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                restored += 1
    return {'corpus_snapshot': lock['corpus_snapshot'], 'assets': len(selected),
            'restored_files': restored, 'unchanged_files': existing}


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=root/'data/corpus.lock.json')
    parser.add_argument('--destination', type=Path, default=root)
    parser.add_argument('--cache', type=Path, default=root/'.local/corpus-cache')
    parser.add_argument('--include-reference', action='store_true', help='Also restore the full document and audit archive')
    args = parser.parse_args()
    print(json.dumps(prepare(args.lock, args.destination, args.cache, args.include_reference), ensure_ascii=False))
