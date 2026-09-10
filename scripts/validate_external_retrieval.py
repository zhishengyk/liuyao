"""Audit natural-question retrieval; topic agreement is not relevance recall."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

from liuyao_mcp.retrieval import search_knowledge
from liuyao_mcp.taxonomy import classify

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def actual_roots(classification):
    roots=classification.get('roots', [])
    if not roots:
        roots=[classification['topic']] if classification.get('topic') else []
    return sorted({root.split('/')[0] for root in roots})


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split',choices=['development','holdout'],default='development')
    parser.add_argument('--database',type=Path,default=ROOT/'data/knowledge.sqlite')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--mode',choices=['bm25','hybrid','hybrid_rerank'],default='bm25')
    args=parser.parse_args()
    output=args.output or ROOT/'.local'/f'evaluation-{args.split}'/args.mode
    output.mkdir(parents=True,exist_ok=True)
    database=args.database.resolve()
    blind_path=ROOT/'data/evaluation'/f'{args.split}.blind.jsonl'
    blind={row['case_id']:row for row in read_jsonl(blind_path)}
    # Do not load either answer key. Filtering is explicit and defaults to development.
    challenges=[row for row in read_jsonl(ROOT/'data/evaluation/semantic_challenges.jsonl') if row['split']==args.split]
    assert set(blind)=={row['case_id'] for row in challenges}
    db_hash_before=sha256(database)
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as connection:
        db_counts={table:connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ['sources','chunks','cases']}
    runs=[]
    with (output/'raw_results.jsonl').open('w',encoding='utf-8') as stream:
        for challenge in challenges:
            chart=blind[challenge['case_id']]['chart']
            expected=challenge['expected_topic']
            expected_root={'annual':'affairs'}.get(expected,expected)
            for kind in ['rule','case']:
                features={name:chart['features'][name] for name in ['shi_relative','ying_relative']} if kind=='case' else {}
                request={'query':challenge['query'],'kind':kind,'method':'all','limit':3,'max_chars':60000,'features':features,'retrieval_mode':args.mode}
                start=time.perf_counter()
                record={'case_id':challenge['case_id'],'query_id':challenge['query_id'],'split':args.split,'expected_topic':expected,'expected_schema_root':expected_root,'expected_structural_needs':challenge['expected_structural_needs'],'query_classification':classify(challenge['query']),'request':request,'input_chart_flags':chart['features']}
                try:
                    result=search_knowledge(**request,db_path=database)
                    records=[]
                    for rank,item in enumerate(result['items'],1):
                        classification=item.get('classification',{})
                        roots=actual_roots(classification)
                        case=item.get('case',{})
                        records.append({'rank':rank,'evidence_id':item['evidence_id'],'actual_topic':classification.get('topic'),'actual_roots':roots,'topic_agreement':expected_root in roots,'classification_status':classification.get('status'),'content_role':item.get('content_role'),'source_type':item['source_type'],'chart_validation':case.get('extraction',{}).get('chart_validation'),'chart_flags':case.get('features'),'structure_match':item.get('structure_match')})
                    record.update({'status':'ok','result':result,'candidate_audit':records})
                except Exception as exc:
                    record.update({'status':'error','error_type':type(exc).__name__,'error':str(exc)})
                record['elapsed_ms']=round((time.perf_counter()-start)*1000,2)
                runs.append(record)
                stream.write(json.dumps(record,ensure_ascii=False)+'\n');stream.flush()
            print(json.dumps({'done':challenge['case_id'],'mode':args.mode,'split':args.split},ensure_ascii=False),flush=True)
    groups={}
    for kind in ['rule','case']:
        group=[record for record in runs if record['request']['kind']==kind]
        successful=[record for record in group if record['status']=='ok']
        nonempty=[record for record in successful if record['candidate_audit']]
        candidates=[item for record in successful for item in record['candidate_audit']]
        groups[kind]={'queries':len(group),'errors':len(group)-len(successful),'empty_results':len(successful)-len(nonempty),'returned_items':len(candidates),'top1_same_topic_queries':sum(record['candidate_audit'][0]['topic_agreement'] for record in nonempty),'top3_any_same_topic_queries':sum(any(item['topic_agreement'] for item in record['candidate_audit']) for record in nonempty),'same_topic_items':sum(item['topic_agreement'] for item in candidates),'chart_validation_counts':dict(Counter(str(item['chart_validation']) for item in candidates)),'actual_topic_counts':dict(Counter(str(item['actual_topic']) for item in candidates)),'budget_skipped_count':sum(len(record['result']['budget_skipped']) for record in successful),'query_terms_empty':sum(not record['result']['query_terms'] for record in successful),'mean_elapsed_ms':round(sum(record['elapsed_ms'] for record in group)/len(group),2)}
    after=sha256(database)
    summary={'created_at_utc':datetime.now(timezone.utc).isoformat(),'split':args.split,'requested_mode':args.mode,'database':str(database),'database_counts':db_counts,'database_sha256_before':db_hash_before,'database_sha256_after':after,'database_unchanged':db_hash_before==after,'blind_input_sha256':sha256(blind_path),'corpus_hashes':sorted({record['result']['corpus_hash'] for record in runs if record['status']=='ok'}),'actual_modes':dict(Counter(record['result']['retrieval'] for record in runs if record['status']=='ok')),'queries':len(challenges),'runs':len(runs),'groups':groups,'metric_definition':'Same-topic means the manually preassigned expected schema root is in automatic returned classification roots. Counts use all queries as denominator, including empty/error queries. General/common rules may be applicable without topic agreement. No full relevance gold set exists: these counts are not recall, precision, or prediction accuracy.','expected_topic_normalization':{'annual':'affairs'},'filtering':'Natural questions sent without topic/author/outcome filters. Only case requests receive mechanically known shi_relative and ying_relative.'}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    assert summary['database_unchanged'], 'database changed during run; rerun audit'
    assert len(summary['corpus_hashes'])<=1, 'multiple corpus revisions returned; rerun audit'


if __name__=='__main__':main()
