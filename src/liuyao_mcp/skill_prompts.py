"""Read immutable, verbatim skill files bundled beside the selected database."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .common import database_path


@lru_cache(maxsize=4)
def database_hash(path, size, modified_ns):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=4)
def source_content_hash(path, size, modified_ns):
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True) as db:
        value = {
            'sources': list(db.execute('SELECT id,metadata,body FROM sources ORDER BY id')),
            'chunks': list(db.execute('SELECT id,payload FROM chunks ORDER BY id')),
            'ocr_pages': list(db.execute('SELECT source_id,pdf_page,payload FROM ocr_pages ORDER BY source_id,pdf_page')),
        }
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def read_prompt(evidence_id, offset, max_chars, db_path=None):
    name = evidence_id.removeprefix('prompt:')
    if not re.fullmatch(r'(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.md', name):
        raise ValueError('未知提示词原文路径')
    database = Path(db_path or database_path()).resolve()
    candidates = [database.parent / 'source-prompts', database.parent / 'references/source-prompts',
                  database.parent.parent / 'plugins/liuyao-assistant/skills/interpret-liuyao/references/source-prompts']
    directory = next((p for p in candidates if (p / 'manifest.json').is_file()), None)
    if directory is None:
        raise FileNotFoundError('同版提示词原文未安装；请使用包含source-prompts的发行包，或在源码库运行scripts/build_skill_prompts.py')
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    stat = database.stat()
    logical_hash = source_content_hash(str(database), stat.st_size, stat.st_mtime_ns)
    if manifest['source_content_sha256'] != logical_hash:
        raise ValueError('提示词原文与当前语料内容不一致，请重新生成同版提示词')
    path = (directory / name).resolve()
    if name not in manifest['files_sha256'] or not path.is_relative_to(directory.resolve()):
        raise ValueError('提示词原文路径不在发行清单中')
    raw = path.read_bytes()
    expected = manifest['files_sha256'][name]
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('提示词原文文件校验失败')
    full = raw.decode('utf-8')
    end = min(len(full), offset + max_chars)
    return {'evidence_id': evidence_id, 'kind': 'skill_prompt', 'prompt_path': name,
            'source': {'title': '生产断卦流程与领域入口', 'sha256': expected,
                       'database_sha256': database_hash(str(database), stat.st_size, stat.st_mtime_ns),
                       'source_content_sha256': logical_hash},
            'text': full[offset:end], 'offset': offset, 'total_chars': len(full),
            'has_more': end < len(full), 'next_offset': end if end < len(full) else None,
            'source_sections': [s for s in manifest['sections'] if s['file'] == name
                                and s['file_start_offset'] < end and s['file_end_offset'] > offset],
            'note': '固定读取发行包中的预测流程和领域入口。历史案例、作者断语、事后反馈、评分与回归指令不在生产提示词中；规则原文按 evidence ID 定向读取。'}
