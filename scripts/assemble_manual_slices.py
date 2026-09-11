"""Merge reviewed manual batches, without deriving or approving any new cuts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from liuyao_mcp.canonical import load_document, resolve_spans


def positions(document, spans):
    offsets, offset = [], 0
    for line in document.lines:
        offsets.append(offset)
        offset += len(line) + 1
    selected = set()
    resolved = resolve_spans(document, spans)
    for span in resolved['source_spans']:
        start = offsets[span['start_line']-1] + span['start_column']
        end = offsets[span['end_line']-1] + span['end_column']
        selected.update(i for i in range(start, end) if not document.body[i].isspace())
    return selected


def assemble(root):
    root = Path(root).resolve()
    folder = root/'data/manual_slices'
    (folder/'seeds').mkdir(parents=True, exist_ok=True)
    reports = []
    for source in map(json.loads, (root/'data/canonical/sources.jsonl').read_text(encoding='utf8').splitlines()):
        sid = source['source_id']
        output = folder/f'{sid}.json'
        seed = folder/'seeds'/output.name
        if output.exists() and not seed.exists():
            previous = json.loads(output.read_text(encoding='utf8'))
            if not previous.get('assembled_from'):
                shutil.copy2(output, seed)
        files = sorted((folder/'shards'/sid).glob('*.json'))
        if not files:
            continue
        document = load_document(root, source, allow_partial=True)
        units, exclusions, issues, inputs, covered, skipped = [], [], [], [], set(), []
        for path in files:
            data = json.loads(path.read_text(encoding='utf8'))
            if data.get('status') in ('in_progress', 'draft', 'pending') or data.get('batch', {}).get('status') in ('in_progress', 'draft', 'pending'):
                skipped.append(path.relative_to(root).as_posix())
                continue
            if (data['schema_version'] != 'manual-slices-1' or data['source_id'] != sid
                    or data['source_sha256'] != document.source_sha256):
                raise ValueError(f'Shard source identity mismatch: {path}')
            inputs.append({'path': path.relative_to(root).as_posix(),
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            for group, target in [('units', units), ('exclusions', exclusions)]:
                for item in data.get(group, []):
                    current = positions(document, item['spans'])
                    if covered & current:
                        raise ValueError(f'Overlapping manual batch content: {path}: {item.get("unit_id", item.get("reason"))}')
                    covered.update(current)
                    target.append(item)
            issues.extend(data.get('audit_points', []))
        replaced = []
        if seed.exists():
            for item in json.loads(seed.read_text(encoding='utf8'))['units']:
                current = positions(document, item['spans'])
                if current <= covered:
                    replaced.append(item['unit_id'])
                elif current & covered:
                    raise ValueError(f'Partial seed/batch overlap needs manual resolution: {item["unit_id"]}')
                else:
                    units.append(item)
                    covered.update(current)
        ids = [item['unit_id'] for item in units]
        if len(ids) != len(set(ids)):
            raise ValueError(f'Duplicate manual unit IDs: {sid}')
        data = {'schema_version': 'manual-slices-1', 'source_id': sid,
                'source_sha256': document.source_sha256, 'assembled_from': inputs,
                'units': units, 'exclusions': exclusions, 'audit_points': issues,
                'seed_units_replaced_by_complete_batches': replaced}
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        reports.append({'source_id': sid, 'batches': len(inputs), 'skipped_unfinished_batches': skipped, 'units': len(units),
                        'exclusions': len(exclusions), 'replaced_seed_units': replaced,
                        'nonwhitespace_characters_accounted': len(covered)})
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    reports = assemble(args.root)
    path = args.root/'.local/rebuild/assembly-report.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(reports, ensure_ascii=False))


if __name__ == '__main__':
    main()
