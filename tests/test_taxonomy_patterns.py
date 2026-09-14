import json
from pathlib import Path

import pytest

from liuyao_mcp.chart import build_chart
from liuyao_mcp.patterns import stage
from liuyao_mcp.proofreading import apply
from liuyao_mcp.retrieval import get_topics, get_source, search_knowledge, structure_match
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


def test_repayment_is_not_a_return_journey_and_separate_events_survive():
    question = '借出去的钱什么时候能收回来？'
    assert classify(question)['roots'] == ['wealth']
    assert 'wealth/debt' in classify(question)['topic_ids']
    assert set(classify(question + '另外问出差的丈夫何时回来')['roots']) == {'wealth', 'travel'}


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


def test_named_questions_exclude_narrative_and_activity_background():
    for question,roots in [
        ('例十、戌月辛亥日，一日本学员跟随我学习预测，摇卦测在北京举行的马拉松比赛中，日本的选手旭化成能获胜否',{'affairs'}),
        ('例五、戌月庚戌日，一日本人跟随我学习六爻预测，当时天正在下雨，测雨何时停',{'weather'}),
        ('辰月甲戌日，行舟占顺风',{'weather'}),
        ('例二、亥月庚午日，某男测到医院看病时把钱丢失，可找回否',{'lost'}),
        ('我最近正在准备考试，摇卦问店铺生意如何',{'wealth'}),
        ('上班时手机丢失，能否找到',{'lost'}),
        ('旅行的时候身体出现症状，问病情如何',{'health'}),
    ]:
        assert set(classify(question)['roots']) == roots
    assert '看病时' in classify('看病时把钱包丢失')['background_context']
    assert classify('行舟占顺风')['topic_ids'] == ['weather','weather/weather']
    for question in ('问风水如何','问风险如何','问阴宅如何'):
        assert 'weather' not in classify(question)['roots']


def test_question_focus_preserves_multiple_events_causes_and_references():
    for question,roots in [
        ('先测学习进展，再问比赛名次',{'study','affairs'}),
        ('某男测身体病情，另外问工作调动能否成功',{'health','job'}),
        ('既问考试成绩，也问店铺经营',{'study','wealth'}),
        ('看病时会不会耽误考试',{'health','study'}),
        ('身体有病，问考试是否会受影响',{'health','study'}),
        ('去医院看病，另外问考试能否通过',{'health','study'}),
        ('女儿离家三天未归，问何时能回来',{'lost','travel'}),
        ('老婆生气出走，通过电话测老婆何时回家，会不会和自己离婚',{'lost','travel','relationship'}),
        ('工作时间能否调整',{'job'}),
    ]:
        assert set(classify(question)['roots']) == roots
    assert 'wealth/business' in classify('想做生意测财运')['topic_ids']
    assert 'health/treatment' in classify('预定明天手术，测自己病情')['topic_ids']


def test_generic_status_followups_keep_the_earlier_event():
    for question,topic in [
        ('孩子离家后没有消息，问安危与下落','lost'),
        ('朋友去外地出差，问目前人身安全','travel'),
        ('钱包丢失，问现在安危和去向','lost'),
        ('合伙人被拘留，问近况和消息','lawsuit'),
        ('准备申请住房，问进展如何','property'),
    ]:
        assert classify(question)['topic']==topic
    # A new named event is still distinct from the prefatory activity.
    assert classify('我正在学习预测，问比赛结果')['roots']==['affairs']
    assert classify('出差前学习预测，测雨何时停')['roots']==['weather']
    assert classify('问人身安全')['topic']=='health'


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


def test_yongshen_scope_distinguishes_hidden_from_flying_line():
    arguments=dict(line_values=[2,2,1,1,1,1],month_branch='辰',day_ganzhi='甲子',yongshen_positions=[1])
    primary=build_chart(**arguments)
    hidden=build_chart(**arguments,yongshen_scope='hidden')
    assert primary['lines'][0]['relative']=='父母'
    assert hidden['lines'][0]['hidden']['relative']=='子孙'
    assert primary['patterns']['combination_checks'][3]['status']=='not_detected'
    motif=next(f for f in hidden['patterns']['facts'] if f['pattern_id']=='combination_04')
    assert motif['participants']==[{'scope':'hidden','position':1,'branch':'子'}]
    assert hidden['patterns']['yongshen_refs']==motif['participants']
    assert hidden['lines'][0]['hidden']['moving'] is None
    with pytest.raises(ValueError,match='没有伏神'):
        build_chart([2,2,1,1,1,1],month_branch='辰',day_ganzhi='甲子',yongshen_positions=[3],yongshen_scope='hidden')
    changed=build_chart([3,1,1,1,1,1],month_branch='辰',day_ganzhi='甲子',
                        yongshen_positions=[1],yongshen_scope='changed')
    assert changed['patterns']['yongshen_refs']==[{'scope':'changed','position':1,'branch':'丑'}]
    assert changed['lines'][0]['transformation']['moving'] is None
    with pytest.raises(ValueError,match='没有动爻所化变爻'):
        build_chart([3,1,1,1,1,1],month_branch='辰',day_ganzhi='甲子',
                    yongshen_positions=[2],yongshen_scope='changed')


def test_hidden_yongshen_candidates_participate_in_indexed_retrieval():
    found=search_knowledge('',kind='case',features={'yongshen_relative':'父母','yongshen_scope':'hidden'},limit=1,max_chars=150000)
    assert found['items']
    first=found['items'][0]
    selected=[c for c in first['case']['features']['yongshen_candidates'] if c['relative']=='父母' and c['scope']=='hidden']
    assert len(selected)==1 and selected[0]['scope']=='hidden'
    assert len(first['structure_match']['matched'])==2 and not first['structure_match']['unknown']


def test_yongshen_states_do_not_mix_candidates_across_layers():
    features={'yongshen_reported':['父母'],'yongshen_candidates':[
        {'relative':'父母','scope':'hidden','void':True,'moving':None,'month_break':False},
        {'relative':'父母','scope':'changed','void':False,'moving':None,'month_break':True}]}
    match=structure_match({'yongshen_relative':'父母','yongshen_scope':'hidden','yongshen_void':False},features)
    assert len(match['matched'])==2 and len(match['different'])==1
    assert structure_match({'yongshen_void':False},features)['unknown']
    assert structure_match({'yongshen_scope':'changed','yongshen_moving':False},features)['unknown']


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
    import sqlite3
    from liuyao_mcp.common import database_path
    page=get_source('page:liuyao_lifa_jinjie:6')
    assert page['text_version']=='visually_reviewed_page'
    assert '六爻基础入门' in page['text'] and '仔细斟酌' in page['text']
    with sqlite3.connect(database_path()) as db:
        pages=[(sid,number,json.loads(payload)) for sid,number,payload
               in db.execute('SELECT source_id,pdf_page,payload FROM ocr_pages')]
    for sid,number,review in pages:
        result=get_source(f'page:{sid}:{number}',max_chars=1000)
        expected='visually_reviewed_page' if review.get('visual_reviewed') else 'machine_extracted_page'
        assert result['text_version']==expected
        assert result['text']==review['canonical_text'][:1000]
