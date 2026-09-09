"""Prebuilt SQLite vectors; querying needs sqlite-vec but no model runtime."""
from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3


def load_extension(db):
    import sqlite_vec
    db.enable_load_extension(True)
    try:
        sqlite_vec.load(db)
    finally:
        db.enable_load_extension(False)


def pack_vector(values, dimensions):
    from sqlite_vec import serialize_float32
    values = list(values)
    if len(values) != dimensions or not all(math.isfinite(x) for x in values) or not any(values):
        raise ValueError("向量维度不一致，或包含非有限值、零向量")
    return serialize_float32(values)


def manifest_at(path):
    path = Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='semantic_metadata'").fetchone():
            return None
        return json.loads(db.execute('SELECT payload FROM semantic_metadata').fetchone()[0])


def write_index(path, manifest, rows, vectors, source=None):
    """Build a separate atomic snapshot, optionally including the source knowledge DB."""
    path = Path(path).resolve()
    if source is not None and path == Path(source).resolve():
        raise ValueError("向量建库输出须与原知识库分开")
    dimensions = manifest['dimensions']
    if not isinstance(dimensions, int) or dimensions < 1 or len(rows) != len(vectors):
        raise ValueError("向量维度或条目数量异常")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.building.sqlite')
    if temporary.exists():
        temporary.unlink()
    with closing(sqlite3.connect(temporary)) as db:
        if source is not None:
            with closing(sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)) as original:
                original.backup(db)
        load_extension(db)
        db.executescript('''
            DROP TABLE IF EXISTS semantic_metadata;
            DROP TABLE IF EXISTS semantic_vectors;
            CREATE TABLE semantic_metadata(payload TEXT NOT NULL);
            CREATE TABLE semantic_vectors(
                evidence_id TEXT NOT NULL, kind TEXT NOT NULL,
                start INT NOT NULL, end INT NOT NULL,
                embedding BLOB NOT NULL CHECK(typeof(embedding)='blob')
            );
            CREATE INDEX semantic_by_kind_id ON semantic_vectors(kind,evidence_id);
        ''')
        db.execute('INSERT INTO semantic_metadata VALUES(?)', (json.dumps(manifest),))
        db.executemany('INSERT INTO semantic_vectors VALUES(?,?,?,?,?)', (
            (row['evidence_id'], row['kind'], *row['span'], pack_vector(vector, dimensions))
            for row, vector in zip(rows, vectors)
        ))
        db.commit()
    temporary.replace(path)


def search_vectors(path, query_vectors, kind, allowed_ids, limit):
    """Cosine KNN with filters before ranking and max score over text windows."""
    if limit < 1 or not query_vectors:
        raise ValueError("向量查询需要非空查询向量和正数limit")
    path = Path(path).resolve()
    best = {}
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        load_extension(db)
        db.execute('PRAGMA query_only=ON')
        manifest = json.loads(db.execute('SELECT payload FROM semantic_metadata').fetchone()[0])
        allowed = json.dumps(sorted(allowed_ids))
        for vector in query_vectors:
            packed = pack_vector(vector, manifest['dimensions'])
            # ponytail: exact scan for this small corpus; consider vec0 if measured latency requires it.
            matches = db.execute('''
                WITH scored AS MATERIALIZED (
                    SELECT evidence_id, start, end, 1-vec_distance_cosine(embedding, ?) AS score
                    FROM semantic_vectors
                    WHERE kind=? AND evidence_id IN (SELECT value FROM json_each(?))
                ), ranked AS (
                    SELECT *, row_number() OVER (
                        PARTITION BY evidence_id ORDER BY score DESC, start, end
                    ) AS position FROM scored
                )
                SELECT evidence_id, start, end, score FROM ranked WHERE position=1
                ORDER BY score DESC, evidence_id LIMIT ?
            ''', (packed, kind, allowed, limit+1))
            for eid, start, end, score in matches:
                candidate = {'evidence_id': eid, 'score': score, 'span': [start, end]}
                previous = best.get(eid)
                if previous is None or (-score, candidate['span']) < (-previous['score'], previous['span']):
                    best[eid] = candidate
    ranked = sorted(best.values(), key=lambda item: (-item['score'], item['evidence_id']))
    return ranked[:limit], len(ranked) > limit
