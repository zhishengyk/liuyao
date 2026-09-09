"""One loopback process shares BGE models between all local MCP clients."""
import argparse
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time

from .common import digest, dumps, runtime_root as project_root
from .semantic import model_key, model_lock


def text_windows(tokenizer, text, max_tokens, query=None):
    """Cover the entire text with overlapping windows; never silently truncate."""
    pending = [(0,len(text))]
    result = []
    while pending:
        start,end = pending.pop(0)
        piece = text[start:end]
        encoded = tokenizer(query,piece,add_special_tokens=True) if query is not None else tokenizer(piece,add_special_tokens=True)
        if len(encoded["input_ids"]) <= max_tokens:
            result.append((start,end,piece))
            continue
        if end-start<8:
            raise ValueError("查询本身超过模型窗口，请缩短检索条件")
        middle = (start+end)//2
        overlap = min(40,(end-start)//8)
        pending[0:0] = [(start,middle+overlap),(middle-overlap,end)]
    return result


class Models:
    def __init__(self):
        self.metadata = model_lock()
        self.lock = threading.Lock()
        self.models = {}
        self.tokenizers = {}
        self.embedding_cache = OrderedDict()
        self.rerank_cache = OrderedDict()

    def load(self, role):
        if role in self.models:
            return self.models[role],self.tokenizers[role]
        import torch
        from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer
        torch.set_num_threads(min(8,os.cpu_count() or 4))
        path = self.metadata[role]["path"]
        tokenizer = AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        factory = AutoModel if role=="embedding" else AutoModelForSequenceClassification
        model,loading = factory.from_pretrained(path,local_files_only=True,trust_remote_code=False,output_loading_info=True)
        missing = set(loading.get("missing_keys",[]))
        if role=="embedding":
            missing -= {"pooler.dense.weight","pooler.dense.bias"}
        if missing or loading.get("mismatched_keys"):
            raise ValueError(f"模型核心参数未完整加载：{sorted(missing)}")
        if role=="reranker" and model.config.num_labels!=1:
            raise ValueError("预期单一相关性logit的reranker")
        model.eval()
        model.to(device="cpu",dtype=torch.float32)
        if role=="embedding":
            from pathlib import Path
            pooling = Path(path)/"1_Pooling/config.json"
            if pooling.is_file():
                config = json.loads(pooling.read_text(encoding="utf8"))
                if not config.get("pooling_mode_cls_token") or config.get("pooling_mode_mean_tokens"):
                    raise ValueError("BGE embedding pooling配置与CLS实现不一致")
        self.models[role],self.tokenizers[role] = model,tokenizer
        return model,tokenizer

    @staticmethod
    def remember(cache,key,value,limit):
        cache[key] = value
        cache.move_to_end(key)
        while len(cache)>limit:
            cache.popitem(last=False)

    def embed(self,texts,max_tokens=768):
        import torch
        with self.lock:
            model,tokenizer = self.load("embedding")
            vectors,owners,spans = [],[],[]
            for owner,text in enumerate(texts):
                for start,end,piece in text_windows(tokenizer,text,max_tokens):
                    key = digest(piece)
                    vector = self.embedding_cache.get(key)
                    if vector is None:
                        inputs = tokenizer(piece,return_tensors="pt",truncation=False)
                        with torch.inference_mode():
                            vector = torch.nn.functional.normalize(model(**inputs).last_hidden_state[:,0],p=2,dim=1)[0].float().tolist()
                        self.remember(self.embedding_cache,key,vector,2000)
                    vectors.append(vector)
                    owners.append(owner)
                    spans.append([start,end])
            return {"vectors":vectors,"owners":owners,"spans":spans,"model":self.metadata["embedding"]["name"],"revision":self.metadata["embedding"]["revision"],"precision":"float32","pooling":"cls_l2","device":"cpu"}

    def rerank(self,query,texts,max_tokens=1024):
        import torch
        with self.lock:
            model,tokenizer = self.load("reranker")
            scores,counts = [],[]
            for text in texts:
                window_scores = []
                windows = text_windows(tokenizer,text,max_tokens,query)
                for _,_,piece in windows:
                    key = digest(query+"\x00"+piece)
                    score = self.rerank_cache.get(key)
                    if score is None:
                        inputs = tokenizer(query,piece,return_tensors="pt",truncation=False)
                        with torch.inference_mode():
                            score = float(model(**inputs).logits.reshape(-1)[0])
                        self.remember(self.rerank_cache,key,score,8000)
                    window_scores.append(score)
                scores.append(max(window_scores))
                counts.append(len(windows))
            return {"scores":scores,"window_counts":counts,"model":self.metadata["reranker"]["name"],"revision":self.metadata["reranker"]["revision"],"precision":"float32","device":"cpu","is_probability":False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=18766)
    args = parser.parse_args()
    models = Models()
    class Handler(BaseHTTPRequestHandler):
        def respond(self,status,data):
            body = dumps(data).encode("utf8")
            self.send_response(status)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/health":
                self.respond(404,{"error":"unknown endpoint"})
                return
            self.respond(200,{"root":str(project_root()),"pid":os.getpid(),"model_key":model_key(models.metadata),"loaded":list(models.models),"device":"cpu"})

        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))))
                if self.path == "/stop":
                    if body.get("root") != str(project_root()) or body.get("model_key") != model_key(models.metadata):
                        self.respond(409,{"error":"worker ownership mismatch"})
                        return
                    self.respond(200,{"stopping":True,"pid":os.getpid()})
                    threading.Thread(target=self.server.shutdown,daemon=True).start()
                    return
                texts = body.get("texts")
                if not isinstance(texts,list) or not texts or any(not isinstance(t,str) or not t for t in texts):
                    raise ValueError("texts必须是非空文本数组")
                start = time.perf_counter()
                if self.path == "/embed":
                    result = models.embed(texts,int(body.get("max_tokens",768)))
                elif self.path == "/rerank":
                    result = models.rerank(body["query"],texts,int(body.get("max_tokens",1024)))
                else:
                    self.respond(404,{"error":"unknown endpoint"})
                    return
                result["elapsed_ms"] = round((time.perf_counter()-start)*1000,2)
                self.respond(200,result)
            except Exception as exc:
                self.respond(500,{"error":f"{type(exc).__name__}: {exc}"})

    # Bind before loading weights. Concurrent starters cannot allocate duplicate models.
    server = ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    print(dumps({"event":"ready","port":args.port,"pid":os.getpid(),"root":str(project_root())}),flush=True)
    server.serve_forever()
    server.server_close()


if __name__ == "__main__":
    main()
