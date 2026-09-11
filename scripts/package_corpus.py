"""Package a validated manual corpus for Release distribution, without Git data."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def package(root, output):
    root, output = Path(root).resolve(), Path(output)
    names = {'data/sources.jsonl', 'data/ocr_corrections.json', 'data/xiangfa_outline.json'}
    for folder in ('data/canonical', 'data/proofread_pages'):
        names.update(p.relative_to(root).as_posix() for p in (root/folder).rglob('*') if p.is_file())
    for registry in ('data/sources.jsonl', 'data/canonical/sources.jsonl'):
        for line in (root/registry).read_text(encoding='utf8').splitlines():
            source = json.loads(line)
            names.add(source['path'])
    bound_audits, expected_shards = set(), {}
    folder = root/'data/manual_slices'
    for manifest_path in sorted([*folder.glob('*.json'), *(folder/'quality_reviews').glob('*.json')]):
        names.add(manifest_path.relative_to(root).as_posix())
        manifest = json.loads(manifest_path.read_text(encoding='utf8'))
        for shard in manifest.get('assembled_from', []):
            names.add(shard['path'])
            expected_shards[shard['path']] = shard['sha256']
        for unit in manifest.get('units', []):
            for cast in [unit.get('cast') or {}, *unit.get('additional_casts', [])]:
                audit = cast.get('verification', {}).get('evidence')
                if audit:
                    bound_audits.add(audit)
    for subfolder in ('seeds', 'audits'):
        for path in (folder/subfolder).rglob('*'):
            if not path.is_file() or path.suffix not in ('.json', '.md'):
                continue
            name = path.relative_to(root).as_posix()
            if subfolder == 'audits' and path.name.startswith('native-') and name not in bound_audits:
                continue
            names.add(name)
    names.update(bound_audits)
    contents = {}
    for name in sorted(names):
        path = (root/name).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f'Corpus input leaves project root: {name}')
        blob = path.read_bytes()
        if name in expected_shards and hashlib.sha256(blob).hexdigest() != expected_shards[name]:
            raise ValueError(f'Shard changed since assembly: {name}')
        contents[name] = blob
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, blob in contents.items():
            info = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, blob)
    return {'kind': 'corpus', 'name': output.name,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'size': output.stat().st_size,
            'file_count': len(contents), 'uncompressed_size': sum(map(len, contents.values()))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.root, args.output), ensure_ascii=False, indent=2))
