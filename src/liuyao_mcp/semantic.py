"""Local model preparation and shared inference client; no silent BM25 fallback."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener

from .common import digest, dumps, project_root

MODEL_IDS = {"embedding":"BAAI/bge-m3", "reranker":"BAAI/bge-reranker-v2-m3"}
WORKER_PORT = int(os.environ.get("LIUYAO_INFERENCE_PORT", "18766"))
LOCAL_HTTP = build_opener(ProxyHandler({}))


def prepare_models(root=None):
    from huggingface_hub import HfApi, snapshot_download
    root = Path(root or project_root())
    folder = root/".local"
    folder.mkdir(parents=True,exist_ok=True)
    lock_path = folder/"models.json"
    old = json.loads(lock_path.read_text(encoding="utf8")) if lock_path.exists() else {}
    models = {}
    for role, name in MODEL_IDS.items():
        revision = old.get(role,{}).get("revision")
        info = HfApi(token=False).model_info(name,revision=revision)
        files = {s.rfilename for s in info.siblings}
        weights = ["*.safetensors","*.safetensors.index.json"] if any(f.endswith(".safetensors") and "/" not in f for f in files) else ["pytorch_model*.bin","pytorch_model.bin.index.json"]
        print(f"Preparing {name}@{info.sha}",flush=True)
        path = snapshot_download(name,revision=info.sha,allow_patterns=weights+["config.json","tokenizer.json","tokenizer_config.json","special_tokens_map.json","sentencepiece.bpe.model","1_Pooling/config.json","modules.json","config_sentence_transformers.json","sentence_bert_config.json"],max_workers=2,token=False)
        models[role] = {"name":name,"revision":info.sha,"path":path}
        lock_path.write_text(json.dumps({**old,**models},ensure_ascii=False,indent=2),encoding="utf8")
    return models


def model_lock():
    path = project_root()/".local/models.json"
    if not path.is_file():
        raise ValueError("语义模型未准备，请运行 python -m liuyao_mcp.semantic prepare")
    models = json.loads(path.read_text(encoding="utf8"))
    if not all(role in models for role in MODEL_IDS):
        raise ValueError("语义模型尚未下载完成")
    return models


def model_key(models=None):
    return digest(dumps({role:{k:v for k,v in value.items() if k!='path'} for role,value in (models or model_lock()).items()}))


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
        if value.get("root") != str(project_root()) or value.get("model_key") != model_key():
            raise ValueError("本地语义服务属于其他项目或模型版本；请停止旧服务或调整 LIUYAO_INFERENCE_PORT")
        return value
    existing = health()
    if existing:
        return existing
    model_lock()
    local = project_root()/".local"
    local.mkdir(exist_ok=True)
    with (local/"inference-worker.log").open("ab") as log:
        subprocess.Popen([sys.executable,"-m","liuyao_mcp.inference_worker","--port",str(WORKER_PORT)],cwd=project_root(),env={**os.environ,"LIUYAO_ROOT":str(project_root()),"PYTHONIOENCODING":"utf-8"},stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    for _ in range(100):
        result = health()
        if result:
            return result
        time.sleep(0.1)
    raise ValueError("语义服务未就绪，请查看 .local/inference-worker.log")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action",choices=["prepare","warm","health"])
    args = parser.parse_args()
    if args.action == "prepare":
        print(dumps(prepare_models()))
    elif args.action == "warm":
        ensure_worker()
        print(dumps(request("embed",{"texts":["六爻用神旬空"],"max_tokens":768})))
        print(dumps(request("rerank",{"query":"用神旬空","texts":["论旬空与用神的关系。","计算机网络协议。"],"max_tokens":1024})))
    else:
        print(dumps(request("health",timeout=2)))


if __name__ == "__main__":
    main()
