import json
from pathlib import Path
import sqlite3

import pytest

from liuyao_mcp.common import case_search_text, database_path
from liuyao_mcp.inference_worker import text_windows
from liuyao_mcp.retrieval import search_knowledge


class CharacterTokenizer:
    def __call__(self,first,second=None,**kwargs):
        return {"input_ids":list(range(len(first)+len(second or "")+2))}


def test_windows_cover_whole_text_without_truncation():
    text = "先看用神。"*80+"最后一段必须保留。"
    windows = text_windows(CharacterTokenizer(),text,100,query="旬空")
    covered = set()
    for start,end,piece in windows:
        assert piece==text[start:end]
        assert len(piece)+len("旬空")+2<=100
        covered.update(range(start,end))
    assert covered == set(range(len(text)))
    assert windows[-1][2].endswith("最后一段必须保留。")


def test_case_embedding_and_reranking_input_exclude_answers():
    with sqlite3.connect(database_path()) as db:
        case = json.loads(db.execute("SELECT payload FROM cases LIMIT 1").fetchone()[0])
    case["interpretations"] = [{"original_text":"SECRET_AUTHOR_CONCLUSION"}]
    case["outcome"] = {"quote":"SECRET_OUTCOME"}
    text = case_search_text(case)
    assert "SECRET" not in text and case["question"]["raw"] in text


def test_exact_dense_ranking_filters_ids_and_detects_stale_index(tmp_path,monkeypatch):
    np = pytest.importorskip("numpy")
    from liuyao_mcp import vector_index as vi
    folder = tmp_path/"semantic-index"
    version = folder/"test"
    version.mkdir(parents=True)
    (folder/"active.json").write_text(json.dumps({"generation":"test"}))
    (version/"manifest.json").write_text(json.dumps({"dimensions":2,"corpus_hash":"corpus","model_key":"model","models":{"embedding":{"name":"fixture","revision":"1"}}}))
    (version/"rows.json").write_text(json.dumps([{"evidence_id":"a","kind":"rule","span":[0,2]},{"evidence_id":"b","kind":"case","span":[0,2]},{"evidence_id":"c","kind":"rule","span":[0,2]}]))
    np.save(version/"vectors.npy",np.array([[1,0],[1,0],[0.8,0.6]],dtype=np.float32))
    monkeypatch.setattr(vi,"model_key",lambda:"model")
    monkeypatch.setattr(vi,"ensure_worker",lambda:None)
    monkeypatch.setattr(vi,"request",lambda *a,**k:{"vectors":[[1,0]]})
    result,_ = vi.dense_search("q","rule",{"a","b","c"},10,"corpus",tmp_path/"db.sqlite")
    assert [r["evidence_id"] for r in result]==["a","c"]
    result,_ = vi.dense_search("q","rule",{"c"},10,"corpus",tmp_path/"db.sqlite")
    assert [r["evidence_id"] for r in result]==["c"]
    with pytest.raises(ValueError,match="不一致"):
        vi.dense_search("q","rule",{"a"},10,"different",tmp_path/"db.sqlite")


def test_hybrid_reranker_reorders_dense_candidates(monkeypatch):
    from liuyao_mcp import vector_index, semantic
    with sqlite3.connect(database_path()) as db:
        ids = [r[0] for r in db.execute("SELECT id FROM chunks WHERE source_id='liuyao_lifa_jinjie' ORDER BY id LIMIT 2")]
    def dense(query,kind,allowed,limit,corpus,path):
        assert set(ids)<=allowed
        return [{"evidence_id":ids[0],"score":0.9},{"evidence_id":ids[1],"score":0.8}],{"elapsed_ms":1,"model":{"name":"fixture"},"index_generation":"fixture","has_more":False}
    monkeypatch.setattr(vector_index,"dense_search",dense)
    monkeypatch.setattr(semantic,"ensure_worker",lambda:None)
    monkeypatch.setattr(semantic,"request",lambda *a,**k:{"scores":[-1,2],"elapsed_ms":1,"model":"fixture","revision":"1","device":"cpu","precision":"float32","window_counts":[1,1]})
    result = search_knowledge("zzunseenqueryzz",retrieval_mode="hybrid_rerank",limit=2)
    assert result["retrieval"]=="hybrid_rerank"
    assert [r["evidence_id"] for r in result["items"]]==list(reversed(ids))
    assert all(r["ranking"]["reranker_score"] is not None for r in result["items"])
