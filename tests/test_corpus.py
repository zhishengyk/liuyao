"""Check every compiled record against canonical source text and reported coverage."""
import hashlib
import json
import sqlite3
from collections import defaultdict

from liuyao_mcp.common import database_path
from liuyao_mcp.ingest import read_spans


def test_every_source_chunk_and_case_is_retraceable():
    with sqlite3.connect(database_path()) as db:
        report = json.loads(dict(db.execute('SELECT key,value FROM build_info'))['coverage_report'])
        sources = {sid: (json.loads(meta), body.split('\n'))
                   for sid, meta, body in db.execute('SELECT id,metadata,body FROM sources')}
        assert report['mode'] == 'manual-corpus' and len(sources) == 6
        assert report['total_unapproved_units'] == 0
        assert db.execute('SELECT COUNT(*) FROM ocr_pages').fetchone()[0] == 811
        owned = defaultdict(set)

        def own(sid, spans):
            lines = sources[sid][1]
            for span in spans:
                for line_number in range(span['start_line'], span['end_line']+1):
                    line = lines[line_number-1]
                    start = span['start_column'] if line_number == span['start_line'] else 0
                    end = span['end_column'] if line_number == span['end_line'] else len(line)
                    assert 0 <= start <= end <= len(line)
                    for column in range(start, end):
                        if not line[column].isspace():
                            point = (line_number, column)
                            assert point not in owned[sid], (sid, point)
                            owned[sid].add(point)

        for payload, in db.execute('SELECT payload FROM chunks'):
            rule = json.loads(payload)
            sid, spans = rule['source_id'], rule['source_spans']
            assert rule['text'] == read_spans(sources[sid][1], spans)
            assert rule['review']['status'] == 'approved'
            for context in rule['required_contexts']:
                assert context['text'] == read_spans(sources[sid][1], context['source_spans'])
            own(sid, spans)

        seen_units = set()
        for case_id, payload in db.execute('SELECT id,payload FROM cases'):
            case = json.loads(payload)
            sid = case['source']['source_id']
            metadata, lines = sources[sid]
            assert case['schema_version'] == 'manual-corpus-1'
            assert case['source']['sha256'] == metadata['sha256']
            assert case['source']['original_text'] == read_spans(lines, case['source']['spans'])
            assert case['outcome']['independently_verified'] is False
            if case['cast']['line_values']:
                assert len(case['cast']['line_values']) == 6
                assert all(value in (0, 1, 2, 3) for value in case['cast']['line_values'])
            if case['extraction']['chart_validation'] == 'calculated':
                assert case['extraction']['source_chart_independently_verified'] is True
                assert [line['value'] for line in case['derived']['lines']] == case['cast']['line_values']
            else:
                # Internal calculations remain available for audits, but their
                # structural features must not become retrieval evidence.
                assert case['features']['chart_feature_status'] != 'calculated'
                assert 'moving_positions' not in case['features']
                assert 'void_positions' not in case['features']
            indexed = db.execute("SELECT COUNT(*) FROM search_index WHERE evidence_id=? AND kind='case'", (case_id,)).fetchone()[0]
            assert indexed == int(case['quality']['status'] == 'eligible')
            if case['unit_id'] not in seen_units:
                own(sid, case['source']['spans'])
                seen_units.add(case['unit_id'])

        for source in report['sources']:
            sid = source['source_id']
            metadata, lines = sources[sid]
            assert source['total_lines'] == len(lines) == metadata['canonical_line_count']
            assert hashlib.sha256('\n'.join(lines).encode()).hexdigest() == source['canonical_text_sha256']
            for excluded in source['excluded_ranges']:
                assert excluded['review']['status'] == 'approved'
                assert excluded['exact_text'] == read_spans(lines, excluded['source_spans'])
                own(sid, excluded['source_spans'])
            assert len(owned[sid]) == source['covered_nonwhitespace_chars']
            assert source['coverage_ratio'] == source['covered_nonwhitespace_chars']/source['total_nonwhitespace_chars']
            if source['complete']:
                assert not source['uncovered_spans'] and not source['missing_pages']
                assert source['coverage_ratio'] == 1.0
            else:
                assert source['uncovered_spans'] or source['missing_pages'] or source['manifest_missing']
