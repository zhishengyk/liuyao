"""Mechanical motifs in the registered books; interpretation stays conditional."""
from itertools import combinations, product

from .chart import BRANCHES, BRANCH_ELEMENT, relation

VERSION = 'book-structure-2'
STAGES = ('长生','沐浴','冠带','临官','帝旺','衰','病','死','墓','绝','胎','养')
START = {'木':'亥','火':'寅','金':'巳','水':'申','土':'申'}
# 墓库概论（上册 p0277 规则共享上下文）的五行定位，不采用完整十二阶段推布来认定效力。
TOMB_BRANCH = {'木':'未','火':'戌','金':'丑','水':'辰','土':'辰'}
HARM = {frozenset(p) for p in ('子未','丑午','寅巳','卯辰','申亥','酉戌')}
OPPOSED = {frozenset(p) for p in ('乾巽','坎离','艮坤','震兑')}
EARLY_OPPOSED = {frozenset(p) for p in ('乾坤','震巽','艮兑','离坎')}
DIRECTION_PAIRS = {frozenset(p) for p in ('丑寅','辰巳','未申','戌亥')}
LABELS={'three_punishments':'三刑三支组合','partial_three_punishments':'三刑两支关系',
        'three_harmony_candidate':'三合支组候选','half_harmony_candidate':'半合支组候选',
        'zi_mao_punishment':'子卯刑','double_punishment':'双刑','self_punishment_branch':'自刑支出现',
        'harm':'相害','upper_lower_fanyin':'上下卦方位反吟','trigram_change_fanyin':'卦变方位反吟',
        'early_trigram_change_fanyin':'先天方位卦变反吟','line_fanyin':'爻变反吟','line_fuyin':'爻变伏吟',
        'all_transform_harm':'全化害','line_change_clash':'动爻变支相冲','line_change_same_branch':'动爻变支相同',
        'geshan_chain':'隔山化爻','relative_position_change':'同类爻进退位比较',
        'hidden_flying_relation':'飞伏五行关系'}
COMBINATION_LABELS=['父母白虎动克世','父母与日辰关联','父财互化','青龙子孙临世用',
                    '白虎子孙月破','螣蛇子孙','青龙官鬼临世用','玄武持世','玄武兄弟发动',
                    '勾陈临宅位','世用在五爻','世应虎雀对立','世应同五行','子孙虎马与游魂',
                    '官鬼伏藏与妻财月破','财子伏藏组合','世应世用同宫','用神候选化进退']


def stage(element, branch):
    return STAGES[(BRANCHES.index(branch)-BRANCHES.index(START[element])) % 12]


def ref(line, scope='primary'):
    return {'scope':scope,'position':line['position'],'branch':line['branch']}


def detect(chart, yongshen_positions=None, yongshen_scope='primary'):
    selected = set(yongshen_positions or [])
    if any(type(p) is not int or not 1 <= p <= 6 for p in selected):
        raise ValueError('用神候选爻位须在1..6之间')
    if yongshen_scope not in ('primary','hidden','changed'):
        raise ValueError('yongshen_scope须为primary、hidden或changed')
    lines = chart['lines']
    selected_primary = selected if yongshen_scope == 'primary' else set()
    yongshen = []
    for position in sorted(selected):
        line = lines[position-1]
        candidate = line if yongshen_scope == 'primary' else line['hidden' if yongshen_scope=='hidden' else 'transformation']
        if candidate is None:
            label = '伏神' if yongshen_scope=='hidden' else '动爻所化变爻'
            raise ValueError(f'第{position}爻没有{label}，不能用另一层的爻代替')
        yongshen.append(candidate)
    shi = lines[chart['shi_position']-1]
    ying = lines[chart['ying_position']-1]
    moving = [l for l in lines if l['moving']]
    facts = []
    def add(code, refs, rule, **details):
        label=COMBINATION_LABELS[int(code[-2:])-1] if code.startswith('combination_') else LABELS.get(code,code.replace('transform_','化'))
        facts.append({'pattern_id':code,'label':label,'participants':refs,'source_rule_id':rule,**details})
    calendar = [{'scope':'month','branch':chart['calendar']['month_branch']},
                {'scope':'day','branch':chart['calendar']['day_ganzhi'][1]}]

    stages = []
    for l in lines:
        for target in calendar + [ref(t) for t in lines if t['position']!=l['position']]:
            state=stage(l['element'], target['branch'])
            stages.append({'position':l['position'],'reference':target,'stage':state})
        if l['moving']:
            target=ref(l['transformation'],'changed')
            state=stage(l['element'],target['branch'])
            stages.append({'position':l['position'],'reference':target,'stage':state})
            if state in ('长生','病','死','墓','绝'):
                add('transform_'+state,[ref(l),target],'xf_shang_c03',stage=state)

    current=[ref(l) for l in lines]+calendar
    active=[ref(l) for l in moving]+[ref(l['transformation'],'changed') for l in moving]+calendar
    for family in ('申子辰','巳酉丑','寅午戌','亥卯未'):
        groups=[[r for r in active if r['branch']==branch] for branch in family]
        if all(groups):
            for participants in product(*groups):
                if any(r['scope']!='month' and r['scope']!='day' for r in participants):
                    add('three_harmony_candidate',list(participants),'rule_liuyao_zixiu_dxj_4520',family=family,
                        requires='空破墓、暗动和成局时点须另核，静爻未直接计入')
        elif groups[1] and sum(bool(g) for g in groups)==2:
            present=[g for g in groups if g]
            for participants in product(*present):
                if any(r['scope']=='primary' for r in participants):
                    add('half_harmony_candidate',list(participants),'rule_liuyao_zixiu_dxj_4520',family=family,
                        missing=[family[i] for i,g in enumerate(groups) if not g])
    for family,rule in [('寅巳申','xf_xia_c04_s02'),('丑未戌','xf_xia_c04_s03')]:
        groups=[[r for r in current if r['branch']==branch] for branch in family]
        if all(groups):
            for participants in product(*groups):
                count=sum(r['scope']=='primary' for r in participants)
                if count:
                    add('three_punishments',list(participants),rule,family=family,
                        formation={3:'卦内三支齐见',2:'卦内两支借日月',1:'卦内一支借日月'}[count])
    # Distinguish a visible relation from an active moving/day/month relation.
    actors=[ref(l) for l in moving]+calendar
    edges=[(actor,ref(t)) for actor in actors for t in lines
           if actor.get('position')!=t['position']]
    edges += [(ref(l['transformation'],'changed'),ref(l)) for l in moving]
    for a,b in edges:
        pair=frozenset((a['branch'],b['branch']))
        if pair==frozenset('子卯'):
            add('zi_mao_punishment',[a,b],'xf_xia_c04_s01')
        elif len(pair)==2 and (pair<=set('寅巳申') or pair<=set('丑未戌')):
            add('partial_three_punishments',[a,b], 'xf_xia_c04_s02' if pair<=set('寅巳申') else 'xf_xia_c04_s03')
        if pair in HARM:
            relations=relation(a['branch'],b['branch'])
            kind='生中带害' if '生' in relations else '克中带害' if '克' in relations else '纯相害'
            add('harm',[a,b],{'生中带害':'xf_xia_c10_u01','克中带害':'xf_xia_c10_u02','纯相害':'xf_xia_c10_u03'}[kind],kind=kind)
    for a,b in combinations(lines,2):
        selected_pair = (a['shi'] and (b['ying'] or b['position'] in selected_primary)) or (b['shi'] and (a['ying'] or a['position'] in selected_primary))
        if a['element']==b['element'] and (a['moving'] or b['moving'] or selected_pair):
            add('double_punishment',[ref(a),ref(b)],'xf_xia_c04_s04',same_branch=a['branch']==b['branch'])
    for l in lines:
        if l['branch'] in '辰午酉亥':
            add('self_punishment_branch',[ref(l)],'xf_xia_c04_s05',
                note='本书单支自刑取象定义；不等同于通行的两支自刑判法')
    for scope in ('primary','changed'):
        h=chart[scope]
        if frozenset((h['upper'],h['lower'])) in OPPOSED:
            add('upper_lower_fanyin',[],'xf_xia_c07_u01',scope=scope)
    for side in ('upper','lower'):
        if frozenset((chart['primary'][side],chart['changed'][side])) in OPPOSED:
            add('trigram_change_fanyin',[],'xf_xia_c07_u02',side=side)
        if frozenset((chart['primary'][side],chart['changed'][side])) in EARLY_OPPOSED:
            add('early_trigram_change_fanyin',[],'rule_liuyao_zixiu_dxj_4784',side=side)
    for l in moving:
        if '冲' in relation(l['transformation']['branch'],l['branch']):
            add('line_fanyin',[ref(l),ref(l['transformation'],'changed')],'rule_liuyao_zixiu_dxj_4784')
        if l['branch']==l['transformation']['branch']:
            add('line_fuyin',[ref(l),ref(l['transformation'],'changed')],'rule_liuyao_zixiu_dxj_4784')
    for lower,upper in ((1,3),(4,6)):
        members=[l for l in moving if lower<=l['position']<=upper]
        if len(members)==3 and all(frozenset((l['branch'],l['transformation']['branch'])) in HARM for l in members):
            add('all_transform_harm',[ref(l) for l in members],'xf_xia_c10_u04')
        if members and all('冲' in relation(l['transformation']['branch'],l['branch']) for l in members):
            add('line_change_clash',[ref(l) for l in members],'rule_liuyao_zixiu_dxj_4784',side='lower' if lower==1 else 'upper')
        if members and all(l['branch']==l['transformation']['branch'] for l in members):
            add('line_change_same_branch',[ref(l) for l in members],'rule_liuyao_zixiu_dxj_4784',side='lower' if lower==1 else 'upper',
                note='爻变伏吟结构；取用与适用条件另查理法')

    def chain(path):
        last=path[-1]
        for nxt in moving:
            if nxt in path or last['transformation']['branch']!=nxt['branch']:continue
            new=path+[nxt]
            positions=[l['position'] for l in new]
            direction='顺隔' if positions==sorted(positions) else '逆隔' if positions==sorted(positions,reverse=True) else '混合方向'
            add('geshan_chain',[ref(l) for l in new]+[ref(nxt['transformation'],'changed')],
                'xf_xia_c09',direction=direction,
                note='隔爻链条不视为起始爻直接回头生克')
            chain(new)
    for l in moving:chain([l])
    for l in moving:
        target=l['transformation']
        for base in lines:
            if base['position']==l['position'] or base['relative']!=target['relative']:continue
            if base['branch']==target['branch']:
                delta=l['position']-base['position']
                direction='进位' if delta>0 else '退位'
                basis='爻位上下'
            elif BRANCH_ELEMENT[base['branch']]==target['element']:
                pair=(base['branch'],target['branch'])
                delta=BRANCHES.index(pair[1])-BRANCHES.index(pair[0])
                if pair==('亥','子'):delta=1
                if pair==('子','亥'):delta=-1
                direction='进位' if delta>0 else '退位';basis='同五行地支顺序'
            else:continue
            add('relative_position_change',[ref(base),ref(target,'changed')],'xf_xia_c08',
                direction=direction,basis=basis,requires='两爻是否代表可比较的对象，需结合场景与取用')

    hidden=[l['hidden'] for l in lines if l['hidden']]
    transformed=[l['transformation'] for l in moving]
    for l in lines:
        if l['hidden']:
            add('hidden_flying_relation',[ref(l),ref(l['hidden'],'hidden')],'xf_xia_c05',
                relations=relation(l['branch'],l['hidden']['branch']))
    selected_roles=[l for l in yongshen if yongshen_scope!='primary' or not l.get('shi')]
    roles=[shi]+selected_roles
    day=calendar[1]['branch']
    yima = dict(zip('申子辰寅午戌巳酉丑亥卯未','寅寅寅申申申亥亥亥巳巳巳'))[day]
    motifs = {
      1:[l for l in moving if l['relative']=='父母' and l['spirit']=='白虎' and '克' in relation(l['branch'],shi['branch'])],
      2:[l for l in lines if l['relative']=='父母' and (l['branch']==day or '合' in relation(day,l['branch']) or l['element']==BRANCH_ELEMENT[day])],
      3:[l for l in moving if {l['relative'],l['transformation']['relative']}=={'父母','妻财'}],
      4:[l for l in roles if l['relative']=='子孙' and l['spirit']=='青龙'],
      5:[l for l in lines if l['relative']=='子孙' and l['spirit']=='白虎' and l['month_break']],
      6:[l for l in lines if l['relative']=='子孙' and l['spirit']=='螣蛇'],
      7:[l for l in roles if l['relative']=='官鬼' and l['spirit']=='青龙'],
      8:[shi] if shi['spirit']=='玄武' else [],
      9:[l for l in moving if l['relative']=='兄弟' and l['spirit']=='玄武'],
      10:[l for l in roles if l['position']==2 and l['spirit']=='勾陈'],
      11:[l for l in roles if l['position']==5],
      12:[shi,ying] if {shi['spirit'],ying['spirit']}=={'白虎','朱雀'} else [],
      13:[shi,ying] if shi['element']==ying['element'] else [],
      14:[l for l in lines if l['relative']=='子孙' and (l['spirit']=='白虎' or l['branch']==yima) and chart['primary']['palace_stage']=='游魂'],
      15:[l for l in lines if l['relative']=='妻财' and l['month_break']] if any(l['relative']=='官鬼' for l in hidden) else [],
      16:hidden if {'妻财','子孙'} <= {l['relative'] for l in hidden} else [],
      17:[t for t in [ying]+selected_roles
          if t['branch']==shi['branch'] or frozenset((shi['branch'],t['branch'])) in DIRECTION_PAIRS],
      18:[l for l in moving if l['position'] in selected_primary and (l['transformation']['advance'] or l['transformation']['retreat'])]}
    for number,participants in motifs.items():
        if participants:
            if number==17:participants=[shi]+participants
            add(f'combination_{number:02}',[ref(l,'hidden' if l in hidden else 'changed' if l in transformed else 'primary') for l in participants],
                f'xf_shang_c02_u{number:02}',requires='原文场景、对象与旺衰条件；此处仅检出盘面前提')
    checks=[{'source_rule_id':f'xf_shang_c02_u{number:02}',
             'status':'structural_match' if participants else 'needs_yongshen' if not selected and number in (4,7,10,11,17,18) else 'not_detected',
             'interpretation':'requires_scene_and_original_conditions'} for number,participants in motifs.items()]
    return {'version':VERSION,'ruleset':'逐项按所附书籍规则识别，保留作者体系边界', 'facts':facts,'combination_checks':checks,
            'life_stages':stages, 'source_rule_ids':sorted({f['source_rule_id'] for f in facts}|{'xf_shang_c03'}),
            'yongshen_candidates_supplied':sorted(selected),
            'yongshen_scope':yongshen_scope,'yongshen_refs':[ref(l,yongshen_scope) for l in yongshen],
            'requires_context': ['用神与元神的具体爻位、场景、旺衰及原文例外不能由结构匹配自动推出'],
            'boundary':'命中结构不等于事件结论或吉凶；缺失的场景条件保留待判断'}


def review_checks(chart):
    """Runtime-only source-review prompts; do not persist these in derived cases."""
    lines = chart['lines']
    shi, ying = lines[chart['shi_position']-1], lines[chart['ying_position']-1]
    moving = [line for line in lines if line['moving']]
    calendar = [{'scope':'month','branch':chart['calendar']['month_branch']},
                {'scope':'day','branch':chart['calendar']['day_ganzhi'][1]}]
    selected = []
    for candidate in chart['patterns']['yongshen_refs']:
        line, scope = lines[candidate['position']-1], candidate['scope']
        selected.append((line if scope=='primary' else line['hidden' if scope=='hidden' else 'transformation'],scope,'用神候选'))
    checks = []
    def review(check_id, trigger, conditions, queries):
        checks.append({'check_id':check_id, 'status':'needs_source_review',
                       'trigger_facts':trigger, 'conditions_to_check':conditions,
                       'suggested_queries':queries})
    def describe(line, scope='primary'):
        return {**ref(line,scope), **{key:line[key] for key in
                ('relative','element','spirit','moving','void','month_relations','day_relations')}}

    key_lines = {}
    for line,scope,role in [(shi,'primary','世'),(ying,'primary','应')]+selected:
        entry = key_lines.setdefault((scope,line['position']), {'line':line,'roles':[]})
        entry['roles'].append(role)

    basic_sources = {
        '父母':'liuyao_zixiu_dxj.full.l2136.rule',
        '官鬼':'liuyao_zixiu_dxj.full.l2140.rule',
        '兄弟':'liuyao_zixiu_dxj.full.l2144.rule',
        '妻财':'liuyao_zixiu_dxj.full.l2148.rule',
        '子孙':'liuyao_zixiu_dxj.full.l2152.rule',
        '青龙':'liuyao_zixiu_dxj.full.l2188.rule',
        '朱雀':'liuyao_zixiu_dxj.full.l2192.rule',
        '勾陈':'liuyao_zixiu_dxj.full.l2196.rule',
        '螣蛇':'liuyao_zixiu_dxj.full.l2200.rule',
        '白虎':'liuyao_zixiu_dxj.full.l2204.rule',
        '玄武':'liuyao_zixiu_dxj.full.l2208.rule',
    }
    def image_ref(line, scope='primary'):
        return {**ref(line,scope), **{key:line[key] for key in ('relative','element','spirit','moving')},
                'basic_source_ids':[basic_sources[line['relative']],basic_sources[line['spirit']]]}

    primary = chart['primary']
    review('key_images',
           {'primary_hexagram':{key:primary[key] for key in ('name','palace','palace_element','upper','lower')},
            'key_lines':[{**image_ref(entry['line'],scope),'roles':entry['roles']}
                         for (scope,_),entry in key_lines.items()]},
           ['按原问判断是否需要特征、原因或位置，分别查卦宫、上下卦和关键爻取象；吉凶或转归不能代替描述。',
            '人物用神与事项或症状取象分层；宫与爻的五行分别保留，不自动对应具体病名、事件或发生时态。'],
           [f"{primary['palace']}宫 {primary['upper']} {primary['lower']} 卦象 取象"]+
           list(dict.fromkeys(f"第{position}爻 {entry['line']['relative']} {entry['line']['element']} {entry['line']['spirit']} 取象"
                              for (scope,position),entry in key_lines.items())))

    def key_relations(actor):
        result = []
        for (scope,position),entry in key_lines.items():
            if scope=='primary' and position==actor['position']:
                continue
            target = entry['line']
            # 变爻不作为跨位作用者，也不假定本卦爻可对异位变爻发生作用。
            result.append({'target':ref(target,scope), 'roles':entry['roles'],
                           'relations_from_primary':relation(actor['branch'],target['branch']) if scope!='changed' else None,
                           'effect_status':'requires_scope_and_source_conditions'})
        return result

    if len(moving)==1:
        line = moving[0]
        changed = line['transformation']
        role = '世爻' if line['shi'] else '应爻' if line['ying'] else f"第{line['position']}爻"
        shi_relations = [] if line['shi'] else [r+'世' for r in relation(line['branch'],shi['branch']) if r in ('生','克','冲','合')]
        change_terms = ['化空'] if changed['void'] else []
        review(f"single_moving:primary:{line['position']}",
               {'moving_line':describe(line), 'key_relations':key_relations(line),
                'own_transformation':{**describe(changed,'changed'),
                                      'to_original_relations':changed['to_original_relations']}},
               ['核对独发规则的场景、主体及世应或用神角色，不能只按普通多动卦条件套用。',
                '核对日月、空破及变爻条件是否限制本动爻，再追踪它对所问对象的作用；五行关系本身不等于有效作用。'],
               [f"{role} {line['relative']} 独发 {' '.join(shi_relations)}".strip(),
                ' '.join(['独发','动爻',line['branch'],'化'+changed['branch'],*change_terms,'作用条件'])])
        hidden_stages = []
        for parent in lines:
            hidden = parent['hidden']
            if hidden:
                item = {'subject':image_ref(hidden,'hidden'), 'reference':image_ref(line),
                        'stage':stage(hidden['element'],line['branch']),
                        'same_position_flying':hidden['position']==line['position'],
                        'yongshen_candidate_supplied':('hidden',hidden['position']) in key_lines}
                if item['stage']=='死':
                    item['get_source_requests'] = [
                        {'evidence_id':'liuyao_xiangfa_jinjie_shang.manual.p0264_si_death_absence'},
                        {'evidence_id':'liuyao_zixiu_dxj.full.l4076.rule'}]
                hidden_stages.append(item)
        if hidden_stages:
            single = checks[-1]
            single['trigger_facts'].update(hidden_life_stages=hidden_stages,
                                          life_stage_table_reference_id='xf_shang_c03')
            single['conditions_to_check'] += [
                '阶段方向为伏神五行在唯一明动爻地支上的状态，不是生克方向；须核本位/异位、伏神与独发场景、旺衰空破及变爻限制。',
                '阶段名不等于吉凶或失效；表入口未证明全部适用。get_source_requests仅为回查入口，须读全文及required_contexts，死地也不自动决定结果或优先级。']
            single['suggested_queries'] = list(dict.fromkeys(single['suggested_queries'] + [
                f"伏神 {item['subject']['relative']} {item['subject']['element']} {item['stage']} 独发 {line['branch']} 适用条件"
                for item in hidden_stages]))

    auxiliary = [line['hidden'] for line in lines if line['hidden']
                 and ('hidden',line['position']) not in key_lines]
    if moving and (auxiliary or len(moving)>1):
        # Single-move and static-day-clash checks already carry their key-line relations.
        targets = [(scope,entry['line']) for (scope,_),entry in key_lines.items()
                   if len(moving)>1 and scope!='changed'
                   and not (scope=='primary' and entry['line']['moving'] is False and entry['line']['day_clash'])]
        targets += [('hidden',line) for line in auxiliary]
        rows, queries = [], []
        for actor in moving:
            for scope,target in targets:
                if scope=='primary' and actor['position']==target['position']:
                    continue
                relations = relation(actor['branch'],target['branch'])
                rows.append([actor['position'],scope,target['position'],relations,
                             scope=='hidden' and actor['position']==target['position']])
                if scope=='hidden':
                    queries.append(f"{actor['relative']}动 伏神{target['relative']} {' '.join(relations)} 适用条件")
        if len(moving)>1:
            queries.append('多动 世应 用神 生克 变爻 作用范围')
        review('moving_relationships',
               {'actor_scope':'primary','moving_lines':[image_ref(line) for line in moving],
                'key_target_refs':[ref(line,scope) for scope,line in targets if (scope,line['position']) in key_lines],
                'auxiliary_hidden':[{**image_ref(line,'hidden'),'flying_ref':ref(lines[line['position']-1])}
                                    for line in auxiliary],
                'columns':['actor_position','target_scope','target_position','relations_from_actor','same_position_flying'],
                'rows':rows,
                'own_transformation_columns':['position','changed_branch','changed_relative','to_original_relations'],
                'own_transformations':[[line['position'],line['transformation']['branch'],line['transformation']['relative'],
                                        line['transformation']['to_original_relations']] for line in moving] if len(moving)>1 else []},
               ['关系方向均从本卦明动爻到目标；本位飞伏与异位明动分开核查，辅助伏神不自动替代人物或事项主用神。',
                '按原问补查辅助信息及其作用条件；本表只列变爻本位回头关系，其他跨层象法须凭原文另行核查。单动或静日冲已列的关键关系不在此重复。'],
               list(dict.fromkeys(queries)))

    for line in lines:
        if line['moving'] is False and line['day_clash']:
            review(f"static_day_clash:primary:{line['position']}",
                   {'line':describe(line), 'moving_relations':[
                       {'actor':describe(actor), 'relations_to_line':relation(actor['branch'],line['branch'])}
                       for actor in moving], 'key_relations':key_relations(line)},
                   ['结合月令和实际动爻生克核查暗动或日破，日冲本身不确定效力。',
                    '若原文支持暗动，继续核对该爻对世应及用神的作用；自身受生不能直接替代所问结果。'],
                   [f"{line['relative']} 静爻 日冲 暗动 日破",
                    f"{line['relative']} 暗动 用神 生克 条件"])

    for (scope,position),entry in key_lines.items():
        line = entry['line']
        tomb_branch = TOMB_BRANCH[line['element']]
        sources = [{**item,'kind':item['scope']} for item in calendar]
        sources += [{**describe(actor),'kind':'moving'} for actor in moving
                    if not (scope=='primary' and actor['position']==position)]
        # 飞爻所化不等于伏神自身所化；变爻也没有第二次变化。
        if scope=='primary' and line['moving']:
            sources.append({**describe(line['transformation'],'changed'),'kind':'own_transformation'})
        sources = [source for source in sources if source['branch']==tomb_branch]
        if sources:
            kinds = {'day':'日墓','month':'月墓','moving':'动墓','own_transformation':'化墓'}
            kind_terms = ' '.join(dict.fromkeys(kinds[source['kind']] for source in sources))
            review(f"tomb_candidate:{scope}:{position}",
                   {'line':describe(line,scope), 'roles':entry['roles'],
                    'tomb_branch':tomb_branch, 'tomb_sources':sources},
                   ['按候选所在层核对日墓、动墓、化墓的适用与效力；月墓及跨层关系须另查象法边界。',
                    '核对旺衰、空破与出墓条件，区分理法作用和象法信息；墓支相符不等于已入墓或不能作用。'],
                   [f"{line['relative']} {line['branch']} {kind_terms} 旺衰 条件",
                    f"{line['relative']} {line['spirit']} 墓库 理法 象法"])

    six_states, six_queries = [], []
    for scope in ('primary','changed') if moving else ('primary',):
        h = chart[scope]
        pairs = [relation(h['lines'][i]['branch'],h['lines'][i+3]['branch']) for i in range(3)] if scope=='changed' else []
        flags = {key:chart['features'][key] if scope=='primary' else all(symbol in pair for pair in pairs)
                 for key,symbol in [('six_clash','冲'),('six_harmony','合')]}
        if any(flags.values()):
            six_states.append({'scope':scope,'hexagram':h['name'],**flags})
            six_queries.extend(f"{label} {'本卦' if scope=='primary' else '变卦'} 用神 适用 应期"
                               for key,label in [('six_clash','六冲'),('six_harmony','六合')] if flags[key])
        if h['palace_stage'] in ('游魂','归魂'):
            stage_name = h['palace_stage']
            review(f'palace_stage:{scope}',
                   {'scope':scope,'hexagram':h['name'],'palace_stage':stage_name},
                   ['核对主卦或实际变卦的适用范围，结合所问对象和用神条件；宫位名称不能单独决定所问结果。'],
                   [f"{stage_name} {'本卦' if scope=='primary' else '变卦'} 用神 适用条件"])
    if six_states:
        review('six_relations', {'hexagrams':six_states},
               ['核对六冲六合在原问、用神及应期中的适用条件；不由聚散直接决定结果，卦宫阶段不是六冲六合判据。'],
               six_queries)
    focus = {key:entry['roles'][:] for key,entry in key_lines.items()}
    for line in moving:
        focus.setdefault(('primary',line['position']), []).append('明动')
        focus.setdefault(('changed',line['position']), []).append('明动爻所化')
    groups = {}
    for index,fact in enumerate(chart['patterns']['facts']):
        if fact.get('scope')=='changed' and not moving:
            continue
        participants = fact['participants']
        matched = [p for p in participants if (p['scope'],p.get('position')) in focus]
        if participants and not matched:
            continue
        group = groups.setdefault(fact['source_rule_id'], {'matched_patterns':{}, 'focus_refs':[]})
        pattern = group['matched_patterns'].setdefault(fact['pattern_id'], {
            'pattern_id':fact['pattern_id'], 'label':fact['label'], 'fact_indexes_zero_based':[]})
        pattern['fact_indexes_zero_based'].append(index)
        for participant in matched:
            item = {**participant,'roles':focus[(participant['scope'],participant['position'])]}
            if item not in group['focus_refs']:
                group['focus_refs'].append(item)
    for reference,group in groups.items():
        group['matched_patterns'] = list(group['matched_patterns'].values())
        review('pattern_source:'+reference, {'source_rule_id':reference, **group},
               ['按fact_indexes_zero_based回看patterns.facts的各组参与爻，核对原问与关键爻，回查引用规则及共享上下文后判断适用性；未入组的模式仍保留在facts，不等于不存在。'],
               list(dict.fromkeys(item['label']+' 适用条件' for item in group['matched_patterns'])))
    return checks
