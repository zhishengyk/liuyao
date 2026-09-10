"""SQL retrieval keeps unknown semantics and bounds full-payload decoding."""
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest

from liuyao_mcp.common import database_path
from liuyao_mcp.ingest import SCHEMA, store_search_metadata
from liuyao_mcp.retrieval import search_knowledge, structural_candidates, structure_match


def test_sql_structural_scores_preserve_unknown_lists_and_yongshen():
    with sqlite3.connect(database_path()) as original:
        case = json.loads(original.execute('SELECT payload FROM cases LIMIT 1').fetchone()[0])
        source = json.loads(original.execute('SELECT metadata FROM sources WHERE id=?',
                                            (case['source']['source_id'],)).fetchone()[0])
    feature_sets = [
        {}, {'shi_relative':'官鬼','moving_positions':[], 'pattern_ids':[]},
        {'shi_relative':'官鬼','moving_positions':[2,1], 'pattern_ids':['a','b']},
        {'shi_relative':'妻财','moving_positions':[1,1], 'pattern_ids':['a','{}']},
        {'yongshen_reported':['官鬼'], 'yongshen_candidates':[
            {'relative':'官鬼','void':True,'moving':False,'month_break':False}]},
        {'yongshen_reported':['官鬼'], 'yongshen_candidates':[
            {'relative':'官鬼','void':True,'moving':False,'month_break':False},
            {'relative':'官鬼','void':False,'moving':True,'month_break':False}]},
        {'yongshen_reported':['官鬼','妻财'], 'yongshen_candidates':[
            {'relative':'官鬼','void':True,'moving':False,'month_break':False},
            {'relative':'妻财','void':False,'moving':True,'month_break':False}]},
        {'numeric':True,'nested':{'a':1}, 'null_list':[None,1]},
        {'yongshen_reported':['父母'], 'yongshen_candidates':[
            {'relative':'父母','scope':'hidden','void':True,'moving':None,'month_break':False},
            {'relative':'父母','scope':'changed','void':False,'moving':None,'month_break':True}]},
    ]
    queries = [
        {'shi_relative':'官鬼','unavailable':True}, {'moving_positions':[]},
        {'moving_positions':[1,2]}, {'moving_positions':[1,1]}, {'moving_positions':1},
        {'pattern_ids':['a']}, {'pattern_ids':[]}, {'pattern_ids':['a','b']},
        {'yongshen_relative':'官鬼','yongshen_void':True,'yongshen_moving':False},
        {'yongshen_relative':'妻财','yongshen_void':False}, {'yongshen_void':False},
        {'numeric':1,'nested':{'a':1}}, {'numeric':'true','nested':'{"a":1}'},
        {'null_list':[None]}, {'null_list':[True]}, {'pattern_ids':[{}]},
        {"'; DROP TABLE case_features; --":True},
        {'yongshen_relative':'父母','yongshen_scope':'hidden','yongshen_void':False},
        {'yongshen_relative':'父母','yongshen_scope':'changed','yongshen_void':False},
        {'yongshen_scope':'changed','yongshen_moving':False}, {'yongshen_scope':['hidden','changed']},
    ]
    with sqlite3.connect(':memory:') as db:
        db.row_factory=sqlite3.Row; db.executescript(SCHEMA)
        for index,features in enumerate(feature_sets):
            payload=dict(case,case_id=str(index),features=features)
            store_search_metadata(db,'case',payload,source)
        for query in queries:
            expected=[]
            for index,features in enumerate(feature_sets):
                match=structure_match(query,features)
                if match['matched']:
                    expected.append((str(index),match['score'],len(match['matched'])))
            expected.sort(key=lambda x:(-x[1],-x[2],x[0]))
            actual=structural_candidates(db,'SELECT evidence_id FROM evidence_metadata',{},query,100)
            assert [(r['evidence_id'],r['score'],r['matched_count']) for r in actual]==expected


def test_bm25_decodes_only_returned_case_payloads_and_does_not_write(monkeypatch):
    from liuyao_mcp import retrieval
    database=database_path()
    before=hashlib.sha256(database.read_bytes()).hexdigest()
    loads=json.loads; decoded=[]
    def tracked(text):
        value=loads(text)
        if isinstance(value,dict) and 'case_id' in value:
            decoded.append(value['case_id'])
        return value
    monkeypatch.setattr(retrieval,'json',SimpleNamespace(loads=tracked))
    result=search_knowledge('unlikely_unique_phrase_scaling',kind='case',limit=3,
                           features={'moving_positions':[]},retrieval_mode='bm25',max_chars=150000,
                           exclude_ids=[f'unrelated-{index}' for index in range(1000)])
    assert result['returned_count']==3
    assert decoded==[item['evidence_id'] for item in result['items']]
    assert all(item['ranking']['bm25'] is None for item in result['items'])
    assert result['candidate_pool_size']<=60
    assert hashlib.sha256(database.read_bytes()).hexdigest()==before


def test_old_schema_requires_explicit_rebuild(tmp_path):
    database=tmp_path/'old.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE build_info(key TEXT,value TEXT)')
        db.execute("INSERT INTO build_info VALUES('search_index_version','focused-1')")
    with pytest.raises(ValueError,match='索引版本过旧'):
        search_knowledge('旬空',db_path=database,retrieval_mode='bm25')


def test_dense_sql_scope_filters_before_topk_and_preserves_id_api(tmp_path):
    from liuyao_mcp.sqlite_vectors import write_index,search_vectors
    source=tmp_path/'base.sqlite'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE eligible(evidence_id TEXT PRIMARY KEY,category TEXT)')
        db.executemany('INSERT INTO eligible VALUES(?,?)',[('a','job'),('b','job'),('c','health')])
    snapshot=tmp_path/'vectors.sqlite'
    rows=[{'evidence_id':eid,'kind':'case','span':[0,2]} for eid in ('a','b','c')]
    write_index(snapshot,{'dimensions':2},rows,[[0.8,0.6],[0,1],[1,0]],source=source)
    before=hashlib.sha256(snapshot.read_bytes()).hexdigest()
    expected=search_vectors(snapshot,[[1,0]],'case',{'a','b'},1)
    assert search_vectors(snapshot,[[1,0]],'case',('a','b'),1)==expected
    actual=search_vectors(snapshot,[[1,0]],'case',(
        'SELECT evidence_id FROM eligible WHERE category=:category',{'category':'job'}),1)
    assert actual==expected and actual[0][0]['evidence_id']=='a' and actual[1]
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==before


def test_candidate_index_build_preserves_active_pointer(tmp_path,monkeypatch):
    from liuyao_mcp import vector_index
    source=tmp_path/'source.sqlite'
    with sqlite3.connect(source) as db:
        db.executescript('CREATE TABLE build_info(key TEXT,value TEXT); CREATE TABLE chunks(id TEXT,payload TEXT); CREATE TABLE cases(id TEXT,payload TEXT);')
        db.execute("INSERT INTO build_info VALUES('corpus_hash','fixture')")
        db.execute('INSERT INTO chunks VALUES(?,?)',('one',json.dumps({'chapter':'旬空','text':'用神旬空'})))
    folder=tmp_path/'semantic-index';folder.mkdir()
    pointer=folder/'active.json';pointer.write_text('{"generation":"existing"}')
    original=pointer.read_bytes()
    monkeypatch.setattr(vector_index,'model_lock',lambda:{'embedding':{'name':'fixture'},'reranker':{'name':'fixture'}})
    monkeypatch.setattr(vector_index,'model_key',lambda *args:'fixture')
    monkeypatch.setattr(vector_index,'ensure_worker',lambda:None)
    monkeypatch.setattr(vector_index,'request',lambda *args,**kwargs:{'vectors':[[1.0]+[0.0]*1023],'spans':[[0,7]]})
    built=vector_index.build_index(source,activate=False)
    assert pointer.read_bytes()==original
    assert (folder/built['generation']/'knowledge.sqlite').is_file()


@pytest.mark.parametrize('query,subtopic',[
    ('女儿离家几天，联系不上，什么时候能回家？','lost/person'),
    ('申请调动到另一个单位，什么时候能批下来？','job/change'),
])
def test_natural_case_questions_prefer_the_specific_event(query,subtopic,monkeypatch):
    from liuyao_mcp import retrieval,vector_index
    distractor_topic={'lost/person':'lost/belongings','job/change':'job/job_search'}[subtopic]
    with sqlite3.connect(database_path()) as db:
        ids=[db.execute("""SELECT e.evidence_id FROM evidence_metadata e JOIN evidence_topics t
            ON t.evidence_id=e.evidence_id WHERE e.kind='case' AND e.searchable=1
            AND t.topic_id=? ORDER BY e.evidence_id LIMIT 1""",(topic,)).fetchone()[0]
            for topic in (subtopic,distractor_topic)]
    # Isolate ranking from lexical luck: a high-scoring parent-topic distractor
    # must not displace an available case about the actual requested event.
    monkeypatch.setattr(retrieval,'tokens',lambda text:['no_lexical_fixture_hit'])
    monkeypatch.setattr(vector_index,'dense_search',lambda *args,**kwargs:(
        [{'evidence_id':ids[1],'score':.99},{'evidence_id':ids[0],'score':.7}],
        {'elapsed_ms':0,'model':{'name':'fixture'},'index_generation':'fixture','has_more':False}))
    result=search_knowledge(query,kind='case',retrieval_mode='hybrid',limit=3,max_chars=150000)
    assert result['subtopic']==subtopic
    assert result['items'][0]['evidence_id']==ids[0]
    tiers=[0 if item['category_match']=='same_subtopic' else 1 for item in result['items']]
    assert tiers==sorted(tiers)
