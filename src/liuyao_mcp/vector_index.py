"""Versioned multi-window vectors and exact dense retrieval for the small corpus."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time

from .common import case_search_text, database_path, digest, dumps, plain, retrieval_data_dir
from .semantic import ensure_worker, model_key, model_lock, request
from .sqlite_vectors import manifest_at, search_vectors, write_index

INDEX_VERSION = "sqlite-cosine-windowed-1"
MAX_EMBED_TOKENS = 768


def document_text(kind,payload):
    return payload["chapter"]+"\n"+plain(payload["text"]) if kind=="rule" else case_search_text(payload)


def build_index(db_path=None):
    import numpy as np
    path = Path(db_path or database_path()).resolve()
    if not path.is_file():
        raise ValueError("请先构建知识库，再构建向量索引")
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        corpus = db.execute("SELECT value FROM build_info WHERE key='corpus_hash'").fetchone()[0]
        docs = [(eid,"rule",json.loads(payload)) for eid,payload in db.execute("SELECT id,payload FROM chunks ORDER BY id")]
        docs += [(eid,"case",json.loads(payload)) for eid,payload in db.execute("SELECT id,payload FROM cases ORDER BY id")]
    docs = [(eid,kind,document_text(kind,payload)) for eid,kind,payload in docs]
    excluded_empty = [eid for eid,_,text in docs if not text.strip()]
    docs = [(eid,kind,text) for eid,kind,text in docs if text.strip()]
    if not docs:
        raise ValueError("知识库没有可用于向量检索的非空文本")
    models = model_lock()
    key = model_key(models)
    spec_key = digest(key+INDEX_VERSION+str(MAX_EMBED_TOKENS))
    folder = retrieval_data_dir(db_path)/"semantic-index"
    # A single composite hash avoids exceeding Windows MAX_PATH in deep checkouts.
    cache = folder/"cache"
    cache.mkdir(parents=True,exist_ok=True)
    generation = digest(corpus+spec_key)
    output = folder/generation
    output.mkdir(exist_ok=True)
    ensure_worker()
    entries,matrices = [],[]
    cached,new = 0,0
    started = time.perf_counter()
    for index,(eid,kind,text) in enumerate(docs,1):
        text_hash = digest(text)
        cached_file = cache/(digest(spec_key+text_hash)+".npz")
        if cached_file.is_file():
            with np.load(cached_file,allow_pickle=False) as stored:
                vectors,spans = stored["vectors"],stored["spans"]
            cached += 1
        else:
            result = request("embed",{"texts":[text],"max_tokens":MAX_EMBED_TOKENS})
            vectors = np.asarray(result["vectors"],dtype=np.float32)
            spans = np.asarray(result["spans"],dtype=np.int32)
            new += 1
        if vectors.ndim!=2 or vectors.shape[1]!=1024 or len(vectors)!=len(spans) or not np.isfinite(vectors).all() or not np.allclose(np.linalg.norm(vectors,axis=1),1,atol=1e-5):
            raise ValueError(f"BGE embedding维度或数值异常：{cached_file}")
        if not cached_file.is_file():
            temporary = cached_file.with_suffix('.next.npz')
            np.savez(temporary,vectors=vectors,spans=spans)
            temporary.replace(cached_file)
        matrices.append(vectors)
        entries.extend({"evidence_id":eid,"kind":kind,"text_hash":text_hash,"span":[int(start),int(end)]} for start,end in spans)
        if index%25==0 or index==len(docs):
            progress = {"done":index,"total":len(docs),"cached":cached,"encoded":new,"elapsed_seconds":round(time.perf_counter()-started,1)}
            (folder/"build-progress.json").write_text(dumps(progress),encoding="utf8")
            print(dumps(progress),flush=True)
    matrix = np.concatenate(matrices,axis=0)
    manifest = {"index_version":INDEX_VERSION,"corpus_hash":corpus,"model_key":key,"models":{role:{k:v for k,v in item.items() if k!='path'} for role,item in models.items()},"generation":generation,"source_documents":len(docs)+len(excluded_empty),"excluded_empty_evidence_ids":excluded_empty,"documents":len(docs),"vectors":len(entries),"dimensions":int(matrix.shape[1]),"dtype":"float32","pooling":"cls_l2","max_tokens":MAX_EMBED_TOKENS,"whole_text_covered_by_windows":True,"cached_documents":cached,"encoded_documents":new,"elapsed_seconds":round(time.perf_counter()-started,2)}
    write_index(output/"knowledge.sqlite", manifest, entries, matrix, source=path)
    (output/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf8")
    temporary = folder/"active.next.json"
    temporary.write_text(dumps({"generation":generation}),encoding="utf8")
    temporary.replace(folder/"active.json")
    return manifest


def dense_search(query,kind,allowed_ids,limit,corpus_hash,db_path=None):
    path = Path(db_path or database_path()).resolve()
    manifest = manifest_at(path)
    if manifest is None:
        folder = retrieval_data_dir(db_path)/"semantic-index"
        active = folder/"active.json"
        if not active.is_file():
            raise ValueError("向量索引尚未构建，请运行 python -m liuyao_mcp.vector_index")
        generation = json.loads(active.read_text(encoding="utf8"))["generation"]
        path = folder/generation/"knowledge.sqlite"
        if not path.is_file():
            raise ValueError("缺少SQLite向量索引，请重新构建向量索引")
        manifest = manifest_at(path)
    if manifest is None:
        raise ValueError("数据库缺少向量索引元数据")
    generation = manifest['generation']
    if manifest["corpus_hash"] != corpus_hash or manifest["model_key"] != model_key():
        raise ValueError("向量索引与当前语料或模型版本不一致，请重新构建向量索引")
    ensure_worker()
    start = time.perf_counter()
    encoded = request("embed",{"texts":[query],"max_tokens":MAX_EMBED_TOKENS})
    query_vectors = encoded["vectors"]
    ranked, has_more = search_vectors(path, query_vectors, kind, allowed_ids, limit)
    return ranked,{"model":manifest["models"]["embedding"],"index_generation":generation,"query_windows":len(query_vectors),"elapsed_ms":round((time.perf_counter()-start)*1000,2),"has_more":has_more,"storage":"sqlite-vec"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database",type=Path)
    args = parser.parse_args()
    print(dumps(build_index(args.database)))


if __name__ == "__main__":
    main()
