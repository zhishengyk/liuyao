import json
from pathlib import Path

import pytest

from liuyao_mcp.chart import build_chart
from liuyao_mcp.patterns import stage
from liuyao_mcp.proofreading import apply
from liuyao_mcp.retrieval import get_topics, get_source, search_knowledge
from liuyao_mcp.taxonomy import classify, classify_rule, resolve, tier


def test_two_level_taxonomy_and_unknown_scope():
    assert resolve('relationship','reconciliation') == ('relationship','relationship/reconciliation')
    assert classify('想与前任复合')['topic']=='relationship'
    assert 'relationship/marriage' in classify('想再婚，问能否结婚')['topic_ids']
    assert {'study','health'} <= set(classify('身体有病会不会影响考试')['roots'])
    assert classify('求测人：男')['status']=='unknown'
    assert classify_rule('日辰与月建','这里讨论日月生克',[],'lifa')['scope']=='common'
    assert classify_rule('未识别标题','不明内容',[],'lifa')['scope']=='unknown'
    assert classify_rule('朱雀','文书与消息',[],'xiangfa')['scope']=='scene'
    assert tier({'scope':'common','roots':[]},'study',None,False) is None
    with pytest.raises(ValueError):resolve('study','relationship/reconciliation')


def test_explicit_events_take_precedence_over_institution_and_role_context():
    # Training-source housing questions and independent role/event contracts.
    for question in ('例四、戌月丁巳日，某女测工作单位分房可得到否',
                     '例一、辰月癸酉日，某人问向工作单位要住房，可得否',
                     '向单位要房子可得否'):
        result = classify(question)
        assert result['roots'] == ['property']
        assert 'property/allocation' in result['topic_ids']
    for question, root in [('测前男友会不会还钱', 'wealth'),
                           ('到医院看病时把钱丢失，可找回否', 'lost'),
                           ('医生应聘工作能否录用', 'job'),
                           ('班主任的孩子走失了', 'lost'),
                           ('让同事帮忙炒股', 'wealth'),
                           ('合伙人因纠纷被扣留，问何时获释', 'lawsuit')]:
        assert classify(question)['topic'] == root
    assert classify('工作单位分房')['background_context'] == ['工作单位']
    assert resolve('property', 'allocation') == ('property', 'property/allocation')


def test_event_context_preserves_multiple_matters_and_role_only_fallbacks():
    for question, roots in [('工作发展和申请住房都顺利吗', {'job', 'property'}),
                            ('工作单位前景和分房都顺利吗', {'job', 'property'}),
                            ('身体有病会不会影响考试', {'health', 'study'}),
                            ('去医院看病，另外问考试能否通过', {'health', 'study'}),
                            ('男友的感情和工作前景如何', {'relationship', 'job'}),
                            ('在医院工作能否升职', {'job'}),
                            ('到外地求职何时能录用', {'job'}),
                            ('在工作单位申请住房', {'property'}),
                            ('既问工作调动也问身体病情', {'job', 'health'}),
                            ('和合伙人签订合作合同', {'cooperation'})]:
        assert set(classify(question)['roots']) == roots
    for question, root in [('工作单位前景', 'job'), ('能当班主任吗', 'job'),
                           ('男友怎么样', 'relationship'), ('合伙人怎么样', 'cooperation'),
                           ('去医院', 'health'), ('请同事帮忙', 'affairs')]:
        assert classify(question)['topic'] == root


def test_hierarchical_retrieval_and_common_rule_switch():
    assert len(get_topics()['items'])==14
    assert 'relationship/reconciliation' in {x['id'] for x in get_topics('relationship')['items']}
    result=search_knowledge('复合 世应',kind='case',topic='relationship',subtopic='reconciliation',limit=3,max_chars=200000)
    assert result['items'] and all(x['category_match']=='same_subtopic' for x in result['items'])
    no_common=search_knowledge('旬空 用神',topic='study',include_common=False,limit=30,max_chars=300000)
    assert all(x['classification']['scope']!='common' for x in no_common['items'])
    a=search_knowledge('说话',method='xiangfa',topic='study',subtopic='study/exam',limit=3)
    b=search_knowledge('说话',method='xiangfa',topic='relationship',subtopic='relationship/reconciliation',limit=3)
    assert [x['evidence_id'] for x in a['items']]==[x['evidence_id'] for x in b['items']]


def test_life_stages_follow_book_table():
    assert stage('木','亥')=='长生'
    assert stage('木','巳')=='病'
    assert stage('金','丑')=='墓'
    assert stage('火','亥')=='绝'
    assert all(stage('土',b)==stage('水',b) for b in '子丑寅卯辰巳午未申酉戌亥')


def test_geshan_chain_and_fanyin_reference():
    chart=build_chart([2,2,2,3,0,1],month_branch='子',day_ganzhi='甲申')
    chain=next(x for x in chart['patterns']['facts'] if x['pattern_id']=='geshan_chain')
    assert [r['branch'] for r in chain['participants']]==['酉','未','巳']
    assert [r['position'] for r in chain['participants']]==[4,5,5]
    assert chain['direction']=='顺隔' and chain['source_rule_id']=='xf_xia_c09'
    # Xun changing its first line produces Xiao Xu, whose upper/lower trigrams oppose.
    changed=build_chart([0,1,1,2,1,1],month_branch='申',day_ganzhi='壬午')
    assert any(f['pattern_id']=='upper_lower_fanyin' and f['scope']=='changed' for f in changed['patterns']['facts'])
    assert len(changed['patterns']['combination_checks'])==18
    assert changed['patterns']['combination_checks'][-1]['status']=='needs_yongshen'


def test_punishments_keep_author_rule_and_real_participants():
    c=build_chart([2]*6,month_branch='子',day_ganzhi='甲子')
    facts=c['patterns']['facts']
    assert any(f['pattern_id']=='zi_mao_punishment' for f in facts)
    for f in facts:
        if f['pattern_id']=='self_punishment_branch':
            assert len(f['participants'])==1
            assert f['participants'][0]['branch'] in '辰午酉亥'
    assert any(f['pattern_id']=='harm' and {r['branch'] for r in f['participants']}=={'子','未'} for f in facts)
    with pytest.raises(ValueError):build_chart([2]*6,month_branch='子',day_ganzhi='甲子',yongshen_positions=[7])


def test_pattern_features_can_recall_without_keyword_hits():
    found=search_knowledge('unlikely_unique_phrase_987654',kind='case',
                           features={'pattern_ids':['geshan_chain']},limit=3,max_chars=150000)
    assert found['items']
    assert all('geshan_chain' in x['case']['features']['pattern_ids'] for x in found['items'])
    assert all(x['ranking']['bm25'] is None for x in found['items'])


def test_unreviewed_ocr_proposals_do_not_change_source(tmp_path):
    (tmp_path/'data').mkdir()
    source={'source_id':'test','sha256':'raw'}
    edit={'source_id':'test','line':1,'start':0,'end':2,'before':'六交','after':'六爻','original_sha256':'raw','visual_verified':False}
    p=tmp_path/'data/ocr_corrections.json'
    p.write_text(json.dumps({'edits':[edit]}),encoding='utf8')
    assert apply(source,'六交\n',tmp_path)==(source,'六交\n')
    edit['visual_verified']=True
    p.write_text(json.dumps({'edits':[edit]}),encoding='utf8')
    meta,text=apply(source,'六交\n',tmp_path)
    assert text=='六爻\n' and meta['original_sha256']=='raw'


def test_only_visually_reviewed_pages_can_be_read_as_reviewed_text():
    page=get_source('page:liuyao_lifa_jinjie:6')
    assert page['text_version']=='visually_reviewed_page'
    assert '六爻基础入门' in page['text'] and '仔细斟酌' in page['text']
    with pytest.raises(ValueError,match='尚未逐字'):
        get_source('page:liuyao_xiangfa_jinjie_shang:317')
