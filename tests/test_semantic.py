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
    from liuyao_mcp import vector_index as vi
    from liuyao_mcp.sqlite_vectors import write_index, search_vectors
    base = tmp_path/'db.sqlite'
    sqlite3.connect(base).close()
    folder = tmp_path/"semantic-index"
    version = folder/"test"
    version.mkdir(parents=True)
    (folder/"active.json").write_text(json.dumps({"generation":"test"}))
    manifest = {"dimensions":2,"generation":"test","corpus_hash":"corpus","model_key":"model","models":{"embedding":{"name":"fixture","revision":"1"}}}
    rows = [{"evidence_id":"a","kind":"rule","span":[0,2]}, {"evidence_id":"a","kind":"rule","span":[2,4]},
            {"evidence_id":"b","kind":"case","span":[0,2]}, {"evidence_id":"c","kind":"rule","span":[0,2]},
            {"evidence_id":"d","kind":"rule","span":[0,2]}]
    snapshot = version/'knowledge.sqlite'
    write_index(snapshot,manifest,rows,[[0,1],[1,0],[1,0],[0.8,0.6],[-1,0]])
    before = snapshot.read_bytes()
    monkeypatch.setattr(vi,"model_key",lambda:"model")
    monkeypatch.setattr(vi,"ensure_worker",lambda:None)
    monkeypatch.setattr(vi,"request",lambda *a,**k:{"vectors":[[1,0]]})
    result,details = vi.dense_search("q","rule",{"a","b","c"},10,"corpus",base)
    assert [r["evidence_id"] for r in result]==["a","c"]
    assert result[0]['span']==[2,4] and result[1]['score']==pytest.approx(0.8)
    assert details['storage']=='sqlite-vec'
    result,_ = vi.dense_search("q","rule",{"c"},1,"corpus",base)
    assert [r["evidence_id"] for r in result]==["c"]
    # The complete database can also be selected directly, without active.json.
    result,_ = vi.dense_search("q","case",{"a","b","c"},10,"corpus",snapshot)
    assert [r['evidence_id'] for r in result]==['b']
    result,more = search_vectors(snapshot,[[1,0],[-1,0]],'rule',{'a','b','c','d'},2)
    assert [r['evidence_id'] for r in result]==['a','d'] and more
    assert search_vectors(snapshot,[[1,0]],'rule',set(),2)==([],False)
    assert snapshot.read_bytes()==before
    with pytest.raises(ValueError,match="不一致"):
        vi.dense_search("q","rule",{"a"},10,"different",tmp_path/"db.sqlite")
    monkeypatch.setattr(vi,'model_key',lambda:'other-model')
    with pytest.raises(ValueError,match='不一致'):
        vi.dense_search('q','rule',{'a'},1,'corpus',snapshot)


def test_sqlite_vector_snapshot_preserves_sources_and_rejects_bad_vectors(tmp_path):
    from liuyao_mcp.sqlite_vectors import write_index, search_vectors
    source = tmp_path/'source.sqlite'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE sources(body TEXT)')
        db.execute('INSERT INTO sources VALUES(?)',('可回查原文',))
    output = tmp_path/'complete.sqlite'
    rows = [{'evidence_id':'a','kind':'rule','span':[0,3]}]
    write_index(output,{'dimensions':2},rows,[[1,0]],source=source)
    before = output.read_bytes()
    with sqlite3.connect(output) as db:
        assert db.execute('SELECT body FROM sources').fetchone()[0]=='可回查原文'
    for invalid in ([[1]], [[0,0]], [[float('nan'),1]], [[float('inf'),1]]):
        with pytest.raises(ValueError,match='向量'):
            write_index(output,{'dimensions':2},rows,invalid,source=source)
        assert output.read_bytes()==before
        with pytest.raises(ValueError,match='向量'):
            search_vectors(output,invalid,'rule',{'a'},1)
    with pytest.raises(ValueError,match='分开'):
        write_index(source,{'dimensions':2},rows,[[1,0]],source=source)


def test_hybrid_reranker_reorders_dense_candidates(monkeypatch,tmp_path):
    from liuyao_mcp import vector_index, semantic
    from liuyao_mcp.sqlite_vectors import write_index
    with sqlite3.connect(database_path()) as db:
        ids = [r[0] for r in db.execute("SELECT id FROM chunks WHERE source_id='liuyao_lifa_jinjie' ORDER BY id LIMIT 2")]
        corpus = db.execute("SELECT value FROM build_info WHERE key='corpus_hash'").fetchone()[0]
    snapshot = tmp_path/'knowledge.sqlite'
    manifest = {'dimensions':2,'generation':'fixture','corpus_hash':corpus,'model_key':'fixture',
                'models':{'embedding':{'name':'fixture'}}}
    write_index(snapshot,manifest,[{'evidence_id':eid,'kind':'rule','span':[0,2]} for eid in ids],
                [[1,0],[0.8,0.6]],source=database_path())
    monkeypatch.setattr(vector_index,'model_key',lambda:'fixture')
    monkeypatch.setattr(vector_index,'ensure_worker',lambda:None)
    monkeypatch.setattr(vector_index,'request',lambda *a,**k:{'vectors':[[1,0]]})
    monkeypatch.setattr(semantic,"ensure_worker",lambda:None)
    monkeypatch.setattr(semantic,"request",lambda *a,**k:{"scores":[-1,2],"elapsed_ms":1,"model":"fixture","revision":"1","device":"cpu","precision":"float32","window_counts":[1,1]})
    result = search_knowledge("zzunseenqueryzz",retrieval_mode="hybrid_rerank",limit=2,db_path=snapshot)
    assert result["retrieval"]=="hybrid_rerank"
    assert [r["evidence_id"] for r in result["items"]]==list(reversed(ids))
    assert all(r["ranking"]["reranker_score"] is not None for r in result["items"])


def test_weight_download_resumes_short_response_and_checks_hash(tmp_path,monkeypatch):
    import hashlib
    import io
    from liuyao_mcp import semantic
    content=b'complete-public-model-weights'
    offsets=[]
    class Response(io.BytesIO):
        status=206
        def __init__(self,offset):
            data=content[offset:5] if offset==0 else content[offset:]
            super().__init__(data)
            self.headers={'Content-Range':f'bytes {offset}-{len(content)-1}/{len(content)}'}
    def opening(req,timeout):
        offset=int(req.get_header('Range').split('=')[1].split('-')[0])
        offsets.append(offset)
        return Response(offset)
    monkeypatch.setattr(semantic,'urlopen',opening)
    target=tmp_path/'weights.bin'
    semantic.download_checked('https://example.invalid/weights',target,len(content),hashlib.sha256(content).hexdigest())
    assert target.read_bytes()==content and offsets==[0,5]
    semantic.download_checked('https://example.invalid/weights',target,len(content),hashlib.sha256(content).hexdigest())
    assert offsets==[0,5]


def test_wrong_model_hash_is_never_activated(tmp_path,monkeypatch):
    import io
    from liuyao_mcp import semantic
    class Response(io.BytesIO):
        status=206
        headers={'Content-Range':'bytes 0-2/3'}
    monkeypatch.setattr(semantic,'urlopen',lambda *a,**k:Response(b'bad'))
    target=tmp_path/'model.bin'
    with pytest.raises(ValueError,match='checksum'):
        semantic.download_checked('https://example.invalid/model',target,3,'0'*64)
    assert not target.exists()
