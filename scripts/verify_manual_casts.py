"""Independently compare manually entered native casts with literal chart rows."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from liuyao_mcp.canonical import load_document, resolve_spans
from liuyao_mcp.chart import BRANCHES, STEMS, build_chart


ROW = re.compile(rf'(父母|兄弟|子孙|妻财|官鬼)[{STEMS}]?([{BRANCHES}])[木火土金水]?')
INCOMPLETE_ROW = re.compile(r'(父母|兄弟|子孙|妻财|官鬼)[木火土金水]\s*[′″○Ｏ×ＸXx、]')


def explicit_value(text):
    """Read a literal symbol from one label's column, without repairing glyphs."""
    if any(sign in text for sign in ('×', 'Ｘ', 'X', 'x')):
        return 0
    if any(sign in text for sign in ('○', 'Ｏ')):
        return 3
    if '″' in text or '、、' in text:
        return 0 if '动' in text else 2
    if '′' in text or '、' in text:
        return 3 if '动' in text else 1
    return None


def verify(document, unit):
    cast = unit['cast']
    text = resolve_spans(document, cast.get('diagram_spans') or unit['parts']['chart'])['exact_text']
    for key in ('month_branch', 'day_ganzhi'):
        spans = cast.get('field_spans', {}).get(key, [])
        literal = resolve_spans(document, spans)['exact_text'] if spans else ''
        if cast[key] not in re.sub(r'\s+', '', literal):
            raise ValueError(f"{unit['unit_id']}: {key} is not supported by its literal date span")
    rows = [(line, list(ROW.finditer(line))) for line in text.splitlines()]
    rows = [(line, matches) for line, matches in rows if matches or INCOMPLETE_ROW.search(line)]
    if len(rows) != 6:
        raise ValueError(f"{unit['unit_id']}: expected six explicit diagram rows")
    parsed = []
    for position, (line, matches) in enumerate(reversed(rows), 1):
        if not matches:
            raise ValueError(f"{unit['unit_id']}: incomplete literal label at {position}: {line}")
        columns = [line[label.start():matches[i+1].start() if i+1 < len(matches) else len(line)]
                   for i, label in enumerate(matches)]
        # Native charts place a symbol-free hidden spirit before the primary row,
        # with （伏）, 伏藏, /, or just spacing. Its label is checked below, not discarded.
        primary_index = 1 if explicit_value(columns[0]) is None and len(columns) > 1 else 0
        label, main = matches[primary_index], columns[primary_index]
        value = explicit_value(main)
        if value is None:
            raise ValueError(f"{unit['unit_id']}: unsupported explicit symbol at {position}")
        if len(matches) > primary_index + 2:
            raise ValueError(f"{unit['unit_id']}: unexpected extra diagram labels at {position}")
        if value != cast['line_values'][position-1]:
            raise ValueError(f"{unit['unit_id']}: literal line_value conflict at {position}: "
                             f"source={value}, manual={cast['line_values'][position-1]}")
        parsed.append((line, matches, primary_index, label, main, value))
    chart = build_chart(cast['line_values'], month_branch=cast['month_branch'],
                        day_ganzhi=cast['day_ganzhi'])
    comparisons = []
    for position, (line, matches, primary_index, label, main, value) in enumerate(parsed, 1):
        primary = chart['lines'][position-1]
        checks = {'line_value': value == cast['line_values'][position-1],
                  'primary_relative': label[1] == primary['relative'],
                  'primary_branch': label[2] == primary['branch']}
        if primary_index:
            hidden = primary.get('hidden') or {}
            checks['hidden_relative'] = matches[0][1] == hidden.get('relative')
            checks['hidden_branch'] = matches[0][2] == hidden.get('branch')
        if '世' in main:
            checks['shi'] = primary['shi']
        if '应' in main:
            checks['ying'] = primary['ying']
        if len(matches) > primary_index + 1:
            changed_label = matches[primary_index + 1]
            changed = chart['changed']['lines'][position-1]
            checks['changed_relative'] = changed_label[1] == changed['relative']
            checks['changed_branch'] = changed_label[2] == changed['branch']
        if not all(checks.values()):
            raise ValueError(f"{unit['unit_id']}: source conflict at {position}: {checks}")
        comparisons.append({'position': position, 'source_line': line,
                            'primary_label_index': primary_index, 'checks': checks})
    return {'unit_id': unit['unit_id'], 'source_sha256': document.source_sha256,
            'chart_text_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'input_line_values': cast['line_values'], 'month_branch': cast['month_branch'],
            'day_ganzhi': cast['day_ganzhi'], 'status': 'passed',
            'primary': chart['primary']['full_name'], 'changed': chart['changed']['full_name'],
            'comparisons': comparisons}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--manifests', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-incomplete', action='store_true', help='Record unresolved casts without certifying them')
    args = parser.parse_args()
    sources = {s['source_id']: s for s in map(json.loads, (args.root/'data/canonical/sources.jsonl').read_text(encoding='utf8').splitlines())}
    records = []
    for source_id in sorted(sources):
        path = args.manifests/f'{source_id}.json'
        if not path.is_file():
            if args.allow_incomplete:
                continue
            raise ValueError(f'Missing manual manifest: {source_id}')
        manifest = json.loads(path.read_text(encoding='utf8'))
        source = sources[manifest['source_id']]
        if source['source_type'] != 'native_text':
            if args.allow_incomplete:
                continue
            raise ValueError('This verifier is limited to explicit native-text chart notation')
        document = load_document(args.root, source)
        for unit in manifest['units']:
            if unit['kind'] != 'case':
                continue
            casts = [unit.get('cast', {})] + unit.get('additional_casts', [])
            for index, cast in enumerate(casts):
                cast = cast.get('cast', cast)
                selected = {**unit, 'unit_id': unit['unit_id'] + (f'.cast{index+1}' if index else ''), 'cast': cast}
                try:
                    if not all(cast.get(key) for key in ('line_values', 'month_branch', 'day_ganzhi')):
                        raise ValueError('Source does not give a complete cast and calendar')
                    records.append(verify(document, selected))
                except (ValueError, KeyError) as exc:
                    if not args.allow_incomplete:
                        raise
                    records.append({'unit_id': selected['unit_id'], 'status': 'needs_review', 'reason': str(exc)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'basis': 'independent_literal_chart_labels',
                                    'records': records}, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({'verified_cases': sum(r['status'] == 'passed' for r in records),
                      'needs_review': sum(r['status'] != 'passed' for r in records),
                      'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
