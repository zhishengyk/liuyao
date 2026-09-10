"""Second local OCR pass with per-page comparison; never labels OCR output proofread."""
import argparse
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import time


def normalized(text):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source_id')
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--output', type=Path, default=Path('.local/ocr-review'))
    parser.add_argument('--threads', type=int, default=2)
    args = parser.parse_args()
    import pymupdf
    from rapidocr_onnxruntime import RapidOCR
    root = Path(__file__).resolve().parents[1]
    source = next(s for s in map(json.loads, (root/'data/sources.jsonl').read_text(encoding='utf8').splitlines())
                  if s['source_id'] == args.source_id)
    text = (root/source['path']).read_text(encoding='utf8')
    parts = re.split(r'=+ PDF 第 (\d+) 页 / 共 \d+ 页 =+\n', text)
    original = {int(parts[i]): parts[i+1] for i in range(1, len(parts), 2)}
    folder = args.output/args.source_id
    folder.mkdir(parents=True, exist_ok=True)
    pdf_hash = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    engine = RapidOCR(intra_op_num_threads=args.threads, inter_op_num_threads=1)
    started = time.monotonic()
    with pymupdf.open(args.pdf) as pdf:
        if len(pdf) != source['pdf_pages']:
            raise ValueError('PDF page count differs from registered OCR source')
        for number, page in enumerate(pdf, 1):
            target = folder/f'{number:04}.json'
            if target.is_file():
                stored = json.loads(target.read_text(encoding='utf8'))
                if stored['pdf_sha256'] == pdf_hash and stored['original_sha256'] == source['sha256']:
                    continue
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
            result, elapsed = engine(pixmap.tobytes('png'))
            rows = [{'box': box, 'text': value, 'score': score} for box, value, score in (result or [])]
            candidate = '\n'.join(r['text'] for r in rows if '3051374004' not in normalized(r['text']))
            prior = original[number]
            prior = re.sub(r'【卦象结构化.*?(?=\n\n|\Z)', '', prior, flags=re.S)
            compared = SequenceMatcher(None, normalized(prior), normalized(candidate), autojunk=False)
            record = {'source_id':args.source_id, 'pdf_page':number, 'pdf_sha256':pdf_hash,
                      'original_sha256':source['sha256'], 'engine':'rapidocr-onnxruntime-1.4.4',
                      'status':'machine_compared', 'visual_reviewed':False, 'width':pixmap.width,
                      'height':pixmap.height, 'similarity':round(compared.ratio(),4),
                      'low_confidence_lines':sum(r['score'] < .9 for r in rows),
                      'candidate_text':candidate, 'lines':rows, 'elapsed':elapsed}
            temporary = target.with_suffix('.tmp')
            temporary.write_text(json.dumps(record,ensure_ascii=False),encoding='utf8')
            temporary.replace(target)
            if number % 20 == 0 or number == len(pdf):
                print(json.dumps({'source':args.source_id,'page':number,'total':len(pdf),
                                  'seconds':round(time.monotonic()-started,1)}),flush=True)


if __name__ == '__main__':
    main()
