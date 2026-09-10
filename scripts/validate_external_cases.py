"""Validate curated external cases and materialize blind inputs plus separate keys."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

from liuyao_mcp.chart import build_chart

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/evaluation'
LIBRARY = Path('C:/Users/duanshengxuan/liuyao') if sys.platform == 'win32' else Path('/mnt/c/Users/duanshengxuan/liuyao')
BRANCHES = '子丑寅卯辰巳午未申酉戌亥'
EXPECTED_BRANCHES = {
 'gua01':'辰午申申戌子', 'gua02':'卯丑亥午申戌', 'gua03':'丑亥酉酉未巳',
 'gua04':'子寅辰酉未巳', 'gua05':'子寅辰丑亥酉', 'gua06':'子寅辰丑亥酉',
 'gua07':'卯丑亥未巳卯', 'gua08':'丑亥酉酉未巳', 'gua09':'丑亥酉亥酉未',
 'shao01':'未巳卯丑亥酉', 'shao02':'子寅辰午申戌', 'shao03':'子寅辰亥酉未',
 'shao04':'丑亥酉未巳卯', 'shao05':'巳卯丑戌子寅', 'shao06':'未巳卯午申戌',
 'shao07':'子寅辰酉未巳', 'shao08':'丑亥酉戌子寅', 'shao09':'卯丑亥午申戌',
 'li01':'寅辰午亥酉未','li02':'子寅辰午申戌','li03':'丑亥酉未巳卯',
 'li04':'丑亥酉午申戌','li05':'卯丑亥戌子寅','li06':'未巳卯午申戌',
 'li07':'未巳卯午申戌','li08':'巳卯丑戌子寅','li12':'辰午申亥酉未',
}

FEEDBACK_ANCHORS = {
 'gua01':'后果然如我所说在当日亥时于裤子表袋中找到钱',
 'gua02':'后果然没调走，在本提升为书记',
 'gua03':'后果于午月调入九江市',
 'gua04':'结果在第二天寅时双双自回家来，并产蛋二枚于家中',
 'gua05':'谁料项链就从被角中无意间掉了出来',
 'gua06':'清江方向刚才来了电话，说孩子在清江，被亲戚看到了',
 'gua07':'果是老板扣发工资，身上钱又被人偷去等原因造成迟归。已于昨晚同家，而昨天正是癸酉日',
 'gua08':'到第二天下午申时果然暴风雨大作',
 'gua09':'算起来也就是丑年巳月差不多的时候了——后来果然如此',
 'shao01':'到二月二十九日（丁酉）对方定可放人。”后来电告知果应',
 'shao02':'摸了58元钱，中奖一辆价值580元的赛车',
 'shao03':'到年底厂长反馈信息说，今年亏本将近30万',
 'shao04':'后来他果未被提，并且到1998年（戊寅），连副职也被免去了',
 'shao05':'后果然其妻五月患病。死里逃生，六月底才开始好',
 'shao06':'里里外外亏了十多万元',
 'shao07':'他承包鱼塘成功了，赚了七八万',
 'shao08':'后果于七月（丙申）初一日（癸未）去了',
 'shao09':'他也受到牵连并停职反省两个月',
}
# Primary outcome, timing, optional details. The scorer must grade separately.
TARGETS = {
 'gua01':('钱可找回','当日亥时','裤子表袋'),
 'gua02':('未调离原单位，但职务提升',None,'提升为书记'),
 'gua03':('调动成功','午月','调入九江市'),
 'gua04':('两只鸭子自行回家','第二天寅时','回家产蛋两枚'),
 'gua05':('项链找回','当晚亥时','在被角；丈夫先前藏起'),
 'gua06':('儿子安全，有消息证实去向','当日酉时','在清江被亲戚看到'),
 'gua07':('儿子安全回家','癸酉日','老板扣工资、钱被偷造成迟归'),
 'gua08':('明日有暴风雨','第二天申时','大风伴雨'),
 'gua09':('能够再婚','丑年巳月',None),
 'shao01':('合伙人获释','二月二十九丁酉日',None),
 'shao02':('占日摸奖中奖获利','当日','花58元中价值580元赛车'),
 'shao03':('工厂年度经营亏损','当年年底确认','近30万元'),
 'shao04':('当年未获提正','1998戊寅年副职也被免','延伸结果单独评，不覆盖当年问题'),
 'shao05':('妻子患重病但后来好转','五月发病，六月底开始好','财损未有明确反馈，不计分'),
 'shao06':('运猪生意严重亏损','酉日发生撞车','车辆故障、撞车人伤、猪死病、亏十多万元'),
 'shao07':('承包鱼塘成功获利','当年','赚七八万元；罚款经堂兄担责而免'),
 'shao08':('哥哥病未愈，后去世','申月初一癸未日',None),
 'shao09':('未接受该次调动后受牵连停职，官职保留','次年停职两个月；1998升迁','只能评价已实施选择的后果，不评价接受调动的反事实'),
 'li01':('获得额外财收入',None,'1000多元；反馈日期存在内部冲突，不评分日期'),
 'li02':('让外甥管理生意后破财',None,None),
 'li03':('房地产投资未成功并损失钱财',None,None),
 'li04':('茶楼后续经营被停止','刚交立冬不久','被责令停业并吊销执照；早期收益不作后续评分'),
 'li05':('投资亏损',None,'投入两万多元全部亏损'),
 'li06':('哥哥后去世','丑月','肝癌病重是既有病情，不作后续命中'),
 'li07':('再次求学获收留，后来学习顺利','清明后','学员矛盾经负责人调解'),
 'li08':('大学录取成功',None,'名牌大学'),
 'li12':('侄儿后去世','辛巳年未月','脑膜炎是既有病情，不作后续命中'),
}

def norm(s):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', s).lower().replace('已','巳').replace('戍','戌')

def signature(month, day, lines):
    return (month, day, tuple(lines or []))

def source_line_excerpt(lines, number, limit=220):
    value = lines[number-1]
    return {'line': number, 'text': value[:limit], 'truncated': len(value)>limit}

def overlap_check(candidate, corpora):
    # Exact narrative reuse, not retrieval relevance: 32 normalized characters.
    # Broader overlaps remain inspectable; theory phrases do not automatically exclude.
    text = norm(candidate)
    hits = []
    for source_id, body in corpora:
        matches = []
        for i in range(0, max(0, len(text)-31), 8):
            snippet = text[i:i+32]
            p = body.find(snippet)
            if p >= 0:
                end = i+32
                while end < len(text) and p+end-i < len(body) and text[end] == body[p+end-i]:
                    end += 1
                matches.append((end-i, text[i:end]))
        if matches:
            length, excerpt = max(matches)
            hits.append({'training_source_id':source_id, 'max_exact_normalized_chars':length, 'excerpt':excerpt[:160], 'matching_shingles':len(matches)})
    return hits

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    candidates=[]
    for p in sorted(OUT.glob('candidates_*.json')):
        candidates += json.loads(p.read_text(encoding='utf-8'))
    dbpath=ROOT/'data/knowledge.sqlite'
    conn=sqlite3.connect(f'file:{dbpath.as_posix()}?mode=ro',uri=True)
    training_sources=conn.execute('SELECT id, metadata, body FROM sources').fetchall()
    corpus=[(id,norm(body)) for id,_,body in training_sources]
    training_paths={json.loads(meta).get('path') for _,meta,_ in training_sources}
    training_hashes={json.loads(meta).get('sha256') for _,meta,_ in training_sources}
    training_cases=[(id,json.loads(payload)) for id,payload in conn.execute('SELECT id,payload FROM cases')]
    signatures={}
    for id,c in training_cases:
        cast=c.get('cast',{})
        sig=signature(cast.get('month_branch'),cast.get('day_ganzhi'),cast.get('line_values'))
        signatures.setdefault(sig,[]).append(id)
    reports=[]; accepted=[]; seen={}
    for c in candidates:
        errors=[]; path=LIBRARY/c['source_path']; raw=path.read_bytes(); lines=raw.decode('utf-8-sig').splitlines()
        filehash=hashlib.sha256(raw).hexdigest()
        assert filehash == c['source_sha256'], f"source file changed: {c['id']}"
        assert c['source_path'] not in training_paths and filehash not in training_hashes, c['id']
        chart=build_chart(c['lines'],month_branch=c['month_branch'],day_ganzhi=c['day_ganzhi'])
        for field,actual in [('main_hexagram',chart['primary']['name']),('changed_hexagram',chart['changed']['name'])]:
            expected=c[field]
            if expected and expected not in (actual,chart['primary']['full_name'] if field=='main_hexagram' else chart['changed']['full_name']):
                errors.append(f'{field}: expected {expected}; engine {actual}')
        mainbranches=''.join(l['branch'] for l in chart['lines'])
        expected=c.get('expected_main_branches') or EXPECTED_BRANCHES.get(c['id'])
        if expected and mainbranches != ''.join(expected):
            errors.append(f'main_branches: {expected} != {mainbranches}')
        sig=signature(c['month_branch'],c['day_ganzhi'],c['lines'])
        duplicates=signatures.get(sig,[])
        internal=seen.get(sig)
        if internal: errors.append(f'duplicate external signature: {internal}')
        seen[sig]=c['id']
        if c.get('strict_validation_eligible') is False: errors.append('curator marked uncertain OCR/chart')
        span='\n'.join(lines[c['source_start_line']-1:c['source_end_line']])
        overlaps=overlap_check(span,corpus)
        report={'id':c['id'],'chart_errors':errors,'training_signature_matches':duplicates,'text_overlaps':overlaps,'chart_summary':{'primary':chart['primary']['full_name'],'changed':chart['changed']['full_name'],'main_branches':mainbranches,'moving':chart['features']['moving_positions']}}
        # Review any exact signature as a possible shared historical case.
        if duplicates: errors.append('training case signature needs manual review')
        reports.append(report)
        if errors: continue
        c=dict(c)
        c['provenance']={'path':c['source_path'],'sha256':filehash,'start_line':c['source_start_line'],'end_line':c['source_end_line'],'span_sha256':hashlib.sha256(span.encode('utf-8')).hexdigest(),'chart_excerpts':[source_line_excerpt(lines,n) for n in c['chart_source_lines']],'feedback_excerpts':[source_line_excerpt(lines,n) for n in c['feedback_lines']]}
        if c['id'] in FEEDBACK_ANCHORS:
            quote=FEEDBACK_ANCHORS[c['id']]
            n=next(n for n in c['feedback_lines'] if quote in lines[n-1])
            c['provenance']['short_feedback_quote']={'line':n,'text':quote,'verbatim':True}
        c['scoring_targets']=dict(zip(('primary_outcome','timing','optional_details'),TARGETS[c['id']]))
        c['verified_chart']=chart
        c['overlap_audit']=report
        accepted.append(c)
    assert len(training_sources) == 6, 'expected the six-source training snapshot'
    assert len(accepted) >= 24, 'external accepted corpus below target; inspect validation records'
    report={'candidate_count':len(candidates),'accepted_count':len(accepted),'training_source_ids':[s[0] for s in training_sources],'training_case_count':len(training_cases),'training_db_sha256':hashlib.sha256(dbpath.read_bytes()).hexdigest(),'source_manifest_sha256':hashlib.sha256((ROOT/'data/sources.jsonl').read_bytes()).hexdigest(),'records':reports}
    (OUT/'validation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Deterministic split fixed by author/document; separate family/event for all records.
    # Entire Li document is sealed to reduce author/style leakage from development.
    split_files={name:[] for name in ('development.blind.jsonl','development.key.jsonl','holdout.blind.jsonl','holdout.key.sealed.jsonl')}
    challenges=[]
    for c in accepted:
        split='holdout' if c['id'].startswith('li') or c['id'] in {'gua07','gua08','shao08','shao09'} else 'development'
        blind={'case_id':'external_'+c['id'],'split':split,'question':c['question'],'month_branch':c['month_branch'],'day_ganzhi':c['day_ganzhi'],'line_values':c['lines'],'line_order':'bottom_to_top','calendar_basis':'supplied_ganzhi','chart':c['verified_chart']}
        key={**c,'case_id':blind['case_id'],'split':split}
        # Key-only fields include outcome, source identity and exact source quotations.
        split_files[f'{split}.blind.jsonl'].append(blind)
        split_files[f'{split}.key'+('.sealed' if split=='holdout' else '')+'.jsonl'].append(key)
        challenges.append({'query_id':blind['case_id']+'_semantic','case_id':blind['case_id'],'split':split,'query':c['semantic_query'],'expected_topic':c['topic'],'expected_structural_needs':c['structural_need'],'query_construction':'manually paraphrased from pre-outcome question and mechanical chart; excludes outcome cues'})
    for name,rows in split_files.items():
        (OUT/name).write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
    (OUT/'semantic_challenges.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in challenges),encoding='utf-8')
    print(json.dumps({'candidates':len(candidates),'accepted':len(accepted),'split_counts':{k:len(v) for k,v in split_files.items()},'needs_review':[r for r in reports if r['chart_errors'] or r['text_overlaps']]},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
