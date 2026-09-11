"""Versioned OCR correction overlay; original transcription remains retrievable."""
from collections import defaultdict
import json
from pathlib import Path

from .common import digest

SCHEMA='''CREATE TABLE original_sources(source_id TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE ocr_pages(source_id TEXT NOT NULL,pdf_page INT NOT NULL,payload TEXT NOT NULL,
    PRIMARY KEY(source_id,pdf_page));
CREATE TABLE ocr_edits(source_id TEXT NOT NULL,line INT NOT NULL,payload TEXT NOT NULL);
CREATE INDEX ocr_edit_source ON ocr_edits(source_id,line);'''


def correction_text(root):
    path=Path(root)/'data/ocr_corrections.json'
    data=json.loads(path.read_text(encoding='utf8')) if path.is_file() else {}
    reviews={}
    for reviewed in sorted((Path(root)/'data/proofread_pages').glob('*/*.json')):
        record=json.loads(reviewed.read_text(encoding='utf8'))
        reviews[(record['source_id'],record['pdf_page'])]=record
    for page in data.get('pages',[]):
        record=reviews.get((page['source_id'],page['pdf_page']))
        if record:
            if any(record[key]!=page[key] for key in ('pdf_sha256','original_sha256')):
                raise ValueError('逐页校订与机器底稿来源版本不符')
            page.update(status='visually_checked',visual_reviewed=True,reviewed_text=record['text'],
                        pdf_sha256=record['pdf_sha256'],original_sha256=record['original_sha256'],
                        unclear=record['unclear'],normalization=record['normalization'],
                        review_method=record['method'],review_date=record['review_date'],
                        printed_page=record.get('printed_page'),excluded_regions=record.get('excluded_regions',[]),
                        notes=record.get('notes',[]))
    data['machine_compared_pages']=sum('similarity' in p for p in data.get('pages',[]))
    data['visually_checked_pages']=sum(p.get('visual_reviewed',False) for p in data.get('pages',[]))
    return json.dumps(data,ensure_ascii=False,sort_keys=True)


def apply(source,text,root):
    # Line edits use the original transcription's offsets and hash. Whole-page
    # canonical reviews have separate coordinates and are not inputs here.
    path=Path(root)/'data/ocr_corrections.json'
    data=json.loads(path.read_text(encoding='utf8')) if path.is_file() else {}
    edits=[e for e in data.get('edits',[]) if e['source_id']==source['source_id'] and e.get('visual_verified')]
    if not edits:return source,text
    lines=text.splitlines()
    by_line=defaultdict(list)
    for e in edits:
        if e['original_sha256']!=source['sha256']:raise ValueError('OCR校订版本与原稿不符')
        if '\n' in e['after'] or '\r' in e['after']:raise ValueError('行级修订不得改变目录行号；整页校订请存入proofread_pages')
        by_line[e['line']].append(e)
    for line,changes in by_line.items():
        for e in sorted(changes,key=lambda e:e['start'],reverse=True):
            if lines[line-1][e['start']:e['end']]!=e['before']:raise ValueError('OCR校订锚点失效')
            lines[line-1]=lines[line-1][:e['start']]+e['after']+lines[line-1][e['end']:]
    corrected='\n'.join(lines)+ ('\n' if text.endswith('\n') else '')
    return {**source,'original_sha256':source['sha256'],'sha256':digest(corrected),
            'text_status':'visually_verified_corrections','correction_count':len(edits),
            'proofreading_boundary':'仅已对照原图核准的修订；整书进度以逐页台账为准'},corrected


def store(db,root):
    data=json.loads(correction_text(root))
    for page in data.get('pages',[]):
        db.execute('INSERT INTO ocr_pages VALUES(?,?,?)',(page['source_id'],page['pdf_page'],json.dumps(page,ensure_ascii=False)))
    for edit in data.get('edits',[]):
        if edit.get('visual_verified'):
            db.execute('INSERT INTO ocr_edits VALUES(?,?,?)',(edit['source_id'],edit['line'],json.dumps(edit,ensure_ascii=False)))


def page_reviews(db,source_id,pages):
    result=[]
    for page in pages:
        row=db.execute('SELECT payload FROM ocr_pages WHERE source_id=? AND pdf_page=?',(source_id,page)).fetchone()
        review=json.loads(row[0]) if row else {}
        result.append({'pdf_page':page,'status':review.get('status','not_reviewed'),
                       'evidence_id':f'page:{source_id}:{page}' if review.get('visual_reviewed') else None})
    return result
