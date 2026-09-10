"""PDF-verified book navigation layered over immutable OCR source spans."""
import json
from pathlib import Path
import re

from .common import dumps

OUTLINE_SCHEMA = """
CREATE TABLE outline_nodes(id TEXT PRIMARY KEY, source_id TEXT NOT NULL, parent_id TEXT,
    position INT NOT NULL, start_line INT NOT NULL, end_line INT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX outline_children ON outline_nodes(parent_id,position);
CREATE TABLE evidence_outline(node_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
    PRIMARY KEY(node_id,evidence_id));
CREATE INDEX outline_evidence ON evidence_outline(evidence_id,node_id);
"""


def catalog_text(root):
    path = Path(root) / 'data/xiangfa_outline.json'
    return path.read_text(encoding='utf8') if path.is_file() else '{}'


def build_outline(source, lines, pages, root):
    book = next((b for b in json.loads(catalog_text(root)).get('books', [])
                 if b['source_id'] == source['source_id']), None)
    if book is None:
        return []
    if book['source_sha256'] != source['sha256']:
        raise ValueError('目录锚点与OCR版本不一致，请重新核对目录')
    prefix = 'xf_' + source['source_id'].split('_')[-1]
    nodes = [{'node_id': prefix, 'parent_id': None, 'node_type': 'book', 'depth': 0,
              'title': source['title'], 'start_line': 1, 'end_line': len(lines),
              'source_id': source['source_id'], 'position': 0, 'scene_hints': [],
              'body_start_line': book['body_start_line'], 'pdf_verification': book['pdf'],
              'toc_pdf_pages': book['toc_pdf_pages'], 'title_basis': 'source_manifest'}]
    for position, entry in enumerate(book['nodes'], 1):
        key, start = entry['key'], entry['start_line']
        if not 1 <= start <= len(lines) or lines[start-1] != entry['anchor_text']:
            raise ValueError(f'目录锚点失效：{prefix}_{key}')
        depth = len(key.split('_'))
        node_type = 'front_matter' if key.startswith('front') else ('chapter', 'section', 'usage')[
            2 if '_u' in key else depth-1]
        nodes.append({'node_id': prefix+'_'+key,
                      'parent_id': prefix+'_'+key.rsplit('_', 1)[0] if '_' in key else prefix,
                      'node_type': node_type, 'depth': depth, 'source_id': source['source_id'],
                      'position': position, 'title': entry['title'], 'title_basis': 'pdf_toc',
                      'ocr_anchor': entry['anchor_text'], 'ocr_status': entry['ocr_status'],
                      'start_line': start, 'toc_printed_page': entry['toc_printed_page'],
                      'scene_hints': entry.get('scene_hints', []), 'scene_hint_basis': 'source_paraphrase'})
        if 'body_printed_page_verified' in entry:
            nodes[-1]['body_printed_page_verified'] = entry['body_printed_page_verified']
            nodes[-1]['toc_page_differs_from_body'] = entry['toc_printed_page'] != entry['body_printed_page_verified']
    by_id = {n['node_id']: n for n in nodes}
    for i, node in enumerate(nodes):
        node['end_line'] = next((n['start_line']-1 for n in nodes[i+1:]
                                 if n['depth'] <= node['depth']), len(lines))
        path = []
        current = node
        while current:
            path.insert(0, {'node_id': current['node_id'], 'title': current['title']})
            current = by_id.get(current['parent_id'])
        node['path'] = path
        node['pdf_pages'] = sorted({p for p in pages[node['start_line']-1:node['end_line']] if p})
        node['intro_span'] = None
        if node['node_type'] not in ('book', 'front_matter'):
            end = min(node['end_line'], next((n['start_line']-1 for n in nodes[i+1:]
                                             if n['parent_id'] == node['node_id']), node['end_line']))
            for j in range(node['start_line']-1, end):
                if re.match(r'^\s*(?:求测人|占问事宜|公历[:：]|主变卦|【卦象结构化)', lines[j]):
                    end = j
                    break
            if end >= node['start_line']:
                node['intro_span'] = {'start_line': node['start_line'], 'end_line': end}
    return nodes


def node_at(nodes, line):
    return max((n for n in nodes if n['start_line'] <= line <= n['end_line']),
               key=lambda n: n['depth'], default=None)


def evidence_navigation(node, nodes):
    by_id = {n['node_id']: n for n in nodes}
    refs = []
    for part in node['path']:
        ancestor = by_id[part['node_id']]
        if ancestor['intro_span']:
            refs.append({'node_id': ancestor['node_id'], 'title': ancestor['title'],
                         **ancestor['intro_span']})
    return {'node_id': node['node_id'], 'path': node['path'], 'intro_refs': refs,
            'ocr_status': node.get('ocr_status'), 'scene_hints': node['scene_hints']}


def index_text(navigation):
    return ' '.join([p['title'] for p in navigation.get('path', [])] + navigation.get('scene_hints', []))


def store_outline(db, nodes, chunks, cases):
    for node in nodes:
        db.execute('INSERT INTO outline_nodes VALUES(?,?,?,?,?,?,?)', (
            node['node_id'], node['source_id'], node['parent_id'], node['position'],
            node['start_line'], node['end_line'], dumps(node)))
    for eid, record in [(c['id'], c) for c in chunks] + [(c['case_id'], c) for c in cases]:
        if record.get('outline'):
            db.executemany('INSERT INTO evidence_outline VALUES(?,?)',
                           ((p['node_id'], eid) for p in record['outline']['path']))


def related_cases(db, node_id, limit=10, exclude_ids=()):
    rows = db.execute('''SELECT c.id FROM evidence_outline e JOIN cases c ON c.id=e.evidence_id
                         WHERE e.node_id=? ORDER BY c.id''', (node_id,)).fetchall()
    rows = [r for r in rows if r[0] not in exclude_ids]
    return {'case_ids': [r[0] for r in rows[:limit]], 'total_cases': len(rows),
            'has_more': len(rows) > limit}


def read_outline(db, source_id=None, parent_id=None):
    if parent_id:
        parent = db.execute('SELECT source_id FROM outline_nodes WHERE id=?', (parent_id,)).fetchone()
        if parent is None or (source_id and source_id != parent[0]):
            raise ValueError('未知目录节点或目录与来源不符')
        rows = db.execute('SELECT payload FROM outline_nodes WHERE parent_id=? ORDER BY position', (parent_id,))
    elif source_id:
        root = db.execute('SELECT id FROM outline_nodes WHERE source_id=? AND parent_id IS NULL', (source_id,)).fetchone()
        if root is None:
            raise ValueError('该来源没有目录，请先不传参数查看可用书籍')
        rows = db.execute('SELECT payload FROM outline_nodes WHERE parent_id=? ORDER BY position', (root[0],))
    else:
        rows = db.execute('SELECT payload FROM outline_nodes WHERE parent_id IS NULL ORDER BY id')
    return [json.loads(r[0]) for r in rows]
