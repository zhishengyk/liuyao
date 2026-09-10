"""Local model preparation and shared inference client; no silent BM25 fallback."""
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener, urlopen

from .common import digest, dumps, retrieval_data_dir, runtime_root

MODEL_IDS = {"embedding":"BAAI/bge-m3", "reranker":"BAAI/bge-reranker-v2-m3"}
MODEL_REVISIONS = {"embedding":"5617a9f61b028005a4858fdac845db406aefb181", "reranker":"953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"}
WORKER_PORT = int(os.environ.get("LIUYAO_INFERENCE_PORT", "18766"))
LOCAL_HTTP = build_opener(ProxyHandler({}))


def file_sha256(path):
    hashed = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b""):
            hashed.update(block)
    return hashed.hexdigest()


def download_checked(url,target,size,sha256):
    if target.is_file() and target.stat().st_size==size and file_sha256(target)==sha256:
        return
    partial = target.with_name(target.name+".checked-download")
    target.parent.mkdir(parents=True,exist_ok=True)
    failures = 0
    while not partial.exists() or partial.stat().st_size<size:
        offset = partial.stat().st_size if partial.exists() else 0
        try:
            req = Request(url,headers={"Range":f"bytes={offset}-","Cache-Control":"no-cache"})
            with urlopen(req,timeout=120) as response:
                content_range = response.headers.get("Content-Range","")
                if response.status==206 and not content_range.startswith(f"bytes {offset}-"):
                    raise ValueError("Download returned the wrong byte range")
                if response.status==200 and offset:
                    offset = 0
                received = offset
                with partial.open("ab" if offset else "wb") as stream:
                    while block := response.read(4*1024*1024):
                        stream.write(block)
                        received += len(block)
                        if received//(64*1024*1024) != (received-len(block))//(64*1024*1024):
                            print(dumps({"file":target.name,"downloaded":received,"total":size}),flush=True)
            if received==offset:
                raise OSError("Empty download response")
            failures = 0
        except (OSError,TimeoutError) as exc:
            failures += 1
            if failures>=5:
                raise
            print(dumps({"file":target.name,"retry":failures,"error":type(exc).__name__}),flush=True)
            time.sleep(min(failures,5))
    if partial.stat().st_size!=size or file_sha256(partial)!=sha256:
        raise ValueError(f"Model checksum mismatch: {target.name}; file was not activated")
    partial.replace(target)
    print(dumps({"file":target.name,"sha256_verified":sha256}),flush=True)


def prepare_models(root=None,download_source="modelscope"):
    # Use the official resumable HTTP path; native Xet stalled on this host.
    os.environ.setdefault("HF_HUB_DISABLE_XET","1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING","1")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT","120")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT","60")
    from huggingface_hub import HfApi, snapshot_download
    root = Path(root or runtime_root())
    folder = root/".local"
    folder.mkdir(parents=True,exist_ok=True)
    lock_path = folder/"models.json"
    old = json.loads(lock_path.read_text(encoding="utf8")) if lock_path.exists() else {}
    models = {}
    for role, name in MODEL_IDS.items():
        revision = old.get(role,{}).get("revision",MODEL_REVISIONS[role])
        cached = old.get(role,{})
        cached_path = Path(cached.get("path","."))
        if cached.get("name")==name and cached.get("weight_sha256") and (cached_path/"config.json").is_file() and (cached_path/"tokenizer.json").is_file() and all((cached_path/file).is_file() and file_sha256(cached_path/file)==sha for file,sha in cached["weight_sha256"].items()):
            models[role] = cached
            print(dumps({"model":name,"cached_and_verified":True}),flush=True)
            continue
        info = HfApi(token=False).model_info(name,revision=revision,timeout=60,files_metadata=True)
        files = {s.rfilename for s in info.siblings}
        weights = ["*.safetensors","*.safetensors.index.json"] if any(f.endswith(".safetensors") and "/" not in f for f in files) else ["pytorch_model*.bin","pytorch_model.bin.index.json"]
        print(f"Preparing {name}@{info.sha}",flush=True)
        path = snapshot_download(name,revision=info.sha,allow_patterns=["config.json","tokenizer.json","tokenizer_config.json","special_tokens_map.json","sentencepiece.bpe.model","1_Pooling/config.json","modules.json","config_sentence_transformers.json","sentence_bert_config.json"],max_workers=2,token=False)
        verified = {}
        for entry in info.siblings:
            if "/" in entry.rfilename or not any(fnmatch.fnmatch(entry.rfilename,pattern) for pattern in weights):
                continue
            if not entry.lfs:
                from huggingface_hub import hf_hub_download
                hf_hub_download(name,entry.rfilename,revision=info.sha,token=False)
                continue
            url = f"https://modelscope.cn/models/{name}/resolve/master/{entry.rfilename}" if download_source=="modelscope" else f"https://huggingface.co/{name}/resolve/{info.sha}/{entry.rfilename}?download=true"
            download_checked(url,Path(path)/entry.rfilename,entry.size,entry.lfs.sha256)
            verified[entry.rfilename] = entry.lfs.sha256
        models[role] = {"name":name,"revision":info.sha,"path":path,"weight_sha256":verified}
        lock_path.write_text(json.dumps({**old,**models},ensure_ascii=False,indent=2),encoding="utf8")
    return models


def model_lock(required=("embedding",)):
    path = runtime_root()/".local/models.json"
    if not path.is_file():
        raise ValueError("语义模型未准备，请运行 python -m liuyao_mcp.semantic prepare")
    models = json.loads(path.read_text(encoding="utf8"))
    missing = set(required)-models.keys()
    if missing:
        raise ValueError(f"语义模型尚未下载完成：{', '.join(sorted(missing))}")
    return models


def model_key(models=None, roles=("embedding",)):
    from importlib.metadata import version
    models = models if models is not None else model_lock()
    spec = {role:{k:v for k,v in value.items() if k!='path'} for role,value in models.items() if roles is None or role in roles}
    spec["runtime"] = {name:version(name) for name in ("torch","transformers")}
    return digest(dumps(spec))


def request(operation, payload=None, timeout=600):
    data = dumps(payload).encode("utf8") if payload is not None else None
    req = Request(f"http://127.0.0.1:{WORKER_PORT}/{operation}",data=data,headers={"Content-Type":"application/json"})
    try:
        with LOCAL_HTTP.open(req,timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        body = json.loads(exc.read().decode("utf8"))
        raise ValueError(body.get("error",str(exc))) from exc


def ensure_worker():
    def health():
        try:
            value = request("health",timeout=2)
        except (URLError, TimeoutError, OSError):
            return None
        if value.get("root") != str(runtime_root()) or value.get("model_key") != model_key(roles=None):
            raise ValueError("本地语义服务属于其他项目或模型版本；请停止旧服务或调整 LIUYAO_INFERENCE_PORT")
        return value
    existing = health()
    if existing:
        return existing
    model_lock()
    local = runtime_root()/".local"
    local.mkdir(parents=True,exist_ok=True)
    with (local/"inference-worker.log").open("ab") as log:
        subprocess.Popen([sys.executable,"-m","liuyao_mcp.inference_worker","--port",str(WORKER_PORT)],cwd=runtime_root(),env={**os.environ,"LIUYAO_ROOT":str(runtime_root()),"PYTHONPATH":os.pathsep.join(filter(None,(str(Path(__file__).resolve().parents[1]),os.environ.get("PYTHONPATH")))),"PYTHONIOENCODING":"utf-8"},stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    for _ in range(100):
        result = health()
        if result:
            return result
        time.sleep(0.1)
    raise ValueError("语义服务未就绪，请查看 .local/inference-worker.log")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action",choices=["prepare","warm","health","activate","stop"])
    parser.add_argument("--download-source",choices=["modelscope","huggingface"],default="modelscope")
    args = parser.parse_args()
    if args.action == "prepare":
        print(dumps(prepare_models(download_source=args.download_source)))
    elif args.action == "warm":
        ensure_worker()
        embedded = request("embed",{"texts":["六爻用神旬空"],"max_tokens":768})
        print(dumps({k:v for k,v in embedded.items() if k!='vectors'} | {"dimensions":len(embedded["vectors"][0])}))
        print(dumps(request("rerank",{"query":"用神旬空","texts":["论旬空与用神的关系。","计算机网络协议。"],"max_tokens":1024})))
    elif args.action == "activate":
        from .retrieval import search_knowledge
        results = []
        for kind,query in (("rule","工作 用神 旬空"),("case","求职面试能否录用")):
            result = search_knowledge(query,kind=kind,retrieval_mode="hybrid_rerank")
            if not result["items"] or any(i["ranking"]["reranker_score"] is None for i in result["items"]):
                raise ValueError("真实混合检索及重排未通过，未启用默认模式")
            results.append(result)
        folder = retrieval_data_dir()
        config_path = folder/"retrieval-config.json"
        config = json.loads(config_path.read_text(encoding="utf8")) if config_path.exists() else {}
        config["mode"] = "hybrid_rerank"
        config.setdefault("rerank_candidates",40)
        config_path.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding="utf8")
        (folder/"semantic-index/activation.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf8")
        print(dumps({"default_mode":"hybrid_rerank","checks":[{"kind":r["kind"],"returned_count":r["returned_count"],"models":r["models"],"timings":r["timings"]} for r in results]}))
    elif args.action == "stop":
        health = request("health",timeout=2)
        if health.get("root") != str(runtime_root()):
            raise ValueError("语义服务属于其他项目，未停止")
        print(dumps(request("stop",{"root":str(runtime_root()),"model_key":health["model_key"]},timeout=10)))
    else:
        print(dumps(request("health",timeout=2)))


if __name__ == "__main__":
    main()
