import hashlib
import json

import pytest

from liuyao_mcp.chart import build_chart
from liuyao_mcp.patterns import review_checks


def checks_for(values, **kwargs):
    chart = build_chart(values, **kwargs)
    return chart, {item['check_id']: item for item in review_checks(chart)}


def without_basic_sources(value):
    if isinstance(value, dict):
        return {key:without_basic_sources(item) for key,item in value.items() if key != 'basic_source_ids'}
    if isinstance(value, list):
        return [without_basic_sources(item) for item in value]
    return value


def without_relation_semantics(value):
    if isinstance(value, dict):
        return {key:without_relation_semantics(item) for key,item in value.items() if key != 'relation_semantics'}
    if isinstance(value, list):
        return [without_relation_semantics(item) for item in value]
    return value


def test_exam_regression_exposes_day_clash_moving_tomb_and_changed_returning_soul():
    chart, checks = checks_for([1, 1, 1, 1, 2, 0], month_branch='午', day_ganzhi='甲寅',
                              yongshen_positions=[2, 4])
    clash = checks['static_day_clash:primary:5']['trigger_facts']
    assert clash['line']['relative'] == '子孙' and clash['line']['moving'] is False
    assert clash['line']['month_relations'] == ['克']
    actor = clash['moving_relations'][0]
    assert actor['actor']['position'] == 6 and actor['actor']['scope'] == 'primary'
    assert actor['relations_to_line'] == ['生']
    official = next(item for item in clash['key_relations'] if item['target']['position'] == 2)
    assert '克' in official['relations_from_primary']
    tomb = checks['tomb_candidate:primary:4']['trigger_facts']
    assert tomb['line']['relative'] == '父母' and tomb['line']['branch'] == '午'
    assert tomb['tomb_branch'] == '戌' and tomb['roles'] == ['世', '用神候选']
    assert [(s['scope'], s['position'], s['kind'], s['spirit']) for s in tomb['tomb_sources']] == [
        ('primary', 6, 'moving', '玄武')]
    assert checks['palace_stage:changed']['trigger_facts'] == {
        'scope': 'changed', 'hexagram': '大有', 'palace_stage': '归魂'}
    assert 'xf_shang_c03' in chart['patterns']['source_rule_ids']


def test_visitor_responding_line_single_move_survives_day_control_and_changed_void():
    # 合成来访结构：应爻亥水独发、生世卯木，同时受日克且化空；不预设来或不来。
    chart, checks = checks_for([1, 1, 2, 2, 0, 2], month_branch='申', day_ganzhi='乙丑')
    single = checks['single_moving:primary:5']
    trigger = single['trigger_facts']
    assert chart['ying_position'] == 5 and trigger['moving_line']['day_relations'] == ['克']
    assert trigger['own_transformation']['void'] is True
    assert trigger['own_transformation']['moving'] is None
    shi = next(item for item in trigger['key_relations'] if '世' in item['roles'])
    assert shi['target']['position'] == 2 and shi['relations_from_primary'] == ['生']
    assert any('应爻' in q and '独发' in q and '生世' in q for q in single['suggested_queries'])
    assert any('化空' in q for q in single['suggested_queries'])
    _, multi = checks_for([1, 1, 2, 2, 0, 0], month_branch='申', day_ganzhi='乙丑')
    assert not any(key.startswith('single_moving:') for key in multi)


def test_absent_structures_do_not_create_checks_or_changed_palace_facts():
    _, checks = checks_for([1] * 6, month_branch='卯', day_ganzhi='乙卯')
    assert not any(key.startswith(('single_moving:', 'static_day_clash:', 'tomb_candidate:', 'palace_stage:'))
                   or key == 'moving_relationships' for key in checks)
    _, stationary = checks_for([1, 1, 2, 1, 2, 2], month_branch='子', day_ganzhi='甲子')
    assert stationary['palace_stage:primary']['trigger_facts']['palace_stage'] == '归魂'
    assert 'palace_stage:changed' not in stationary
    assert not any(key.startswith('single_moving:') for key in stationary)


@pytest.mark.parametrize('scope,values,branch,relative,moving', [
    ('primary', [2, 2, 1, 1, 1, 1], '辰', '父母', False),
    ('hidden', [2, 2, 1, 1, 1, 1], '子', '子孙', None),
    ('changed', [3, 1, 1, 1, 1, 1], '丑', '父母', None),
])
def test_selected_tomb_candidates_keep_layer_and_calendar_sources(scope, values, branch, relative, moving):
    _, checks = checks_for(values, month_branch='辰', day_ganzhi='甲辰',
                           yongshen_positions=[1], yongshen_scope=scope)
    trigger = checks[f'tomb_candidate:{scope}:1']['trigger_facts']
    assert trigger['line']['scope'] == scope and trigger['line']['branch'] == branch
    assert trigger['line']['relative'] == relative and trigger['line']['moving'] is moving
    assert '用神候选' in trigger['roles']
    assert {s['kind'] for s in trigger['tomb_sources']} >= {'day', 'month'}
    if scope != 'primary':
        assert all(s['kind'] != 'own_transformation' for s in trigger['tomb_sources'])


def test_hidden_and_changed_day_clashes_are_not_labelled_static_primary_clashes():
    hidden, hidden_checks = checks_for([2, 2, 1, 1, 1, 1], month_branch='辰', day_ganzhi='甲午',
                                      yongshen_positions=[1], yongshen_scope='hidden')
    assert hidden['lines'][0]['hidden']['day_clash'] is True
    assert 'static_day_clash:primary:1' not in hidden_checks
    changed, changed_checks = checks_for([1, 1, 1, 1, 2, 0], month_branch='辰', day_ganzhi='癸亥',
                                        yongshen_positions=[6], yongshen_scope='changed')
    assert changed['lines'][5]['transformation']['day_clash'] is True
    assert not any(key.startswith('static_day_clash:') for key in changed_checks)
    relations = changed_checks['single_moving:primary:6']['trigger_facts']['key_relations']
    selected = next(item for item in relations if item['target']['scope'] == 'changed')
    assert selected['relations_from_primary'] is None


def test_moving_day_clash_is_not_relabelled_as_static():
    _, checks = checks_for([1, 1, 1, 1, 0, 2], month_branch='午', day_ganzhi='甲寅')
    assert 'static_day_clash:primary:5' not in checks


def test_own_transformation_does_not_become_another_lines_moving_tomb():
    _, checks = checks_for([1, 1, 0, 1, 2, 2], month_branch='子', day_ganzhi='甲子')
    own = checks['tomb_candidate:primary:3']['trigger_facts']['tomb_sources']
    assert [(s['scope'], s['position'], s['kind']) for s in own] == [('changed', 3, 'own_transformation')]
    # 应爻戌土也以辰为墓，但第三爻所化辰不能越位当作第六爻的化墓。
    assert 'tomb_candidate:primary:6' not in checks


def test_tomb_scan_is_limited_to_shi_ying_and_supplied_candidates():
    _, checks = checks_for([1] * 6, month_branch='辰', day_ganzhi='甲辰')
    assert {key for key in checks if key.startswith('tomb_candidate:')} == {
        'tomb_candidate:primary:3', 'tomb_candidate:primary:6'}
    _, selected = checks_for([1] * 6, month_branch='辰', day_ganzhi='甲辰', yongshen_positions=[1])
    assert 'tomb_candidate:primary:1' in selected


def test_runtime_review_does_not_change_the_chart_used_for_corpus_compilation():
    chart = build_chart([2, 2, 1, 1, 1, 1], month_branch='辰', day_ganzhi='甲午',
                        yongshen_positions=[1], yongshen_scope='hidden')
    before = json.dumps(chart, ensure_ascii=False, sort_keys=True)
    checks = review_checks(chart)
    assert any(check['check_id'] == 'tomb_candidate:hidden:1' for check in checks)
    assert 'review_checks' not in chart['patterns']
    assert json.dumps(chart, ensure_ascii=False, sort_keys=True) == before


@pytest.mark.parametrize('selected,expected_hash', [
    (False, 'bd5024e72208141016789f2ab08e85845c3b59839f576e0a45de5b5d04e693da'),
    (True, '8ec2eb6deab2d3c2f59256c97c3b923540797b361a90b4aa9f067a4bc2e2ea1b'),
])
def test_single_move_reviews_hidden_life_stage_with_or_without_selection(selected, expected_hash):
    # Synthetic V6 snapshot: hidden fire at 2, primary metal at 5; no event outcome.
    options = dict(yongshen_positions=[2], yongshen_scope='hidden') if selected else {}
    chart = build_chart([1, 1, 1, 1, 3, 2], month_branch='辰', day_ganzhi='甲辰', **options)
    full_before = json.dumps(chart, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    before = json.dumps(without_relation_semantics(chart), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    checks = {item['check_id']: item for item in review_checks(chart)}
    single = checks['single_moving:primary:5']
    row, = single['trigger_facts']['hidden_life_stages']
    assert row['subject'] == {'scope': 'hidden', 'position': 2, 'branch': '巳',
                              'relative': '父母', 'element': '火', 'spirit': '朱雀', 'moving': None,
                              'basic_source_ids': ['liuyao_zixiu_dxj.full.l2136.rule',
                                                   'liuyao_zixiu_dxj.full.l2192.rule']}
    assert row['reference'] == {'scope': 'primary', 'position': 5, 'branch': '酉',
                                'relative': '子孙', 'element': '金', 'spirit': '白虎', 'moving': True,
                                'basic_source_ids': ['liuyao_zixiu_dxj.full.l2152.rule',
                                                     'liuyao_zixiu_dxj.full.l2204.rule']}
    assert row['stage'] == '死' and row['same_position_flying'] is False
    assert row['yongshen_candidate_supplied'] is selected
    assert row['get_source_requests'] == [
        {'evidence_id': 'liuyao_xiangfa_jinjie_shang.manual.p0264_si_death_absence'},
        {'evidence_id': 'liuyao_zixiu_dxj.full.l4076.rule'}]
    assert single['trigger_facts']['life_stage_table_reference_id'] == 'xf_shang_c03'
    assert single['status'] == 'needs_source_review'
    assert '伏神 父母 火 死 独发 酉 适用条件' in single['suggested_queries']
    conditions = ''.join(single['conditions_to_check'])
    assert 'required_contexts' in conditions and '旺衰' in conditions
    assert len(single['suggested_queries']) == len(set(single['suggested_queries']))
    # Preserve the pre-change shared result, not merely this call's input object.
    assert hashlib.sha256(before.encode('utf8')).hexdigest() == expected_hash
    assert json.dumps(chart, ensure_ascii=False, sort_keys=True, separators=(',', ':')) == full_before


@pytest.mark.parametrize('selected', [False, True])
def test_single_move_keeps_all_hidden_stages_and_same_position_flying(selected):
    options = dict(yongshen_positions=[1], yongshen_scope='hidden') if selected else {}
    chart, checks = checks_for([0, 2, 1, 1, 1, 1], month_branch='辰', day_ganzhi='甲辰', **options)
    single = checks['single_moving:primary:1']['trigger_facts']
    rows = single['hidden_life_stages']
    assert [(r['subject']['position'], r['subject']['element'], r['stage'],
             r['same_position_flying'], r['yongshen_candidate_supplied']) for r in rows] == [
        (1, '水', '墓', True, selected), (2, '木', '衰', False, False)]
    assert all(r['subject']['scope'] == 'hidden' and r['subject']['moving'] is None for r in rows)
    assert all(r['reference']['scope'] == 'primary' and r['reference']['position'] == 1
               and r['reference']['branch'] == '辰' and r['reference']['moving'] is True for r in rows)
    assert all('get_source_requests' not in r for r in rows)
    assert single['own_transformation']['branch'] == chart['lines'][0]['transformation']['branch']
    assert single['own_transformation']['scope'] == 'changed'
    assert single['key_relations']  # Existing relation fields remain present.


@pytest.mark.parametrize('values', [
    [2, 2, 1, 1, 1, 1],  # Static chart still has a changed-lines display.
    [0, 2, 3, 1, 1, 1],  # Two real moving lines.
    [3, 1, 1, 1, 1, 1],  # Single move, but no hidden lines.
])
def test_hidden_life_stage_attachment_requires_one_real_move_and_hidden_lines(values):
    _, checks = checks_for(values, month_branch='辰', day_ganzhi='甲辰')
    assert not any('hidden_life_stages' in check['trigger_facts'] for check in checks.values())
    for key, check in checks.items():
        if key.startswith('single_moving:'):
            assert set(check['trigger_facts']) == {'moving_line', 'key_relations', 'own_transformation'}
            assert len(check['conditions_to_check']) == len(check['suggested_queries']) == 2


def test_hidden_life_stage_source_requests_are_not_verification_without_a_database(tmp_path, monkeypatch):
    from liuyao_mcp.server import build_chart as runtime_chart

    absent = tmp_path/'absent.sqlite'
    monkeypatch.setenv('LIUYAO_DB', str(absent))
    chart = runtime_chart([1, 1, 1, 1, 3, 2], month_branch='辰', day_ganzhi='甲辰')
    single = next(c for c in chart['patterns']['review_checks'] if c['check_id']=='single_moving:primary:5')
    assert single['trigger_facts']['hidden_life_stages'][0]['stage'] == '死'
    assert single['status'] == 'needs_source_review'
    assert chart['patterns']['resolved_references']['xf_shang_c03']['status'] == 'unavailable'
    assert all(set(request) == {'evidence_id'}
               for request in single['trigger_facts']['hidden_life_stages'][0]['get_source_requests'])
    assert not absent.exists()


def test_moving_fuyin_facts_share_one_review_group_and_keep_their_participants():
    chart, checks = checks_for([1, 3, 3, 1, 1, 1], month_branch='卯', day_ganzhi='乙卯')
    reference = 'rule_liuyao_zixiu_dxj_4784'
    group = checks['pattern_source:'+reference]['trigger_facts']
    assert group['source_rule_id'] == reference
    fuyin_pattern = next(item for item in group['matched_patterns'] if item['pattern_id'] == 'line_fuyin')
    fuyin = [chart['patterns']['facts'][index] for index in fuyin_pattern['fact_indexes_zero_based']]
    assert {fact['participants'][0]['position'] for fact in fuyin} == {2, 3}
    assert all(fact['participants'][1]['scope'] == 'changed' for fact in fuyin)
    assert any('明动' in item['roles'] for item in group['focus_refs'])
    assert any('爻变伏吟' in query for query in checks['pattern_source:'+reference]['suggested_queries'])
    groups = [check['trigger_facts']['source_rule_id'] for key, check in checks.items()
              if key.startswith('pattern_source:')]
    assert len(groups) == len(set(groups))
    assert set(groups) <= set(chart['patterns']['source_rule_ids'])


def test_pattern_groups_filter_unrelated_facts_without_erasing_them():
    chart, checks = checks_for([1] * 6, month_branch='卯', day_ganzhi='乙卯')
    all_self = [fact for fact in chart['patterns']['facts'] if fact['pattern_id'] == 'self_punishment_branch']
    assert {fact['participants'][0]['position'] for fact in all_self} == {3, 4}
    indexes = checks['pattern_source:xf_xia_c04_s05']['trigger_facts']['matched_patterns'][0]['fact_indexes_zero_based']
    grouped = [chart['patterns']['facts'][index] for index in indexes]
    assert {fact['participants'][0]['position'] for fact in grouped} == {3}
    groups = {check['trigger_facts']['source_rule_id'] for key, check in checks.items()
              if key.startswith('pattern_source:')}
    assert all(check['source_rule_id'] not in groups for check in chart['patterns']['combination_checks']
               if check['status'] != 'structural_match')


def test_descriptive_review_keeps_palace_and_selected_person_line_separate():
    # 已曝光 R01C01 的初始盘，只测试坎宫与父母酉金并列，不编码具体病象。
    _, checks = checks_for([1, 0, 1, 1, 1, 2], month_branch='未', day_ganzhi='己巳',
                           yongshen_positions=[5])
    images = checks['key_images']['trigger_facts']
    assert images['primary_hexagram'] == {
        'name': '革', 'palace': '坎', 'palace_element': '水', 'upper': '兑', 'lower': '离'}
    parent = next(line for line in images['key_lines'] if line['position'] == 5)
    assert (parent['scope'], parent['relative'], parent['branch'], parent['element']) == ('primary', '父母', '酉', '金')
    assert parent['roles'] == ['用神候选']
    assert any('人物用神' in text and '分层' in text for text in checks['key_images']['conditions_to_check'])


def test_static_responding_line_keeps_spirit_and_upper_position_visible():
    # 已曝光 R01C06，静应父戌白虎上爻仍有取象待查入口。
    _, checks = checks_for([2, 2, 2, 1, 1, 1], month_branch='酉', day_ganzhi='壬子')
    images = checks['key_images']['trigger_facts']
    responding = next(line for line in images['key_lines'] if '应' in line['roles'])
    assert (responding['position'], responding['relative'], responding['branch'], responding['spirit']) == (6, '父母', '戌', '白虎')
    assert responding['moving'] is False
    assert 'moving_relationships' not in checks


def test_moving_parent_can_reach_unselected_hidden_wealth_without_replacing_use_role():
    # 已曝光 R02C02 的动父戌合伏财卯；辅助线索不需要先选为主用神。
    _, checks = checks_for([2, 2, 1, 2, 3, 0], month_branch='丑', day_ganzhi='丙戌')
    group = checks['moving_relationships']['trigger_facts']
    hidden = group['auxiliary_hidden'][0]
    assert (hidden['scope'], hidden['position'], hidden['relative'], hidden['branch']) == ('hidden', 2, '妻财', '卯')
    assert hidden['moving'] is None and hidden['flying_ref']['position'] == 2
    actor = next(line for line in group['moving_lines'] if line['position'] == 5)
    assert actor['scope'] == 'primary' and actor['relative'] == '父母' and actor['branch'] == '戌'
    assert [5, 'hidden', 2, ['合', '受克'], False] in group['rows']
    assert [5, 'primary', 4, ['生'], False] in group['rows']
    # 对静日冲应爻的明动关系已在 static_day_clash 中，不在关系表重复。
    assert 'static_day_clash:primary:1' in checks
    assert not any(row[1:3] == ['primary', 1] for row in group['rows'])
    assert group['actor_scope'] == 'primary' and len(group['own_transformations']) == 2


def test_selected_hidden_layer_and_same_position_flying_relation_are_distinct():
    _, chosen = checks_for([2, 2, 1, 2, 3, 0], month_branch='丑', day_ganzhi='丙戌',
                           yongshen_positions=[2], yongshen_scope='hidden')
    group = chosen['moving_relationships']['trigger_facts']
    assert group['auxiliary_hidden'] == []
    assert {'scope': 'hidden', 'position': 2, 'branch': '卯'} in group['key_target_refs']
    _, flying = checks_for([0, 2, 1, 1, 1, 1], month_branch='辰', day_ganzhi='甲午')
    group = flying['moving_relationships']['trigger_facts']
    assert [1, 'hidden', 1, ['克'], True] in group['rows']
    assert group['own_transformations'] == []  # Already in the single-move check.
    assert not group['key_target_refs']  # No duplicate of single-move key relations.


def test_no_hidden_lines_produce_no_auxiliary_targets_and_changed_lines_never_act_across_positions():
    _, checks = checks_for([3, 3, 1, 1, 1, 1], month_branch='卯', day_ganzhi='乙卯',
                           yongshen_positions=[1], yongshen_scope='changed')
    group = checks['moving_relationships']['trigger_facts']
    assert group['auxiliary_hidden'] == [] and group['actor_scope'] == 'primary'
    assert all(row[1] != 'changed' for row in group['rows'])
    assert {row[0] for row in group['own_transformations']} == {1, 2}
    images = checks['key_images']['trigger_facts']['key_lines']
    changed = next(line for line in images if line['scope'] == 'changed')
    assert changed['moving'] is None and changed['position'] == 1


def test_six_clash_and_harmony_use_actual_branch_pairs_and_only_actual_changes():
    _, checks = checks_for([3, 3, 3, 1, 1, 1], month_branch='卯', day_ganzhi='乙卯')
    assert checks['six_relations']['trigger_facts']['hexagrams'] == [
        {'scope': 'primary', 'hexagram': '乾', 'six_clash': True, 'six_harmony': False},
        {'scope': 'changed', 'hexagram': '否', 'six_clash': False, 'six_harmony': True}]
    _, stationary = checks_for([2, 2, 2, 1, 1, 1], month_branch='酉', day_ganzhi='壬子')
    assert [item['scope'] for item in stationary['six_relations']['trigger_facts']['hexagrams']] == ['primary']
    _, returning = checks_for([1, 1, 2, 1, 2, 2], month_branch='子', day_ganzhi='甲子')
    assert 'palace_stage:primary' in returning and 'six_relations' not in returning


@pytest.mark.parametrize('scope,values,branch,relative,relative_id,expected_hash', [
    ('primary', [2, 2, 1, 1, 1, 1], '辰', '父母', 'liuyao_zixiu_dxj.full.l2136.rule',
     '9fe1e58d3f8573c605f061950c0f3fa4f21613f6460731c3c4cae772d73f62db'),
    ('hidden', [2, 2, 1, 1, 1, 1], '子', '子孙', 'liuyao_zixiu_dxj.full.l2152.rule',
     '533c1aec024dbbd36cd5fdc50b481715f59a455b855eb999722dee759a7b5b59'),
    ('changed', [3, 1, 1, 1, 1, 1], '丑', '父母', 'liuyao_zixiu_dxj.full.l2136.rule',
     'ec3939f11ac630736278043968e41769068f30f825c72fccb03c1163367a7d06'),
])
def test_basic_sources_bind_to_selected_layer_and_preserve_runtime(scope, values, branch, relative,
                                                                 relative_id, expected_hash):
    chart, checks = checks_for(values, month_branch='辰', day_ganzhi='甲辰',
                              yongshen_positions=[1], yongshen_scope=scope)
    image = next(line for line in checks['key_images']['trigger_facts']['key_lines']
                 if line['scope'] == scope and line['position'] == 1)
    assert (image['branch'], image['relative'], image['spirit']) == (branch, relative, '青龙')
    assert image['moving'] is (False if scope == 'primary' else None)
    assert image['basic_source_ids'] == [relative_id, 'liuyao_zixiu_dxj.full.l2188.rule']
    assert '用神候选' in image['roles']
    # Hashes captured from the complete chart/review output before adding the field.
    original = {'chart': without_relation_semantics(chart), 'checks': without_basic_sources(list(checks.values()))}
    encoded = json.dumps(original, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    assert hashlib.sha256(encoded.encode('utf8')).hexdigest() == expected_hash


def test_basic_sources_reach_unselected_hidden_parent_without_expanding_key_lines():
    # 已曝光盘面；只验证层、位置和来源入口，不编码事件解释。
    chart, checks = checks_for([1, 1, 1, 0, 2, 2], month_branch='亥', day_ganzhi='丙辰')
    assert chart['patterns']['yongshen_refs'] == []
    images = checks['key_images']['trigger_facts']['key_lines']
    assert [(line['scope'], line['position'], line['roles']) for line in images] == [
        ('primary', 3, ['世']), ('primary', 6, ['应'])]
    row, = checks['single_moving:primary:4']['trigger_facts']['hidden_life_stages']
    assert row['yongshen_candidate_supplied'] is False
    hidden, = checks['moving_relationships']['trigger_facts']['auxiliary_hidden']
    for image in (row['subject'], hidden):
        assert (image['scope'], image['position'], image['branch'], image['relative'], image['spirit']) == (
            'hidden', 2, '巳', '父母', '勾陈')
        assert image['moving'] is None
        assert image['basic_source_ids'] == [
            'liuyao_zixiu_dxj.full.l2136.rule', 'liuyao_zixiu_dxj.full.l2196.rule']
        assert not set(image['basic_source_ids']) & set(chart['patterns']['source_rule_ids'])


def test_review_packet_is_bounded_and_never_claims_source_verification_or_outcomes():
    snapshot = hashlib.sha256()
    for bits in range(64):
        for moving in ('static', 'all', 'single'):
            values = [(3 if bits >> i & 1 else 0) if moving=='all' else (1 if bits >> i & 1 else 2)
                      for i in range(6)]
            if moving=='single':
                position = bits % 6
                values[position] = 3 if values[position]==1 else 0
            chart = build_chart(values, month_branch='辰', day_ganzhi='甲辰', yongshen_positions=list(range(1, 7)))
            checks = review_checks(chart)
            original = {'chart': without_relation_semantics(chart), 'checks': without_basic_sources(checks)}
            snapshot.update(json.dumps(original, ensure_ascii=False, sort_keys=True,
                                       separators=(',', ':')).encode('utf8'))
            assert len(checks) <= 40 and len(json.dumps(checks, ensure_ascii=False)) < 24000
            for check in checks:
                assert set(check) == {'check_id', 'status', 'trigger_facts', 'conditions_to_check', 'suggested_queries'}
                assert check['status'] == 'needs_source_review'
                assert check['conditions_to_check'] and check['suggested_queries']
                text = json.dumps(check, ensure_ascii=False)
                assert all(key not in text for key in ('available', 'judgment', 'prediction', 'weight'))
                assert all(outcome not in query for query in check['suggested_queries']
                           for outcome in ('通过', '失败', '不来', '必来', '吉凶', '改分', '工资欠发', '痰', '眼', '肺癌'))
    # The existing 192-chart sweep must retain every prior field after stripping the new IDs.
    assert snapshot.hexdigest() == 'e65ec30e111cace1ea74daf8084c1620c9550ad06471b8c86f76f1402f44be33'
