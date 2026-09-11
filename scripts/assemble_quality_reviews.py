"""Assemble completed feedback-review batches; preserve earlier standalone reviews."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from liuyao_mcp.manual_ingest import _validate_quality


def assemble(root):
    root = Path(root).resolve()
    folder = root/'data/manual_slices/quality_reviews'
    sources = {s['source_id']: s for s in map(json.loads, (root/'data/canonical/sources.jsonl').read_text(encoding='utf8').splitlines())}
    reports = []
    for directory in sorted((folder/'shards').glob('*')):
        if not directory.is_dir():
            continue
        sid = directory.name
        source = sources[sid]
        source_sha = source.get('original_pdf_sha256', source['sha256'])
        output, seed = folder/f'{sid}.json', folder/'seeds'/f'{sid}.json'
        if output.exists() and not seed.exists() and not json.loads(output.read_text(encoding='utf8')).get('assembled_from'):
            seed.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output, seed)
        reviews, inputs, batch_ids = {}, [], set()
        for path in ([seed] if seed.exists() else []) + sorted(directory.glob('*.json')):
            blob = path.read_bytes()
            data = json.loads(blob)
            if data.get('batch', {}).get('status') in ('draft', 'in_progress', 'pending'):
                continue
            if (data['schema_version'] != 'case-quality-1' or data['source_id'] != sid
                    or data['source_sha256'] != source_sha):
                raise ValueError(f'Quality review source identity mismatch: {path}')
            local_ids = set()
            for review in data['reviews']:
                _validate_quality(review)
                uid = review['unit_id']
                if uid in local_ids or (path != seed and uid in batch_ids):
                    raise ValueError(f'Duplicate quality review unit: {uid}')
                local_ids.add(uid)
                if path != seed:
                    batch_ids.add(uid)
                reviews[uid] = review
            inputs.append({'path': path.relative_to(root).as_posix(), 'sha256': hashlib.sha256(blob).hexdigest()})
        result = {'schema_version': 'case-quality-1', 'source_id': sid, 'source_sha256': source_sha,
                  'assembled_from': inputs, 'reviews': [reviews[uid] for uid in sorted(reviews)]}
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        reports.append({'source_id': sid, 'reviewed_units': len(reviews), 'inputs': len(inputs)})
    return reports


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(assemble(args.root), ensure_ascii=False))
