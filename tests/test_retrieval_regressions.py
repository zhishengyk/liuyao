"""Regressions from independent Astra blind-test tool traces, not answer matching."""
import pytest
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


def test_explicit_task_scope_returns_cases_for_the_requested_subject():
    # Bare keyword relevance is evaluated separately in the frozen independent
    # query reports. It is not a reliable intent classifier: 求职/单位 can match
    # housing, and 父母 can match health instead of a line in a lost-object chart.
    # The caller supplies its intended subject with the existing explicit filter.
    for query, topic in [('股票 妻财 官鬼 发动', 'wealth'), ('失物 饰品 父母', 'lost'),
                         ('求职 指定单位 应爻', 'job')]:
        scoped = search_knowledge(query, kind='case', topic=topic, limit=3, max_chars=60000)
        assert scoped['topic_filter_applied'] and scoped['items']
        assert all(topic in i['classification']['roots'] for i in scoped['items'])


@pytest.mark.xfail(reason="Known unscoped BM25 relevance gap: 求职/单位 ranks housing and bonuses; see CPU检索性能与扩容.md")
def test_unscoped_job_question_retrieves_a_job_case_in_top_three():
    result = search_knowledge('求职 指定单位 应爻', kind='case', retrieval_mode='bm25',
                              limit=3, max_chars=500000)
    assert any('job' in item['classification']['roots'] for item in result['items'])


def test_income_hint_does_not_displace_wage_arbitration_cases(monkeypatch):
    from liuyao_mcp import retrieval
    query = '劳动仲裁申请追回公司拖欠的工资'
    options = dict(kind='case', retrieval_mode='bm25', limit=8, max_chars=500000)
    monkeypatch.setattr(retrieval, 'classify_topic', lambda _: {'roots':[], 'topic_ids':[]})
    baseline = search_knowledge(query, **options)
    assert '仲裁' in baseline['items'][0]['question']['raw']
    # A secondary income label must not promote salary raises above the
    # original debt-recovery action, or add a separate set of candidates.
    monkeypatch.setattr(retrieval, 'classify_topic', lambda _: {
        'roots':['wealth'], 'topic_ids':['wealth', 'wealth/income']})
    result = search_knowledge(query, **options)
    assert result['topic_hint_paths'] == ['wealth/income']
    assert not result['topic_filter_applied']
    assert result['candidate_pool_size'] == baseline['candidate_pool_size']
    assert [(i['evidence_id'], i['ranking']['rrf_score']) for i in result['items']] == [
        (i['evidence_id'], i['ranking']['rrf_score']) for i in baseline['items']]


def test_single_character_chart_conditions_survive_query_filtering():
    for query, expected in [('亥 申 相害 回头生', {'亥', '申', '回头生'}),
                            ('甲 子 金 克 木', {'甲', '子', '金', '克', '木'}),
                            ('世 财 入墓', {'世', '财', '入墓'})]:
        result = search_knowledge(query, kind='rule', limit=2)
        assert expected <= set(result['query_terms'])


def test_unlisted_short_tokens_are_not_silently_reduced_to_another_concept():
    transformed = search_knowledge('子孙化鬼', kind='rule', limit=3)
    assert {'子孙', '化', '鬼'} <= set(transformed['query_terms'])
    external = search_knowledge('外应', kind='rule', limit=3)
    assert external['query_terms'] == ['外应']


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
