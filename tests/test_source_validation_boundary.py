import hashlib
import json
import sqlite3

from liuyao_mcp.common import database_path
from liuyao_mcp.retrieval import get_source


def test_source_lookup_does_not_publish_a_conflicting_computed_chart():
    path = database_path()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with sqlite3.connect(path) as db:
        eid, raw = db.execute("""SELECT id,payload FROM cases
            WHERE json_extract(payload,'$.extraction.chart_validation')='conflict'
            AND json_type(payload,'$.derived')='object' ORDER BY id LIMIT 1""").fetchone()
        valid_id = db.execute("""SELECT id FROM cases
            WHERE json_extract(payload,'$.extraction.chart_validation')='calculated'
            ORDER BY id LIMIT 1""").fetchone()[0]
    diagnostic = json.loads(raw)
    assert diagnostic['derived']['features']
    returned = get_source(eid, max_chars=500000)
    case = returned['structured_case']
    assert returned['text'] and returned['source_spans']
    assert case['cast'] == diagnostic['cast']
    assert case['extraction'] == diagnostic['extraction']
    assert 'derived' not in case
    assert case['computed_chart_omitted']['reason'] == 'chart_not_validated'
    valid = get_source(valid_id, max_chars=500000)['structured_case']
    assert valid['derived']['features'] and 'computed_chart_omitted' not in valid
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
