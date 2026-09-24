"""Compile verbatim book passages into global/domain reading prompts from the release DB.

No model, summarization, ranking or database mutation. Generated corpus stays out of Git.
"""
import argparse
from collections import defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import fnmatch


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


def archive_git_head(path):
    try:
        return subprocess.check_output(
            ['git', '-C', str(path), 'rev-parse', 'HEAD'],
            text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def archive_selected(rel, config):
    name = Path(rel).name
    if any(fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern)
           for pattern in config.get('exclude_globs', [])):
        return False
    if config.get('include_all_markdown_under_root'):
        return True
    if rel in set(config.get('exact_paths', [])):
        return True
    return any(token in name for token in config.get('basename_contains', []))


def archive_authority(rel, config):
    name = Path(rel).name
    for rule in config.get('authority_overrides', []):
        if fnmatch.fnmatch(rel, rule['glob']) or fnmatch.fnmatch(name, rule['glob']):
            return rule['authority_tier']
    return config.get('default_authority_tier', 'wang_case_specific')


def archive_domains(rel, config):
    domains = set()
    for rule in config.get('domain_rules', []):
        if any(token in rel for token in rule.get('contains', [])):
            domains.update(rule.get('domains', []))
    return sorted(domains or {'global'})


def add_wang_archive(generated, sections, archive_root, archive_manifest_path):
    archive_root = Path(archive_root)
    manifest_path = Path(archive_manifest_path)
    config = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not archive_root.is_dir():
        raise FileNotFoundError(f'Wang Huying archive root not found: {archive_root}')
    actual_head = archive_git_head(archive_root)
    expected_head = config.get('archive_commit_sha')
    if expected_head and actual_head and actual_head != expected_head:
        raise ValueError(f'Wang Huying archive commit mismatch: expected {expected_head}, got {actual_head}')
    if expected_head and actual_head is None:
        raise ValueError('Wang Huying archive must be a git checkout so the pinned commit can be verified')

    candidates = []
    for path in sorted(archive_root.rglob('*.md')):
        if config.get('skip_empty_files', True) and path.stat().st_size == 0:
            continue
        rel = path.relative_to(archive_root).as_posix()
        if archive_selected(rel, config):
            candidates.append((rel, path))
    if not candidates:
        raise ValueError('No Wang Huying archive sources matched the manifest selection policy')

    seen_hashes = {}
    records = []
    canonical_records = []
    for rel, path in candidates:
        raw = path.read_text(encoding='utf-8')
        digest = sha(raw.encode())
        authority = archive_authority(rel, config)
        domains = archive_domains(rel, config)
        source_id = 'wha-' + hashlib.sha1(rel.encode('utf-8')).hexdigest()[:12]
        title = Path(rel).name[:-3] if Path(rel).name.endswith('.md') else Path(rel).name
        duplicate_of = seen_hashes.get(digest)
        record = {
            'source_id': source_id,
            'title': title,
            'archive_path': rel,
            'authority_tier': authority,
            'domains': domains,
            'source_sha256': digest,
            'characters': len(raw),
            'duplicate_of': duplicate_of,
        }
        if duplicate_of is None:
            out_name = f'wang-huying-corpus/{source_id}.md'
            generated[out_name] = raw
            record['prompt_path'] = out_name
            seen_hashes[digest] = source_id
            canonical_records.append(record)
            sections.append({
                'file': out_name,
                'marker': f'{source_id}-FULL',
                'source_id': source_id,
                'start_line': 1,
                'end_line': max(1, len(raw.splitlines())),
                'authors': ['王虎应'] if authority in ('wang_direct', 'wang_case_specific') else [],
                'authority_tier': authority,
                'archive_path': rel,
                'text_sha256': digest,
                'characters': len(raw),
                'file_start_offset': 0,
                'file_end_offset': len(raw),
            })
        records.append(record)

    index = [
        '# 王虎应六爻原文全集索引\n\n',
        '本目录由固定的 books-archive-reorg 归档快照生成，保存经 manifest 选择的王虎应六爻原文全文。'
        '这里是证据库，不是要求一次性全部读入上下文。断卦先走 GLOBAL 推理，再读取当前领域索引和最相关的原文。\n\n',
        f'- 归档分支：{config.get("archive_branch")}\n',
        f'- 固定提交：{config.get("archive_commit_sha")}\n',
        f'- 原始匹配文件：{len(records)}\n',
        f'- 精确去重后全文文件：{len(canonical_records)}\n\n',
        '权威说明：wang_direct 可作为王虎应直接方法；wang_case_specific 用于同条件案例/答疑修正；'
        'mixed_requires_attribution 必须在原文中再次确认具体段落作者，不能把整份汇编视为王虎应。\n\n',
        '| 原文 | 权威层级 | 领域 | 归档路径 |\n|---|---|---|---|\n'
    ]
    for record in canonical_records:
        domains = '、'.join(record['domains'])
        index.append(
            f'| [{record["title"]}]({Path(record["prompt_path"]).name}) | '
            f'{record["authority_tier"]} | {domains} | {record["archive_path"]} |\n')
    generated['wang-huying-corpus/INDEX.md'] = ''.join(index)

    domain_names = set()
    has_all_domain_source = False
    for record in canonical_records:
        domain_names.update(record['domains'])
        has_all_domain_source = has_all_domain_source or '*' in record['domains']
    if has_all_domain_source:
        domain_names.update(config.get('all_domains', []))
    for domain in sorted(domain_names):
        if domain in ('global', '*'):
            continue
        rows = [
            f'# 王虎应原文 · {domain} 领域索引\n\n',
            '先按 GLOBAL 和领域 PROMPT 建立待核争议点，再读取下列原文。通用资料可用于所有领域。\n\n'
        ]
        selected = [r for r in canonical_records if domain in r['domains'] or '*' in r['domains']]
        for r in selected:
            rows.append(f'- [{r["title"]}](../{Path(r["prompt_path"]).name}) · {r["authority_tier"]} · {r["archive_path"]}\n')
        generated[f'wang-huying-corpus/domains/{domain}.md'] = ''.join(rows)

    return {
        'schema_version': config.get('schema_version', 1),
        'archive_branch': config.get('archive_branch'),
        'archive_commit_sha': expected_head,
        'archive_head_verified': actual_head,
        'archive_root': config.get('archive_root'),
        'selection_policy': config.get('selection_policy'),
        'matched_files': len(records),
        'canonical_files': len(canonical_records),
        'records': records,
    }


def build(database, output, plan_path, wang_archive_root=None, wang_archive_manifest=None):
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
    production_source_ids = set(plan.get('production_source_ids', []))
    compare_only_evidence = []

    def source_allowed(sid):
        return not production_source_ids or sid in production_source_ids

    def add(bucket, sid, spans, label):
        if bucket not in ranges or sid not in sources or not spans:
            raise ValueError(f'Unknown route/source or missing span: {bucket} {sid} {label}')
        # Keep entire lines, including between disjoint selections, rather than compressing the source.
        start, end = min(s['start_line'] for s in spans), max(s['end_line'] for s in spans)
        source_text(sources[sid]['lines'], start, end)
        ranges[bucket][sid].append([start, end])
        authors = sorted({span.get('author') for span in spans if span.get('author')})
        selections.append({'bucket': bucket, 'source_id': sid, 'start_line': start,
                           'end_line': end, 'label': label, 'authors': authors})

    def add_unit(bucket, uid):
        unit = units[uid]
        if not source_allowed(unit['source_id']):
            compare_only_evidence.append(uid)
            return False
        evidence[bucket].append(uid)
        add(bucket, unit['source_id'], unit['source_spans'], uid)
        for index, context in enumerate(unit.get('required_contexts', [])):
            spans = context.get('source_spans') or [context]
            context_sid = context.get('source_id', unit['source_id'])
            if source_allowed(context_sid):
                add(bucket, context_sid, spans, f'{uid}:context:{index}')
        return True

    database_only = []
    for uid, unit in units.items():
        classification = unit.get('classification', {})
        roots = classification.get('roots', [])
        if roots:
            if source_allowed(unit['source_id']):
                for bucket in roots:
                    add_unit(bucket, uid)
            else:
                compare_only_evidence.append(uid)
        else:
            database_only.append(uid)
    for item in plan.get('supplemental_spans', []):
        if not source_allowed(item['source_id']):
            raise ValueError(f'Supplemental production source is not allowed: {item["source_id"]}')
        add(item['bucket'], item['source_id'], [item], item['reason'])
    for item in plan.get('supplemental_pages', []):
        if not source_allowed(item['source_id']):
            raise ValueError(f'Supplemental production source is not allowed: {item["source_id"]}')
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
            if not source_allowed(units[uid]['source_id']):
                raise ValueError(f'Workflow evidence is not an allowed production source: {uid}')
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
            body = [f'# {title} · {meta.get("title", sid)}\n\n',
                    '以下为原书正文。原注、新评及原例按原顺序保留；原例反馈不属于当前问题。\n\n']
            for start, end in merge_ranges(source_ranges):
                raw = source_text(sources[sid]['lines'], start, end)
                marker = f'{sid}-L{start}-L{end}'
                file_start = sum(len(part) for part in body)
                body.append(raw + '\n\n')
                related_pages = [{'pdf_page': page, 'status': r['status'],
                                  'visual_reviewed': r.get('visual_reviewed'), 'unclear': r.get('unclear', [])}
                                 for (source_id, page), r in sorted(pages.items()) if source_id == sid
                                 and r['canonical_start_line'] <= end and r['canonical_end_line'] >= start]
                range_authors = sorted({
                    author
                    for selection in selections
                    if selection['bucket'] == bucket and selection['source_id'] == sid
                    and selection['start_line'] <= end and selection['end_line'] >= start
                    for author in selection.get('authors', [])
                })
                sections.append({'file': name, 'marker': marker, 'source_id': sid,
                                 'start_line': start, 'end_line': end, 'authors': range_authors,
                                 'text_sha256': sha(raw.encode()),
                                 'characters': len(raw), 'pages': related_pages,
                                 'file_start_offset': file_start,
                                 'file_end_offset': file_start + len(raw)})
            generated[name] = ''.join(body)
        routes[bucket] = files
        if bucket != 'global':
            domain = plan['domains'][bucket]
            questions = '、'.join(domain['questions'])
            own_count = sum(bucket in u.get('classification', {}).get('roots', [])
                            and source_allowed(u['source_id']) for u in units.values())
            generated[f'{bucket}/PROMPT.md'] = (
                f'# {domain["title"]}领域提示词\n\n'
                '本文件只提供王虎应体系下的领域覆盖层，不重复全局旺衰、生克和动变算法。'
                '先完成GLOBAL中的通用主干，再在取用、现实角色、事项特例和应期阶段加载本领域。\n\n'
                f'本领域问意目录：{questions}。同一领域内仍须按原问、对象、动作、时间尺度与专测/兼问分别取用；'
                '不得仅凭领域名称固定一个六亲。复合问题逐维加载、逐维回答。\n\n'
                '生产提示词只自动汇入计划允许的王虎应主证据书系；**书系白名单不等于段落作者白名单**。'
                '特别是《增删卜易评释》属于混合作者来源，必须继续区分古籍正文、旧注与明确【新评释】/王虎应补充，按authority_tier使用。'
                '其他书系作者仍保留在数据库中，仅在显式比较或冲突核查时作为compare_only检索，不得改变王虎应主判。'
                '案例反馈只属于原例，禁止回填当前问题或作为预测答案。\n\n'
                f'当前王虎应直接领域理论条目：{own_count}；补充章段另计。'
                '若本领域缺少王虎应直接原文，必须标reading_gap，并回数据库定向检索，不得用其他作者自动补位。\n\n'
                + ('此领域目前没有直接分类的理论条目；在王虎应生产过滤下，以下仅保留计划显式加入的王虎应通用/相邻原文。\n\n' if own_count == 0 else '')
                + '\n'.join(f'- [{sources[Path(f).stem]["metadata"].get("title", Path(f).stem)}]({Path(f).name})' for f in files)
                + '\n\n先读取[全局断卦流程与原文](../GLOBAL.md)，再核本领域原文及相邻限制。'
                '只有命中当前原问的领域规则才能进入结果路径；未读完、截断或作者归属不清必须记入reading_gaps。\n')

            if domain.get('flow'):
                generated[f'{bucket}/PROMPT.md'] += '\n\n## \u672c\u9886\u57df\u7528\u53d6\u4e0e\u6d41\u7a0b\uff08\u5206\u7c7b\u4e13\u5c5e\uff0c\u5148\u4e8e\u5168\u5c40\u5bf9\u5e94\u6b65\u9aa4\u6267\u884c\uff09:\n\n' + domain['flow'] + '\n'

            if domain.get('case_rules'):
                generated[f'{bucket}/PROMPT.md'] += (
                    '\n\n## 王虎应卦例提炼的领域裁决规则\n\n'
                    + '\n'.join(f'- {rule}' for rule in domain['case_rules'])
                    + '\n\n这些规则来自王虎应正式著作、本人卦例或答疑中反复可泛化的机制。'
                      '只在当前原问满足相同前提时使用；不得把原例反馈、人物故事或事后信息带入当前卦。\n')

    global_parts = ['# 全局断卦流程与原文\n\n',
                    '本文件是王虎应体系的生产主干：先定原问与用神，再按月、日、动爻、本位变爻判断，'
                    '随后核元忌、世爻、事项特例与应期。步骤标题只规定执行顺序；真正断法以紧随其后的王虎应原文为证据。'
                    '评测答案、历史反馈、其他作者规则都不得进入当前问题主判。\n\n']
    flow_sections = []
    for item in sorted(workflow, key=lambda value: value['step']):
        global_parts.extend([f'## 第{item["step"]}步：{item["title"]}\n\n',
                             f'本步执行：{item["route"]}\n\n'])
        for uid in item['evidence_ids']:
            unit = units[uid]
            blocks = [(unit['source_id'], unit['source_spans'])]
            for context in unit.get('required_contexts', []):
                blocks.append((context.get('source_id', unit['source_id']),
                               context.get('source_spans') or [context]))
            for sid, spans in blocks:
                if not source_allowed(sid):
                    continue
                start, end = min(span['start_line'] for span in spans), max(span['end_line'] for span in spans)
                raw = source_text(sources[sid]['lines'], start, end)
                marker = f'{sid}-L{start}-L{end}'
                file_start = sum(len(part) for part in global_parts)
                global_parts.append(raw + '\n\n')
                flow_sections.append({'file': 'GLOBAL.md', 'marker': marker, 'source_id': sid,
                                      'start_line': start, 'end_line': end, 'text_sha256': sha(raw.encode()),
                                      'characters': len(raw), 'file_start_offset': file_start,
                                      'file_end_offset': file_start + len(raw)})
    sections.extend(flow_sections)

    if plan.get('global_case_rules'):
        global_parts.extend([
            '## 王虎应卦例提炼的全局裁决规则\n\n',
            *[f'- {rule}\n' for rule in plan['global_case_rules']],
            '\n这些规则是从王虎应正式方法与具体卦例/答疑交叉提炼的通用机制。'
            '它们用于约束推理顺序，不替代对应原文；当前卦只有满足相同前提时才能调用案例中的例外。\n\n'
        ])

    global_parts.extend(['## 全局补充原文与领域路由\n\n',
        '以下自动汇入的通用原文只来自plan允许进入生产包的王虎应主证据书系；source allowlist只控制书系，不自动提升段落作者权威。'
        '《增删卜易评释》仍须区分古籍正文、旧注与王虎应【新评释】；古籍内容只有在王虎应采用时才能作为classic_endorsed进入主判。'
        '其他作者不进入生成的生产主干，仍可从数据库显式检索作compare_only。王虎应内部同条件仍冲突时保留冲突，不按出现次数投票。\n\n',
        *[f'- [{sources[Path(f).stem]["metadata"].get("title", Path(f).stem)}]({f})\n' for f in routes['global']],
        '\n原文较长时按文件、来源段连续读取并记录读到的位置；遇到上下文或工具截断，不得声称完整读取。'
        '原文文件保持全文，不能为了上下文长度改写或压缩；未完成阅读应明确列为流程缺口。\n\n',
        '根据原问再读取领域PROMPT及其原文：\n\n',
        *[f'- [{d["title"]}]({bucket}/PROMPT.md)：' + '、'.join(d['questions']) + '\n'
          for bucket, d in plan['domains'].items()],
        '\n其余通用细则和未归类情境保留在数据库中，按当前对象和缺口检索；不在每次断卦时强制加载。\n'])
    generated['GLOBAL.md'] = ''.join(global_parts)

    archive_metadata = None
    if wang_archive_root:
        manifest_path = wang_archive_manifest or Path(__file__).with_name('wang_huying_archive_manifest.json')
        archive_metadata = add_wang_archive(generated, sections, wang_archive_root, manifest_path)
        generated['GLOBAL.md'] += (
            '\n\n## 王虎应六爻原文全集\n\n'
            '发行包同时包含固定 book archive 快照提取的王虎应六爻原文全集。'
            '不要一次性全文加载；先完成主推理并形成争议点，再读取 '
            '[王虎应六爻原文全集索引](wang-huying-corpus/INDEX.md)，'
            '随后按当前领域索引和具体原文核验。'
            'mixed_requires_attribution 文件必须再次确认具体段落作者。\n')
        for bucket in plan['domains']:
            prompt = f'{bucket}/PROMPT.md'
            domain_index = f'wang-huying-corpus/domains/{bucket}.md'
            if domain_index in generated:
                generated[prompt] += (
                    '\n\n## 王虎应原文全集入口\n\n'
                    f'需要进一步核验本领域时，读取 [王虎应 {bucket} 原文索引](../{domain_index})；'
                    '只加载与当前结果路径相关的全文，不做全库灌入。\n')

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
    routed_ids = set(uid for ids in evidence.values() for uid in ids)
    compare_only_ids = set(compare_only_evidence) - routed_ids
    manifest = {'schema_version': 2, 'database_sha256': sha(database.read_bytes()),
                'source_content_sha256': logical_hash,
                'plan_sha256': sha(plan_path.read_bytes()), 'theory_units': len(units),
                'database_only_evidence_ids': sorted(set(database_only) - routed_ids),
                'compare_only_evidence_ids': sorted(compare_only_ids),
                'production_source_ids': sorted(production_source_ids),
                'all_theory_units_accounted': (routed_ids | set(database_only) | compare_only_ids) == set(units),
                'source_versions': {sid: {'body_sha256': sha(s['body'].encode()), 'metadata': s['metadata']}
                                    for sid, s in sources.items()},
                'evidence_by_bucket': {k: sorted(set(v)) for k, v in evidence.items()},
                'selection_policy': plan['selection_policy'], 'workflow': workflow,
                'wang_huying_archive': archive_metadata,
                'selections': selections, 'sections': sections,
                'files_sha256': {name: sha((output / name).read_bytes()) for name in generated},
                'limitations': ['Current stored source version; machine OCR and visual review remain distinct.',
                                'Selection is explicit, not whole-book coverage; full original line ranges and contexts are preserved.',
                                'Source examples and historical feedback are not live-case facts or blind-evaluation evidence.',
                                'Production prompt routing may intentionally exclude compare-only authors.',
                                'No model summary, rewriting or prediction accuracy claim.']}
    save_json(old_manifest, manifest)
    return manifest


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=root / 'data/knowledge.sqlite')
    parser.add_argument('--output', type=Path, default=root / 'plugins/liuyao-assistant/skills/interpret-liuyao/references/source-prompts')
    parser.add_argument('--plan', type=Path, default=Path(__file__).with_name('skill_prompt_plan.json'))
    parser.add_argument('--wang-archive-root', type=Path)
    parser.add_argument('--wang-archive-manifest', type=Path,
                        default=Path(__file__).with_name('wang_huying_archive_manifest.json'))
    args = parser.parse_args()
    manifest = build(args.database, args.output, args.plan,
                     wang_archive_root=args.wang_archive_root,
                     wang_archive_manifest=args.wang_archive_manifest)
    print(json.dumps({'theory_units': manifest['theory_units'], 'files': len(manifest['files_sha256']),
                      'source_sections': len(manifest['sections']),
                      'prompt_theory_units': len(set(uid for ids in manifest['evidence_by_bucket'].values() for uid in ids)),
                      'database_only_theory_units': len(manifest['database_only_evidence_ids']),
                      'all_theory_units_accounted': manifest['all_theory_units_accounted']}))


if __name__ == '__main__':
    main()
