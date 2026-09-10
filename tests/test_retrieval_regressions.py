"""Regressions from independent Astra blind-test tool traces, not answer matching."""
from liuyao_mcp.chart import build_chart
from liuyao_mcp.common import tokens, case_search_text
from liuyao_mcp.retrieval import search_knowledge, get_source


def test_meaningful_domain_conditions_survive_query_tokenization():
    cases = {
        '入职': {'入职', '工作'},
        '财生官 官生世': {'财生官', '官生世'},
        '面试 父母 发动 生世': {'父母', '生世'},
        '考试 财爻 发动 父母': {'妻财', '父母'},
        '父母 化破': {'父母', '化破', '月破'},
        '父母生世': {'父母', '生世'},
        '手机 用神两现': {'手机', '用神', '两现'},
        '资格考试': {'考试'},
        '炒股': {'股票'},
    }
    for query, expected in cases.items():
        assert expected <= set(tokens(query)), (query, tokens(query))
        result = search_knowledge(query, limit=2, max_chars=20000)
        assert expected <= set(result['query_terms'])


def test_specific_questions_do_not_recall_unrelated_generic_charts():
    stocks = search_knowledge('股票 妻财 官鬼 发动', kind='case', limit=3, max_chars=60000)
    assert stocks['items']
    assert all('wealth' in i['classification']['roots'] for i in stocks['items'])
    assert all('赴约' not in i['question']['raw'] and '求婚' not in i['question']['raw'] for i in stocks['items'])
    jobs = search_knowledge('求职 指定单位 应爻', kind='case', limit=3, max_chars=60000)
    assert jobs['items']
    assert all(not any(s in i['question']['raw'] for s in ('分房', '住房')) for i in jobs['items'])
    lost = search_knowledge('失物 饰品 父母', kind='case', limit=3, max_chars=60000)
    assert all('lost' in i['classification']['roots'] for i in lost['items'])
    assert all('职称' not in i['question']['raw'] and '往楚' not in i['question']['raw'] for i in lost['items'])


def test_structural_comparisons_only_use_verified_charts():
    for options in ({'require_valid_chart': True}, {'features': {'shi_relative': '父母'}}):
        result = search_knowledge('工作', kind='case', limit=5, max_chars=150000, **options)
        assert result['items']
        assert all(i['case']['extraction']['chart_validation'] == 'calculated' for i in result['items'])


def test_case_index_preserves_mechanical_relations_without_outcome_text():
    selected = {
        'question': {'raw': '面试能否录用'}, 'features': {},
        'derived': build_chart([0, 2, 2, 1, 2, 1], month_branch='午', day_ganzhi='丙寅'),
        'extraction': {'chart_validation': 'calculated'},
        'outcome': {'quotes': ['FORBIDDEN_ANSWER']},
        'interpretations': [{'original_text': 'FORBIDDEN_EXPLANATION'}],
    }
    text = case_search_text(selected)
    assert 'FORBIDDEN' not in text
    assert '父母发动生世（不代表有力或吉凶）' in text


def test_sliced_evidence_keeps_case_context_and_exact_source():
    result = search_knowledge('面试 录用', kind='rule', limit=5, max_chars=100000)
    assert result['items']
    for item in result['items']:
        assert item['content_role'] in ('theory', 'case_excerpt')
        assert len(item['related_case_ids']) <= 1
        assert get_source(item['evidence_id'], max_chars=500000)['text'] == item['quote']


def test_negated_conditions_are_not_positive_keyword_hits():
    for text, positive, negative in [('父母没有发动', '发动', '未发动'),
                                      ('父母没有月破', '月破', '未月破'),
                                      ('父母不生世', '生世', '未生世')]:
        words = set(tokens(text))
        assert negative in words and positive not in words, (text, words)
    from liuyao_mcp.taxonomy import classify, classify_rule
    assert classify('官鬼不见 父母伏藏')['topic'] is None
    assert classify('家养鸭子没有回来，失禽取用')['topic'] == 'lost'
    assert classify('参加摸奖，看当天得失')['topic'] == 'wealth'
    assert '经营' in tokens('承包经营鱼塘')
    assert classify_rule('第十章 应期', '占婚姻或疾病时，应期要分别判断。', [], 'lifa')['scope'] == 'common'


def test_event_intent_outweighs_role_or_generic_safety_word():
    from liuyao_mcp.taxonomy import classify
    assert classify('孩子离家后没有消息，问安危与下落')['topic'] == 'lost'
    assert classify('合伙人因经济纠纷被扣留，问何时能脱身')['topic'] == 'lawsuit'
    assert classify('和合伙人签订合作合同')['topic'] == 'cooperation'
    assert classify('身体健康情况，最近生病了')['topic'] == 'health'
