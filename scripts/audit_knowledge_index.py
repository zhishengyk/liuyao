"""Verify that a persisted knowledge index matches current source text and tokenizer."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from liuyao_mcp.common import case_search_text, database_path, tokens
from liuyao_mcp.outline import index_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=database_path())
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    path = args.database.resolve()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    checked = {'rule': 0, 'case': 0}
    mismatches = []
    with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
        info = dict(db.execute('SELECT key,value FROM build_info'))
        assert info['search_index_version'] == 'focused-1'
        sources = {sid: body.splitlines() for sid,body in db.execute('SELECT id,body FROM sources')}
        for table,kind in [('chunks','rule'), ('cases','case')]:
            for eid,raw in db.execute(f'SELECT id,payload FROM {table} ORDER BY id'):
                record = json.loads(raw)
                if kind == 'rule':
                    focus = record['chapter']
                    text = focus+' '+record['text']+' '+index_text(record.get('outline',{}))
                    assert record['text'] == '\n'.join(sources[record['source_id']][record['start_line']-1:record['end_line']]), eid
                    assert len(record.get('related_case_ids',[])) <= 1, eid
                else:
                    focus = record['question']['raw'] or ''
                    text = case_search_text(record)+' '+index_text(record.get('outline',{}))
                    assert record['outcome']['independently_verified'] is False, eid
                expected = (' '.join(tokens(focus)), ' '.join(tokens(text)))
                actual = db.execute('SELECT focus,body FROM search_index WHERE evidence_id=? AND kind=?',(eid,kind)).fetchall()
                if actual != [expected]:mismatches.append(eid)
                checked[kind] += 1
        assert db.execute('SELECT count(*) FROM search_index').fetchone()[0] == sum(checked.values())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    result = {'database_sha256':before,'corpus_hash':info['corpus_hash'],'checked':checked,
              'index_mismatch_ids':mismatches,'database_unchanged':True}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    assert not mismatches, 'Index was built with different tokenization/content; rebuild before acceptance'


if __name__ == '__main__':main()
