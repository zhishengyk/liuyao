"""Compile verbatim book passages into global/domain reading prompts from the release DB.

No model, summarization, ranking or database mutation. Generated corpus stays out of Git.
"""
import argparse
from collections import defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def merge_ranges(ranges):
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def source_text(lines, start, end):
    if not 1 <= start <= end <= len(lines):
        raise ValueError(f'Invalid source lines {start}..{end} / {len(lines)}')
    return '\n'.join(lines[start - 1:end])


def source_content_hash(source_rows, unit_rows, page_rows):
    value = {'sources': source_rows, 'chunks': unit_rows, 'ocr_pages': page_rows}
    return sha(json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode())


def build(database, output, plan_path):
    database, output, plan_path = map(Path, (database, output, plan_path))
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        source_rows = list(db.execute('SELECT id,metadata,body FROM sources ORDER BY id'))
        unit_rows = list(db.execute('SELECT id,payload FROM chunks ORDER BY id'))
        page_rows = list(db.execute('SELECT source_id,pdf_page,payload FROM ocr_pages ORDER BY source_id,pdf_page'))
        sources = {sid: {'metadata': json.loads(meta), 'body': body, 'lines': body.splitlines()}
                   for sid, meta, body in source_rows}
        units = {uid: json.loads(payload) for uid, payload in unit_rows}
        pages = {(sid, page): json.loads(payload) for sid, page, payload in page_rows}
        logical_hash = source_content_hash(source_rows, unit_rows, page_rows)
    buckets = ['global'] + list(plan['domains'])
    ranges = {bucket: defaultdict(list) for bucket in buckets}
    evidence = {bucket: [] for bucket in buckets}
    selections = []

    def add(bucket, sid, spans, label):
        if bucket not in ranges or sid not in sources or not spans:
            raise ValueError(f'Unknown route/source or missing span: {bucket} {sid} {label}')
        # Keep entire lines, including between disjoint selections, rather than compressing the source.
        start, end = min(s['start_line'] for s in spans), max(s['end_line'] for s in spans)
        source_text(sources[sid]['lines'], start, end)
        ranges[bucket][sid].append([start, end])
        selections.append({'bucket': bucket, 'source_id': sid, 'start_line': start,
                           'end_line': end, 'label': label})

    def add_unit(bucket, uid):
        unit = units[uid]
        evidence[bucket].append(uid)
        add(bucket, unit['source_id'], unit['source_spans'], uid)
        for index, context in enumerate(unit.get('required_contexts', [])):
            spans = context.get('source_spans') or [context]
            add(bucket, context.get('source_id', unit['source_id']), spans, f'{uid}:context:{index}')

    database_only = []
    for uid, unit in units.items():
        classification = unit.get('classification', {})
        roots = classification.get('roots', [])
        if roots:
            for bucket in roots:
                add_unit(bucket, uid)
        else:
            database_only.append(uid)
    for item in plan.get('supplemental_spans', []):
        add(item['bucket'], item['source_id'], [item], item['reason'])
    for item in plan.get('supplemental_pages', []):
        for page in item['pages']:
            record = pages[(item['source_id'], page)]
            add(item['bucket'], item['source_id'], [{'start_line': record['canonical_start_line'],
                                                    'end_line': record['canonical_end_line']}], f'PDF {page}')
    for bucket, ids in plan.get('supplemental_ids', {}).items():
        for uid in ids:
            add_unit(bucket, uid)
    workflow = plan.get('workflow', [])
    seen_workflow_steps = set()
    for item in workflow:
        step = item.get('step')
        if not isinstance(step, int) or step < 1 or step in seen_workflow_steps:
            raise ValueError('Workflow steps must be unique positive integers')
        if not item.get('title') or not item.get('route') or not item.get('evidence_ids'):
            raise ValueError(f'Workflow step {step} needs title, route and evidence_ids')
        seen_workflow_steps.add(step)
        for uid in item['evidence_ids']:
            if uid not in units:
                raise ValueError(f'Workflow references missing evidence: {uid}')
            # Workflow passages are also routed into global source files, so the
            # dedicated reading order never becomes a detached summary.
            add_unit('global', uid)

    output.mkdir(parents=True, exist_ok=True)
    generated, sections, routes = {}, [], {}
    for bucket in buckets:
        title = '全局通用原文' if bucket == 'global' else plan['domains'][bucket]['title']
        files = []
        for sid, source_ranges in sorted(ranges[bucket].items()):
            name = f'{bucket}/{sid}.md'
            files.append(name)
            meta = sources[sid]['metadata']
            body = [f'# {title} · {meta.get("title", sid)}\n',
                    '以下为数据库保留的来源正文，未由模型摘要、改写或补齐。作者原注、新评及原例按原顺序保留；不得将原例反馈回填到当前问题。\n',
                    f'来源ID：{sid}；作者/整理信息：{meta.get("author") or "署名未独立确认"}。',
                    f'正文SHA256：{sha(sources[sid]["body"].encode())}。\n',
                    '位置均为当前来源正文全局行号；PDF页及校订状态见manifest。机器提取页不冒充逐字视觉校订。\n']
            for start, end in merge_ranges(source_ranges):
                raw = source_text(sources[sid]['lines'], start, end)
                marker = f'{sid}-L{start}-L{end}'
                fence = '`' * max(3, max((len(x) for x in re.findall(r'`+', raw)), default=0) + 1)
                body.extend([f'## 原文 {marker}\n', f'{fence}text\n{raw}\n{fence}\n'])
                related_pages = [{'pdf_page': page, 'status': r['status'],
                                  'visual_reviewed': r.get('visual_reviewed'), 'unclear': r.get('unclear', [])}
                                 for (source_id, page), r in sorted(pages.items()) if source_id == sid
                                 and r['canonical_start_line'] <= end and r['canonical_end_line'] >= start]
                sections.append({'file': name, 'marker': marker, 'source_id': sid,
                                 'start_line': start, 'end_line': end, 'text_sha256': sha(raw.encode()),
                                 'characters': len(raw), 'pages': related_pages})
            generated[name] = '\n'.join(body)
            for section in (s for s in sections if s['file'] == name):
                start = generated[name].index('## 原文 ' + section['marker'] + '\n')
                next_start = generated[name].find('\n## 原文 ', start + 1)
                section['file_start_offset'] = start
                section['file_end_offset'] = next_start if next_start >= 0 else len(generated[name])
        routes[bucket] = files
        if bucket != 'global':
            domain = plan['domains'][bucket]
            questions = '、'.join(domain['questions'])
            own_count = sum(bucket in u.get('classification', {}).get('roots', []) for u in units.values())
            generated[f'{bucket}/PROMPT.md'] = (
                f'# {domain["title"]}领域提示词\n\n'
                '先完成全局流程及通用原文阅读，再按本题加载以下领域原文。以下路由说明由整理者编写，断法以各书原文为准。\n\n'
                f'本领域问意目录：{questions}。按实际对象、动作和时限选择，不由同一个领域名称推定相同取用。'
                '复合问题分别加载相关领域并分别回答。\n\n'
                '在FLOW第3步可读取本领域的取用规则；主线吉凶已判后，才在第5步读取本领域细节取象、过程和例外；应期规则留到第6步。'
                '依各书原有顺序核取用、作用、主辅及例外，区分现状/吉凶/应期，再对原问作具体取象。'
                '作者分歧先并列推导；施力者→受力者、双方现实角色/层次、判断层面、时限和前提均对齐而结论相反时，按用户指定以王虎应直接论述或明确署名评释为主。'
                '`世生应`与`应生世`、动变发生在不同一方的案例不是同一结构。'
                '其他原文仍保留；王虎应未覆盖或内部冲突则不自行裁决。文件内原文及例证完整保留，例证反馈只属于原例。\n\n'
                f'已有直接领域理论条目：{own_count}；补充章段与通用取用入口另计。'
                '本汇编覆盖当前已整理理论及清单指定原章，不声称全书每页或本领域所有方法均已完成。\n\n'
                + ('此领域目前没有直接分类的理论条目，以下为明确标出的通用取用原文；具体领域断法仍需数据库补查，不能宣称已有完整专章。\n\n' if own_count == 0 else '')
                + '\n'.join(f'- [{sources[Path(f).stem]["metadata"].get("title", Path(f).stem)}]({Path(f).name})' for f in files)
                + '\n\n先读取[全局断卦执行顺序与原文](../FLOW.md)。本领域涉及取用时在第3步读取相应原文；主线吉凶已判后再读细节取象和过程；应期留在第6步。再核全文及相邻限制，然后用数据库补充细则、例外和相似案例。未读完、截断或来源不清须记入reading_gaps；不得把未读当作没有，也不自动截断原文或以摘要替代。\n')

    flow = ['# 全局断卦执行顺序与原文\n',
            '本文件的步骤标题和“本步执行”仅是整理者根据下列原文安排的阅读与核查路由，不新增断法，也不替代任何作者原句。'
            '每步所列正文均按当前数据库的完整来源行范围保留；同一原文在不同步骤重复出现，是因为它同时约束多个判断环节。'
            '先按此顺序完成主线，再读GLOBAL.md列出的通用原文和本题领域PROMPT；细则、例外和案例仍由数据库按实际盘面补查。\n']
    flow_sections = []
    for item in sorted(workflow, key=lambda value: value['step']):
        flow.extend([f'## 第{item["step"]}步：{item["title"]}\n',
                     f'本步执行：{item["route"]}\n',
                     '以下为本步骤的完整原文依据：\n'])
        for uid in item['evidence_ids']:
            unit = units[uid]
            blocks = [(uid, unit['source_id'], unit['source_spans'])]
            for index, context in enumerate(unit.get('required_contexts', [])):
                blocks.append((f'{uid}:context:{index}', context.get('source_id', unit['source_id']),
                               context.get('source_spans') or [context]))
            for label, sid, spans in blocks:
                start, end = min(span['start_line'] for span in spans), max(span['end_line'] for span in spans)
                raw = source_text(sources[sid]['lines'], start, end)
                marker = f'{label} · {sid}-L{start}-L{end}'
                fence = '`' * max(3, max((len(value) for value in re.findall(r'`+', raw)), default=0) + 1)
                flow.extend([f'### 原文 {marker}\n', f'{fence}text\n{raw}\n{fence}\n'])
                flow_sections.append({'file': 'FLOW.md', 'marker': marker, 'source_id': sid,
                                      'start_line': start, 'end_line': end, 'text_sha256': sha(raw.encode()),
                                      'characters': len(raw)})
    generated['FLOW.md'] = '\n'.join(flow)
    for section in flow_sections:
        start = generated['FLOW.md'].index('### 原文 ' + section['marker'] + '\n')
        next_start = generated['FLOW.md'].find('\n### 原文 ', start + 1)
        section['file_start_offset'] = start
        section['file_end_offset'] = next_start if next_start >= 0 else len(generated['FLOW.md'])
    sections.extend(flow_sections)

    generated['GLOBAL.md'] = ('# 全局必读原文\n\n'
        '先完整读取[全局断卦执行顺序与原文](FLOW.md)，按其中顺序建立主线；再完整读取以下通用原文文件。'
        'FLOW.md的步骤标题只是原文阅读与核查路由，不能替代其下完整原文。以下内容不依赖临时主题检索。'
        '按作者分册阅读，保留原文主辅、例外和不同观点，不把不同书强行合并成一套公式。'
        '跨作者真实冲突按用户指定以王虎应直接论述或明确署名评释为主；先核作者归属、施力者→受力者、双方现实角色/层次、判断层面、时限和前提。'
        '`世生应`与`应生世`不是同一结构，其他作者原文不删除。'
        '王虎应未覆盖或内部仍冲突时保留未决。\n\n'
        + '\n'.join(f'- [{sources[Path(f).stem]["metadata"].get("title", Path(f).stem)}]({f})' for f in routes['global'])
        + '\n\n原文较长时按文件、来源段连续读取并记录读到的位置；遇到上下文或工具截断，不得声称完整读取。'
        '原文文件保持全文，不能为了上下文长度改写或压缩；未完成阅读应明确列为流程缺口。\n\n'
        '根据原问再读取领域PROMPT及其原文：\n\n'
        + '\n'.join(f'- [{d["title"]}]({bucket}/PROMPT.md)：' + '、'.join(d['questions']) for bucket, d in plan['domains'].items())
        + '\n\n其余通用细则和未归类情境保留在数据库中，按当前对象和缺口检索；不在每次断卦时强制加载。\n')

    for name, text in generated.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8', newline='\n')
    # The output directory is generator-owned; stale files must not enter the next plugin archive.
    old_manifest = output / 'manifest.json'
    if old_manifest.exists():
        previous = json.loads(old_manifest.read_text(encoding='utf-8'))
        for name in previous['files_sha256'].keys() - generated.keys():
            path = (output / name).resolve()
            if not path.is_relative_to(output.resolve()):
                raise ValueError('Manifest file escapes generated directory')
            path.unlink(missing_ok=True)
    manifest = {'schema_version': 1, 'database_sha256': sha(database.read_bytes()),
                'source_content_sha256': logical_hash,
                'plan_sha256': sha(plan_path.read_bytes()), 'theory_units': len(units),
                'database_only_evidence_ids': sorted(set(database_only) - set(uid for ids in evidence.values() for uid in ids)),
                'all_theory_units_accounted': (set(uid for ids in evidence.values() for uid in ids)
                                               | set(database_only)) == set(units),
                'source_versions': {sid: {'body_sha256': sha(s['body'].encode()), 'metadata': s['metadata']}
                                    for sid, s in sources.items()},
                'evidence_by_bucket': {k: sorted(set(v)) for k, v in evidence.items()},
                'selection_policy': plan['selection_policy'], 'workflow': workflow,
                'selections': selections, 'sections': sections,
                'files_sha256': {name: sha((output / name).read_bytes()) for name in generated},
                'limitations': ['Current stored source version; machine OCR and visual review remain distinct.',
                                'Selection is explicit, not whole-book coverage; full original line ranges and contexts are preserved.',
                                'Source examples and historical feedback are not live-case facts or blind-evaluation evidence.',
                                'No model summary, rewriting or prediction accuracy claim.']}
    save_json(old_manifest, manifest)
    return manifest


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=root / 'data/knowledge.sqlite')
    parser.add_argument('--output', type=Path, default=root / 'plugins/liuyao-assistant/skills/interpret-liuyao/references/source-prompts')
    parser.add_argument('--plan', type=Path, default=Path(__file__).with_name('skill_prompt_plan.json'))
    args = parser.parse_args()
    manifest = build(args.database, args.output, args.plan)
    print(json.dumps({'theory_units': manifest['theory_units'], 'files': len(manifest['files_sha256']),
                      'source_sections': len(manifest['sections']),
                      'prompt_theory_units': len(set(uid for ids in manifest['evidence_by_bucket'].values() for uid in ids)),
                      'database_only_theory_units': len(manifest['database_only_evidence_ids']),
                      'all_theory_units_accounted': manifest['all_theory_units_accounted']}))


if __name__ == '__main__':
    main()
