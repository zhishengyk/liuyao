"""Runtime contracts plus an opt-in check against prepared, real BGE weights."""
import json
import os
import sqlite3
from contextlib import closing

import pytest

from liuyao_mcp import semantic
from liuyao_mcp.inference_worker import text_windows


def test_embedding_lock_does_not_require_reranker(tmp_path, monkeypatch):
    monkeypatch.setattr(semantic, "runtime_root", lambda: tmp_path)
    folder = tmp_path / ".local"
    folder.mkdir()
    embedding = {"embedding": {"name": "BAAI/bge-m3", "revision": "pinned"}}
    (folder / "models.json").write_text(json.dumps(embedding))
    assert semantic.model_lock() == embedding
    with pytest.raises(ValueError, match="reranker"):
        semantic.model_lock(required=("embedding", "reranker"))


def test_reranker_changes_preserve_embedding_index_key(monkeypatch):
    import importlib.metadata
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "test-runtime")
    embedding = {"embedding": {"name": "BAAI/bge-m3", "revision": "pinned", "path": "one"}}
    both = {**embedding, "reranker": {"name": "BAAI/bge-reranker-v2-m3", "revision": "other"}}
    assert semantic.model_key(embedding) == semantic.model_key(both)
    assert semantic.model_key(embedding, roles=None) != semantic.model_key(both, roles=None)
    moved = {"embedding": {**embedding["embedding"], "path": "two"}}
    assert semantic.model_key(embedding) == semantic.model_key(moved)


def test_oversized_rerank_query_rejected_before_splitting_documents():
    calls = []
    def tokenizer(first, second=None, **kwargs):
        calls.append((first, second))
        return {"input_ids": list(range(len(first) + len(second or "") + 2))}
    with pytest.raises(ValueError, match="查询本身"):
        text_windows(tokenizer, "长文" * 10000, 16, query="查询" * 20)
    assert len(calls) == 1
    with pytest.raises(ValueError, match="max_tokens"):
        text_windows(tokenizer, "文本", 0)


def test_changed_source_corpus_does_not_replace_vector_snapshot(tmp_path):
    from liuyao_mcp.sqlite_vectors import write_index
    source = tmp_path / "source.sqlite"
    output = tmp_path / "vectors.sqlite"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE build_info(key TEXT,value TEXT)")
        db.execute("INSERT INTO build_info VALUES('corpus_hash','new-corpus')")
    output.write_bytes(b"previous-generation")
    rows = [{"evidence_id": "one", "kind": "rule", "span": [0, 1]}]
    with pytest.raises(ValueError, match="语料已改变"):
        write_index(output, {"dimensions": 2, "corpus_hash": "old-corpus"}, rows, [[1, 0]], source=source)
    assert output.read_bytes() == b"previous-generation"


def test_all_inference_callers_reuse_one_compute_thread(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from liuyao_mcp import inference_worker
    monkeypatch.setattr(inference_worker, "model_lock", lambda: {})
    monkeypatch.setattr(inference_worker, "model_key", lambda *args, **kwargs: "fixture")
    seen = []
    def compute(*args):
        seen.append(threading.current_thread())
        return "computed"
    monkeypatch.setattr(inference_worker.Models, "_embed", compute)
    monkeypatch.setattr(inference_worker.Models, "_rerank", compute)
    models = inference_worker.Models()
    try:
        assert models.embed(["first"]) == models.rerank("query", ["first"]) == "computed"
        with ThreadPoolExecutor(max_workers=4) as callers:
            assert list(callers.map(lambda _: models.embed(["next"]), range(12))) == ["computed"] * 12
        assert len(seen) == 14 and all(thread is seen[0] for thread in seen)
        assert seen[0] is not threading.current_thread()
    finally:
        models.compute.shutdown(wait=True)


@pytest.mark.skipif(os.environ.get("LIUYAO_REAL_MODELS") != "1", reason="set LIUYAO_REAL_MODELS=1 with prepared real models")
def test_real_models_dimensions_full_windows_and_relevance():
    import numpy as np
    semantic.ensure_worker()
    texts = ["六爻中用神旬空应该如何判断？", "论旬空与用神的关系。", "计算机网络协议。"]
    result = semantic.request("embed", {"texts": texts})
    vectors = np.asarray(result["vectors"])
    assert vectors.shape == (3, 1024)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
    assert vectors[0] @ vectors[1] > vectors[0] @ vectors[2] + 0.2
    assert result["pooling"] == "cls_l2"
    long_text = "先看用神旬空，再看日月旺衰。" * 30 + "最后一段必须保留。"
    windowed = semantic.request("embed", {"texts": [long_text], "max_tokens": 64})
    covered = set()
    for start, end in windowed["spans"]:
        covered.update(range(start, end))
    assert len(windowed["vectors"]) > 1
    assert covered == set(range(len(long_text)))
    reranked = semantic.request("rerank", {"query": "用神旬空", "texts": texts[1:]})
    assert reranked["scores"][0] > reranked["scores"][1]
    assert reranked["is_probability"] is False
    assert reranked["model"] == semantic.MODEL_IDS["reranker"]


@pytest.mark.skipif(os.environ.get("LIUYAO_REAL_MODELS") != "1", reason="set LIUYAO_REAL_MODELS=1 with prepared real models")
def test_real_sqlite_index_build_cache_resume_and_dense_search(tmp_path):
    from liuyao_mcp.vector_index import build_index, dense_search
    path = tmp_path / "knowledge.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE build_info(key TEXT,value TEXT); CREATE TABLE chunks(id TEXT,payload TEXT); CREATE TABLE cases(id TEXT,payload TEXT);")
        db.execute("INSERT INTO build_info VALUES('corpus_hash','real-model-test')")
        db.executemany("INSERT INTO chunks VALUES(?,?)", [
            ("related", json.dumps({"chapter": "旬空", "text": "论旬空与用神的关系。"})),
            ("unrelated", json.dumps({"chapter": "计算机", "text": "计算机网络协议。"})),
        ])
        db.execute("INSERT INTO cases VALUES(?,?)", ("missing-question", json.dumps({"question": {"raw": None}})))
        db.execute('CREATE TABLE evidence_metadata(evidence_id TEXT PRIMARY KEY,searchable INT)')
        db.executemany('INSERT INTO evidence_metadata VALUES(?,1)',[(eid,) for eid in ('related','unrelated','missing-question')])
    first = build_index(path)
    resumed = build_index(path)
    assert first["documents"] == first["encoded_documents"] == 2
    assert first["source_documents"] == 3
    assert first["excluded_empty_evidence_ids"] == ["missing-question"]
    assert resumed["cached_documents"] == 2 and resumed["encoded_documents"] == 0
    ranked, details = dense_search("用神旬空", "rule", {"related", "unrelated"}, 2, "real-model-test", path)
    assert [item["evidence_id"] for item in ranked] == ["related", "unrelated"]
    assert details["storage"] == "sqlite-vec"


def test_vector_build_skips_unsearchable_text_but_preserves_source_archive(tmp_path, monkeypatch):
    from liuyao_mcp import vector_index
    database=tmp_path/'knowledge.sqlite'
    with sqlite3.connect(database) as db:
        db.executescript('CREATE TABLE build_info(key TEXT,value TEXT); CREATE TABLE chunks(id TEXT,payload TEXT); CREATE TABLE cases(id TEXT,payload TEXT); CREATE TABLE evidence_metadata(evidence_id TEXT PRIMARY KEY,searchable INT);')
        db.execute("INSERT INTO build_info VALUES('corpus_hash','eligibility-fixture')")
        db.execute('INSERT INTO chunks VALUES(?,?)',('rule',json.dumps({'chapter':'旬空','text':'用神旬空的条件。'})))
        for eid,text in [('eligible','面试能否成功'),('noise','NOISE_MUST_NOT_BE_ENCODED'),('pending','PENDING_MUST_NOT_BE_ENCODED')]:
            db.execute('INSERT INTO cases VALUES(?,?)',(eid,json.dumps({'question':{'raw':text}})))
        db.executemany('INSERT INTO evidence_metadata VALUES(?,?)',[('rule',1),('eligible',1),('noise',0),('pending',0)])
    monkeypatch.setattr(vector_index,'model_lock',lambda:{'embedding':{'name':'fixture'}})
    monkeypatch.setattr(vector_index,'model_key',lambda *args:'fixture')
    monkeypatch.setattr(vector_index,'ensure_worker',lambda:None)
    encoded=[]
    def embed(operation,payload):
        assert operation=='embed'
        encoded.extend(payload['texts'])
        return {'vectors':[[1.0]+[0.0]*1023], 'spans':[[0,len(payload['texts'][0])]]}
    monkeypatch.setattr(vector_index,'request',embed)
    result=vector_index.build_index(database,activate=False)
    assert len(encoded)==2 and all('MUST_NOT' not in text for text in encoded)
    assert result['source_documents']==4 and result['excluded_unsearchable_documents']==2
    assert result['documents']==2 and result['document_selection']=='searchable-only-1'
    snapshot=tmp_path/'semantic-index'/result['generation']/'knowledge.sqlite'
    with closing(sqlite3.connect(snapshot)) as db:
        assert {r[0] for r in db.execute('SELECT evidence_id FROM semantic_vectors')}=={'rule','eligible'}
        assert db.execute('SELECT count(*) FROM cases').fetchone()[0]==3
    resumed=vector_index.build_index(database,activate=False)
    assert resumed['cached_documents']==2 and resumed['encoded_documents']==0 and len(encoded)==2
