"""Bind completed independent audits to assembled casts; never approve new casts."""
import argparse
import hashlib
import json
from pathlib import Path

from liuyao_mcp.canonical import load_document, resolve_spans
from liuyao_mcp.manual_ingest import _verified_cast


def attach(root, audit_paths):
    root = Path(root).resolve()
    proofs = {}
    for path in audit_paths:
        path = path.resolve()
        blob = path.read_bytes()
        audit = json.loads(blob)
        for record in audit['records']:
            if record['status'] != 'passed':
                continue
            if record['unit_id'] in proofs:
                raise ValueError(f"Duplicate audit record: {record['unit_id']}")
            proofs[record['unit_id']] = {
                'status': 'verified', 'basis': audit['basis'],
                'evidence': path.relative_to(root).as_posix(),
                'evidence_sha256': hashlib.sha256(blob).hexdigest(),
                'reviewer': 'root:audit-binding',
            }
    outputs, bound = [], []
    for source in map(json.loads, (root/'data/canonical/sources.jsonl').read_text(encoding='utf8').splitlines()):
        path = root/'data/manual_slices'/f"{source['source_id']}.json"
        if not path.exists():
            continue
        manifest = json.loads(path.read_text(encoding='utf8'))
        document = load_document(root, source, allow_partial=True)
        changed = False
        for unit in manifest['units']:
            if unit['kind'] != 'case':
                continue
            for index, cast in enumerate([unit.get('cast') or {}] + unit.get('additional_casts', [])):
                uid = unit['unit_id'] + (f'.cast{index+1}' if index else '')
                if uid not in proofs:
                    continue
                cast['verification'] = proofs[uid]
                chart = resolve_spans(document, cast.get('diagram_spans') or unit['parts']['chart'])
                _verified_cast(root, document, {**unit, 'unit_id': uid}, cast, chart)
                changed = True
                bound.append(uid)
        if changed:
            outputs.append((path, manifest))
    missing = set(proofs) - set(bound)
    if missing:
        raise ValueError(f'Audited casts absent from assembled manifests: {sorted(missing)}')
    for path, manifest in outputs:
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    return {'bound_casts': len(bound), 'manifests_updated': len(outputs)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audits', nargs='+', type=Path)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(attach(args.root, args.audits)))
