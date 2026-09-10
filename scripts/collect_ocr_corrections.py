"""Collect conservative terminology edits; dates, numbers and verdict changes stay flagged."""
import argparse
from collections import Counter
from difflib import SequenceMatcher
import json
from pathlib import Path
import re

TERMS = set('六爻 卦象 卦主 卦爻 爻位 爻辞 卦辞 本卦 变卦 主变卦 世爻 应爻 动爻 静爻 变爻 用神 元神 忌神 仇神 父母 子孙 妻财 官鬼 兄弟 六亲 六神 青龙 朱雀 勾陈 螣蛇 玄武 白虎 旬空 空亡 月建 日辰 月破 回头生 回头克 进神 退神 伏神 飞神 伏吟 反吟 长生 沐浴 冠带 临官 帝旺 旺相 休囚 墓库 生克 相生 相克 相冲 相合 三合 六合 六冲 地支 天干 乾宫 兑宫 离宫 震宫 巽宫 坎宫 艮宫 坤宫'.split())
SENSITIVE = re.compile(r'[0-9甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥不未无没吉凶]')


def normalized_rows(rows):
    chars,locations=[],[]
    for index,text in rows:
        for column,char in enumerate(text):
            if re.match(r'[\w\u4e00-\u9fff]',char):
                chars.append(char);locations.append((index,column))
    return ''.join(chars),locations


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,default=Path('.local/ocr-review'))
    args=parser.parse_args()
    sources=list(map(json.loads,Path('data/sources.jsonl').read_text(encoding='utf8').splitlines()))
    edits=[];pages=[]
    for source in sources:
        if source['source_type']!='ocr_text':continue
        lines=Path(source['path']).read_text(encoding='utf8').splitlines()
        bounds=[(i,int(m[1])) for i,line in enumerate(lines) if (m:=re.search(r'=+ PDF 第 (\d+) 页 / 共',line))]
        for n,(start,page) in enumerate(bounds):
            end=bounds[n+1][0] if n+1<len(bounds) else len(lines)
            path=args.input/source['source_id']/f'{page:04}.json'
            if not path.is_file():
                pages.append({'source_id':source['source_id'],'pdf_page':page,'status':'pending'})
                continue
            record=json.loads(path.read_text(encoding='utf8'))
            original_rows=[];diagram=False
            for i in range(start+1,end):
                if lines[i].startswith('【卦象结构化'):diagram=True
                if diagram:
                    if not lines[i].strip():diagram=False
                    continue
                if not lines[i].strip() or lines[i].strip().isdigit():continue
                original_rows.append((i,lines[i]))
            old,old_pos=normalized_rows(original_rows)
            new,new_pos=normalized_rows([(i,row['text']) for i,row in enumerate(record['lines'])
                                          if '3051374004' not in row['text'].replace(' ','')])
            proposals=[];flagged=[]
            for tag,a,b,c,d in SequenceMatcher(None,old,new,autojunk=False).get_opcodes():
                if tag=='equal':continue
                before,after=old[a:b],new[c:d]
                if not before and not after:continue
                safe=False
                if tag=='replace' and 0<len(before)<=4 and 0<len(after)<=4 and not SENSITIVE.search(before+after):
                    positions=old_pos[a:b]
                    candidate_rows={new_pos[k][0] for k in range(c,d)}
                    if len({p[0] for p in positions})==1 and all(record['lines'][i]['score']>=.985 for i in candidate_rows):
                        context=new[max(0,c-3):min(len(new),d+3)]
                        if any(term in context and new.find(term,max(0,c-3),min(len(new),d+3)) <= c and
                               d <= new.find(term,max(0,c-3),min(len(new),d+3))+len(term) for term in TERMS):
                            line=positions[0][0];begin=positions[0][1];finish=positions[-1][1]+1
                            if lines[line][begin:finish]==before:
                                proposals.append({'source_id':source['source_id'],'pdf_page':page,'line':line+1,
                                                  'start':begin,'end':finish,'before':before,'after':after,
                                                  'original_sha256':source['sha256'],'pdf_sha256':record['pdf_sha256'],
                                                  'basis':'high_confidence_ocr_and_domain_lexicon','visual_verified':False})
                                safe=True
                if not safe and (len(before)>1 or len(after)>1 or SENSITIVE.search(before+after)):
                    flagged.append({'original':before[:100],'candidate':after[:100]})
            edits.extend(proposals)
            pages.append({'source_id':source['source_id'],'pdf_page':page,'status':'machine_compared',
                          'pdf_sha256':record['pdf_sha256'],'original_sha256':source['sha256'],
                          'similarity':record['similarity'],'terminology_edits':len(proposals),
                          'flagged_differences':len(flagged),'visual_reviewed':False})
            (path.parent/f'{page:04}.flags.json').write_text(json.dumps(flagged,ensure_ascii=False),encoding='utf8')
    output={'schema_version':'1','method':'independent_local_ocr_comparison',
            'boundary':'机器对照及保守术语校订；未把页级机器处理标为人工或逐字视觉校对',
            'pages':pages,'edits':edits,'counts':dict(Counter(p['status'] for p in pages))}
    Path('data/ocr_corrections.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(output['counts'],'edits',len(edits),'flagged',sum(p.get('flagged_differences',0) for p in pages))


if __name__=='__main__':main()
