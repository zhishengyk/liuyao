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
        assert info['search_index_version'] == 'focused-2'
        sources = {sid: body.splitlines() for sid,body in db.execute('SELECT id,body FROM sources')}
        for table,kind in [('chunks','rule'), ('cases','case')]:
            for eid,raw in db.execute(f'SELECT id,payload FROM {table} ORDER BY id'):
                record = json.loads(raw)
                meta = db.execute('SELECT kind,source_id,searchable,chart_valid,group_id FROM evidence_metadata WHERE evidence_id=?',(eid,)).fetchone()
                assert meta is not None and meta[0] == kind, eid
                if kind == 'rule':
                    focus = record['chapter']
                    text = focus+' '+record['text']+' '+index_text(record.get('outline',{}))
                    assert record['text'] == '\n'.join(sources[record['source_id']][record['start_line']-1:record['end_line']]), eid
                    assert len(record.get('related_case_ids',[])) <= 1, eid
                    assert meta[1] == record['source_id'] and meta[4] == record['content_hash'], eid
                    if record.get('content_role') == 'background' or (record.get('content_role') == 'case_excerpt' and record.get('has_case_analysis') is False):
                        assert not meta[2], eid
                else:
                    focus = record['question']['raw'] or ''
                    text = case_search_text(record)+' '+index_text(record.get('outline',{}))
                    assert record['outcome']['independently_verified'] is False, eid
                    assert meta[4] == record['duplicate_group'], eid
                    assert bool(meta[3]) == (record['extraction']['chart_validation'] == 'calculated'), eid
                    spans = db.execute('SELECT source_id,start_line,end_line FROM case_spans WHERE evidence_id=? ORDER BY start_line,end_line',(eid,)).fetchall()
                    expected_spans = sorted((meta[1],s['start_line'],s['end_line']) for s in record['source']['spans'])
                    assert spans == expected_spans, eid
                expected = (' '.join(tokens(focus)), ' '.join(tokens(text)))
                actual = db.execute('SELECT focus,body FROM search_index WHERE evidence_id=? AND kind=?',(eid,kind)).fetchall()
                if actual != [expected]:mismatches.append(eid)
                checked[kind] += 1
        assert db.execute('SELECT count(*) FROM search_index').fetchone()[0] == sum(checked.values())
        assert db.execute('SELECT count(*) FROM evidence_metadata').fetchone()[0] == sum(checked.values())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    result = {'database_sha256':before,'corpus_hash':info['corpus_hash'],'checked':checked,
              'search_index_version':info['search_index_version'],
              'index_mismatch_ids':mismatches,'database_unchanged':True}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    assert not mismatches, 'Index was built with different tokenization/content; rebuild before acceptance'


if __name__ == '__main__':main()
