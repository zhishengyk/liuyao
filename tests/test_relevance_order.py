"""A relevance model's ordering must survive topic/source bookkeeping."""
import json
import sqlite3

from liuyao_mcp.common import database_path, plain
from liuyao_mcp.retrieval import search_knowledge


def test_reranker_can_place_common_rule_above_specific_case(monkeypatch):
    from liuyao_mcp import semantic, vector_index
    with sqlite3.connect(database_path()) as db:
        rows=[(eid,json.loads(payload)) for eid,payload in db.execute('SELECT id,payload FROM chunks')]
    common=next(eid for eid,p in rows if p.get('classification',{}).get('scope')=='common')
    specific=next(eid for eid,p in rows if 'job' in p.get('classification',{}).get('roots',[]) and p.get('content_role')!='background')
    monkeypatch.setattr(vector_index,'dense_search',lambda *a,**kw:([
        {'evidence_id':common,'score':0.9},{'evidence_id':specific,'score':0.8}],
        {'elapsed_ms':1,'model':{'name':'fixture'},'index_generation':'fixture','has_more':False}))
    monkeypatch.setattr(semantic,'ensure_worker',lambda:None)
    by_text={p['chapter']+'\n'+plain(p['text']):eid for eid,p in rows}
    def rerank(operation,payload):
        assert operation=='rerank'
        return {'scores':[100 if by_text[t]==common else 0 for t in payload['texts']],
                'elapsed_ms':1,'model':'fixture','revision':'1','device':'cpu','precision':'float32',
                'window_counts':[1]*len(payload['texts'])}
    monkeypatch.setattr(semantic,'request',rerank)
    found=search_knowledge('unlikely_unique_topic_phrase',kind='rule',topic='job',
                           retrieval_mode='hybrid_rerank',limit=2,max_chars=100000)
    assert found['items'][0]['evidence_id']==common
    scores=[r['ranking']['reranker_score'] for r in found['items']]
    assert scores==sorted(scores,reverse=True)
