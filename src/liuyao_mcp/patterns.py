"""Mechanical motifs in the registered books; interpretation stays conditional."""
from itertools import combinations, product

from .chart import BRANCHES, BRANCH_ELEMENT, relation

VERSION = 'book-structure-2'
STAGES = ('长生','沐浴','冠带','临官','帝旺','衰','病','死','墓','绝','胎','养')
START = {'木':'亥','火':'寅','金':'巳','水':'申','土':'申'}
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
    def ref(line, scope='primary'):
        return {'scope':scope,'position':line['position'],'branch':line['branch']}
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
