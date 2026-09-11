"""Synthetic metadata/vector scaling only: these replicas are not an accuracy dataset."""
import argparse
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import statistics
import struct
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

from liuyao_mcp import retrieval
from liuyao_mcp.common import tokens
from liuyao_mcp.sqlite_vectors import search_vectors


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def replica(source,output,size,vector_snapshot=None):
    """Replicate only indexed metadata; full source/case payloads retain original IDs."""
    with closing(sqlite3.connect(output)) as db, closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as original:
        original.backup(db)
        base=db.execute('SELECT count(*) FROM evidence_metadata').fetchone()[0]
        extra=max(0,size-base)
        db.execute('CREATE TEMP TABLE replicas(new_id TEXT PRIMARY KEY,old_id TEXT NOT NULL)')
        ids=[r[0] for r in db.execute('SELECT evidence_id FROM evidence_metadata WHERE searchable=1 ORDER BY rowid')]
        db.executemany('INSERT INTO replicas VALUES(?,?)',
                       ((f'zzsynthetic_{i:06d}:{ids[i%len(ids)]}',ids[i%len(ids)]) for i in range(extra)))
        for table in ('evidence_metadata','evidence_topics','evidence_classification','case_features','case_spans','evidence_outline'):
            columns=[r[1] for r in db.execute(f'PRAGMA table_info({table})')]
            selected=','.join('r.new_id' if name=='evidence_id' else 'e.'+name for name in columns)
            db.execute(f'INSERT INTO {table} SELECT {selected} FROM {table} e JOIN replicas r ON r.old_id=e.evidence_id')
        db.execute('INSERT INTO search_index SELECT r.new_id,e.kind,e.focus,e.body FROM search_index e JOIN replicas r ON r.old_id=e.evidence_id')
        db.execute("INSERT INTO build_info VALUES('synthetic_performance_only','metadata replicas; no semantic accuracy claim')")
        if vector_snapshot:
            db.execute('ATTACH DATABASE ? AS vectors',(str(vector_snapshot),))
            db.executescript('''CREATE TABLE semantic_vectors(evidence_id TEXT,kind TEXT,start INT,end INT,embedding BLOB);
                CREATE INDEX semantic_by_kind_id ON semantic_vectors(kind,evidence_id);
                CREATE TABLE semantic_metadata(payload TEXT);''')
            db.execute('INSERT INTO semantic_metadata SELECT payload FROM vectors.semantic_metadata')
            # Fixed real BGE vectors measure cosine-scan cost. They are not new semantic evidence.
            db.execute('INSERT INTO semantic_vectors SELECT v.* FROM vectors.semantic_vectors v JOIN evidence_metadata e ON e.evidence_id=v.evidence_id')
            db.execute('INSERT INTO semantic_vectors SELECT r.new_id,v.kind,v.start,v.end,v.embedding FROM semantic_vectors v JOIN replicas r ON r.old_id=v.evidence_id')
        db.commit()


def percentile(values,percent):
    return sorted(values)[max(0,math.ceil(len(values)*percent)-1)]


def worker(database,repeats):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(key,ctypes.c_size_t) for key in (
                'PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
                'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
        def rss():
            counters=Counters();counters.cb=ctypes.sizeof(counters)
            ctypes.windll.psapi.GetProcessMemoryInfo(wintypes.HANDLE(-1),ctypes.byref(counters),counters.cb)
            return counters.WorkingSetSize
    else:
        def rss():
            return int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
    tokens('工作求职旬空')
    baseline=rss()
    peak=[baseline]; stop=threading.Event()
    def sample():
        while not stop.wait(.005):
            peak[0]=max(peak[0],rss())
    thread=threading.Thread(target=sample,daemon=True);thread.start()
    before=sha256(database)
    loads=json.loads;decoded=[]
    def tracked(text):
        value=loads(text)
        if isinstance(value,dict) and ('case_id' in value or ('content_hash' in value and 'text' in value)):
            decoded.append(value.get('case_id',value.get('id')))
        return value
    retrieval.json=SimpleNamespace(loads=tracked)
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as db:
        count=db.execute('SELECT count(*) FROM evidence_metadata').fetchone()[0]
        cases=db.execute("SELECT count(*) FROM evidence_metadata WHERE kind='case'").fetchone()[0]
        searchable=db.execute('SELECT count(*) FROM evidence_metadata WHERE searchable=1').fetchone()[0]
        searchable_cases=db.execute("SELECT count(*) FROM evidence_metadata WHERE searchable=1 AND kind='case'").fetchone()[0]
        has_vectors=db.execute("SELECT 1 FROM sqlite_master WHERE name='semantic_vectors'").fetchone()
        vector_row=db.execute('SELECT embedding FROM semantic_vectors LIMIT 1').fetchone() if has_vectors else None
        vector_count=db.execute('SELECT count(*) FROM semantic_vectors').fetchone()[0] if has_vectors else 0
    queries=[('case_bm25',dict(query='工作求职能否成功',kind='case')),
             ('case_structural',dict(query='zz_no_lexical_match',kind='case',features={'moving_positions':[]})),
             ('rule_bm25',dict(query='旬空 用神',kind='rule'))]
    rows=[]
    for name,request in queries:
        elapsed=[];sizes=[];pools=[]
        for iteration in range(repeats+1):
            decoded.clear(); start=time.perf_counter()
            result=retrieval.search_knowledge(**request,db_path=database,retrieval_mode='bm25',limit=3,max_chars=150000)
            ms=(time.perf_counter()-start)*1000
            assert not any(eid.startswith('zzsynthetic_') for eid in decoded), 'Replica unexpectedly reached payload decoding'
            if iteration:
                elapsed.append(ms);sizes.append(len(decoded));pools.append(result['candidate_pool_size'])
        rows.append({'operation':name,'p50_ms':round(statistics.median(elapsed),2),
                     'p95_ms':round(percentile(elapsed,.95),2),'max_decoded_payloads':max(sizes),
                     'max_candidate_pool':max(pools),'samples_ms':[round(t,2) for t in elapsed]})
    if vector_row:
        vector=list(struct.unpack('<'+'f'*(len(vector_row[0])//4),vector_row[0]))
        for kind in ('case','rule'):
            scope=("SELECT evidence_id FROM evidence_metadata WHERE kind=:kind AND searchable=1",{'kind':kind})
            elapsed=[]
            for iteration in range(repeats+1):
                start=time.perf_counter()
                result,more=search_vectors(database,[vector],kind,scope,60)
                ms=(time.perf_counter()-start)*1000
                if iteration:elapsed.append(ms)
            rows.append({'operation':kind+'_exact_dense_scan','p50_ms':round(statistics.median(elapsed),2),
                         'p95_ms':round(percentile(elapsed,.95),2),'returned_candidates':len(result),
                         'samples_ms':[round(t,2) for t in elapsed]})
    stop.set();thread.join();peak[0]=max(peak[0],rss())
    after=sha256(database)
    assert before==after
    return {'database':str(database),'metadata_documents':count,'case_metadata_documents':cases,
            'searchable_documents':searchable,'searchable_case_documents':searchable_cases,
            'vector_windows':vector_count,'full_payloads':'original corpus only; replica metadata shares duplicate groups',
            'baseline_rss_mib':round(baseline/2**20,2),'peak_rss_mib':round(peak[0]/2**20,2),
            'rss_growth_mib':round((peak[0]-baseline)/2**20,2),'database_unchanged':True,
            'database_sha256':before,'operations':rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--sizes',type=int,nargs='+',default=[10000,50000])
    parser.add_argument('--vector-snapshot',type=Path)
    parser.add_argument('--repeats',type=int,default=7)
    parser.add_argument('--worker',action='store_true')
    args=parser.parse_args();database=args.database.resolve()
    if args.worker:
        print(json.dumps(worker(database,args.repeats),ensure_ascii=False));return
    assert args.output, '--output required'
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    before=sha256(database);runs=[]
    with closing(sqlite3.connect(database)) as db:base=db.execute('SELECT count(*) FROM evidence_metadata').fetchone()[0]
    for size in [base,*args.sizes]:
        target=output/f'synthetic-{size}.sqlite'
        if target.exists():target.unlink()
        replica(database,target,size,args.vector_snapshot.resolve() if args.vector_snapshot else None)
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker','--database',str(target),'--repeats',str(args.repeats)],capture_output=True,text=True,encoding='utf8',check=True)
        runs.append(json.loads(result.stdout));print(json.dumps(runs[-1],ensure_ascii=False),flush=True)
    report={'scope':'Synthetic metadata/vector performance; no semantic accuracy, recall or prediction claim',
            'source_database':str(database),'source_sha256_before':before,'source_sha256_after':sha256(database),
            'source_unchanged':before==sha256(database),'repeats':args.repeats,'runs':runs}
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
