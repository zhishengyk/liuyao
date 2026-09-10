"""Export the persistent word-by-word review ledger without claiming machine OCR is verified."""
import json
from pathlib import Path

from liuyao_mcp.proofreading import correction_text


def main():
    root=Path(__file__).resolve().parents[1]
    data=json.loads(correction_text(root))
    manifest=list(map(json.loads,(root/'data/sources.jsonl').read_text(encoding='utf8').splitlines()))
    sources=[s for s in manifest if s['source_type']=='ocr_text']
    report={'total_pages':sum(s['pdf_pages'] for s in sources),
            'machine_compared_pages':data.get('machine_compared_pages',0),
            'visually_checked_pages':data.get('visually_checked_pages',0),'books':[]}
    document=['# OCR逐字校对进度','',
              '验收标准：逐页逐字对照用户提供的PDF原图。机器识别仅作为底稿；未核准的候选不替换正式原文。',
              '', '| 书籍 | 总页数 | 已逐字核对 | 下一页 |', '| --- | --- | --- | --- |']
    for source in sources:
        reviewed=sorted(p['pdf_page'] for p in data.get('pages',[]) if p['source_id']==source['source_id'] and p.get('visual_reviewed'))
        pending=[n for n in range(1,source['pdf_pages']+1) if n not in reviewed]
        entry={'source_id':source['source_id'],'total':source['pdf_pages'],'reviewed_pages':reviewed,
               'next_page':pending[0] if pending else None,'remaining':len(pending)}
        report['books'].append(entry)
        document.append(f"| {source['title']} | {entry['total']} | {len(reviewed)} | {entry['next_page'] or '完成'} |")
        if reviewed:
            transcript=['# '+source['title']+'：已核准校订页','',
                        '这是已逐字对照原图的阶段稿，尚未完成的页面不收录。〔……〕为校注，不是原书文字。','']
            for page in reviewed:
                record=json.loads((root/'data/proofread_pages'/source['source_id']/f'{page:04}.json').read_text(encoding='utf8'))
                transcript += [f'## PDF第{page}页','',record['text'],'']
                if record['unclear']:transcript += ['校对疑点：'+json.dumps(record['unclear'],ensure_ascii=False),'']
            folder=root/'docs/proofread';folder.mkdir(exist_ok=True)
            (folder/(source['source_id']+'.md')).write_text('\n'.join(transcript),encoding='utf8')
    document += ['',f"机器对照已覆盖{report['machine_compared_pages']}页；严格逐字核对已完成{report['visually_checked_pages']}/{report['total_pages']}页。二者分别统计。",'',
                 '逐页成果保存在[data/proofread_pages](../data/proofread_pages)，每页记录原PDF哈希、页码、完整校订文字和疑点。机器候选与差异统计保存在[data/ocr_corrections.json](../data/ocr_corrections.json)。', '',
                 '已核准的页可通过`get_source("page:来源ID:PDF页码")`读取；未核准页会明确报尚未完成逐字校对。原始证据仍可照常查询。', '',
                 '续作时从上表“下一页”开始。逐页查看原图，校核整页文字与图表，再保存单页JSON；禁止用机器识别分数直接批量标记visually_checked。','']
    (root/'data/ocr_review_progress.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (root/'docs/OCR逐字校对进度.md').write_text('\n'.join(document),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
