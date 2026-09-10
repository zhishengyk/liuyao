import json
import math
import threading
from types import SimpleNamespace

import pytest

from liuyao_mcp import semantic
from liuyao_mcp.common import digest, dumps


def test_reranker_precision_changes_worker_identity_but_preserves_embedding_key(monkeypatch):
    import importlib.metadata
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "fixture-version")
    models = {role: {"name": role, "revision": "1", "path": "local-cache"}
              for role in ("embedding", "reranker")}
    monkeypatch.delenv("LIUYAO_RERANK_PRECISION", raising=False)
    original = {role: {"name": role, "revision": "1"} for role in models}
    original["runtime"] = {name: "fixture-version" for name in ("torch", "transformers")}
    worker_key = semantic.model_key(models, roles=None)
    assert worker_key == digest(dumps(original))
    embedding_key = semantic.model_key(models)
    monkeypatch.setenv("LIUYAO_RERANK_PRECISION", "dynamic_int8_per_channel")
    assert semantic.model_key(models) == embedding_key
    assert semantic.model_key(models, roles=None) != worker_key
    assert semantic.model_key(models, roles=None, precision="float32") == worker_key
    monkeypatch.setenv("LIUYAO_RERANK_PRECISION", "int4")
    with pytest.raises(ValueError, match="LIUYAO_RERANK_PRECISION"):
        semantic.model_key(models, roles=None)


def test_int8_runtime_quantizes_linear_and_reports_frozen_precision(monkeypatch):
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    from liuyao_mcp import inference_worker as worker

    threads = []

    class Classifier(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.linear = torch.nn.Linear(4, 1)
            self.config = SimpleNamespace(num_labels=1)

        def forward(self, inputs):
            threads.append(threading.get_ident())
            return SimpleNamespace(logits=self.linear(inputs))

    class Tokenizer:
        def __call__(self, first, second=None, return_tensors=None, **kwargs):
            if return_tensors:
                return {"inputs": torch.tensor([[1., 2., 3., 4.]])}
            return {"input_ids": [1, 2]}

    model = Classifier()
    monkeypatch.setenv("LIUYAO_RERANK_PRECISION", "dynamic_int8_per_channel")
    monkeypatch.setattr(worker, "model_lock", lambda: {"reranker": {"name": "fixture", "revision": "1", "path": "unused"}})
    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", lambda *a, **k: Tokenizer())
    monkeypatch.setattr(transformers.AutoModelForSequenceClassification, "from_pretrained",
                        lambda *a, **k: (model, {"missing_keys": [], "mismatched_keys": []}))
    models = worker.Models()
    try:
        identity = models.identity
        first = models.rerank("用神旬空", ["旺相发动", "旺相发动"])
        monkeypatch.setenv("LIUYAO_RERANK_PRECISION", "float32")
        second = models.rerank("用神旬空", ["衰弱安静"])
        assert isinstance(model.linear, torch.ao.nn.quantized.dynamic.Linear)
        assert first["precision"] == second["precision"] == "dynamic_int8_per_channel"
        assert models.identity == identity and first["quantization_ms"] > 0
        assert all(math.isfinite(s) for s in first["scores"] + second["scores"])
        assert first["scores"][0] == first["scores"][1]
        assert len(threads) == 2 and len(set(threads)) == 1
        assert digest("dynamic_int8_per_channel\0用神旬空\0旺相发动") in models.rerank_cache
    finally:
        models.compute.shutdown(wait=True)


@pytest.mark.parametrize("requested", [None, "hybrid_rerank"])
def test_activate_uses_fast_hybrid_unless_rerank_explicit(tmp_path, monkeypatch, requested):
    from liuyao_mcp import retrieval
    mode = requested or "hybrid"
    calls = []

    def search(query, kind, retrieval_mode):
        calls.append((kind, retrieval_mode))
        return {"kind": kind, "retrieval": retrieval_mode, "returned_count": 1,
                "models": {"embedding": {"name": "fixture"}}, "timings": {},
                "items": [{"ranking": {"dense_cosine": 0.8,
                                          "reranker_score": 1.2 if retrieval_mode == "hybrid_rerank" else None}}]}

    config = tmp_path / "retrieval-config.json"
    config.write_text(json.dumps({"keep": "existing"}))
    (tmp_path / "semantic-index").mkdir()
    monkeypatch.setattr(semantic, "retrieval_data_dir", lambda: tmp_path)
    monkeypatch.setattr(retrieval, "search_knowledge", search)
    monkeypatch.setattr("sys.argv", ["semantic", "activate"] + (["--mode", requested] if requested else []))
    semantic.main()
    saved = json.loads(config.read_text())
    assert saved["mode"] == mode and saved["keep"] == "existing"
    assert ("rerank_candidates" in saved) == (mode == "hybrid_rerank")
    assert calls == [("rule", mode), ("case", mode)]
    activation = json.loads((tmp_path / "semantic-index" / "activation.json").read_text())
    assert all(row["retrieval"] == mode for row in activation)


def test_activate_requires_real_dense_hit_before_writing_config(tmp_path, monkeypatch):
    from liuyao_mcp import retrieval
    config = tmp_path / "retrieval-config.json"
    config.write_text('{"mode":"bm25"}')
    monkeypatch.setattr(semantic, "retrieval_data_dir", lambda: tmp_path)
    monkeypatch.setattr(retrieval, "search_knowledge", lambda *a, **k:
                        {"items": [{"ranking": {"dense_cosine": None, "reranker_score": 1}}]})
    monkeypatch.setattr("sys.argv", ["semantic", "activate"])
    with pytest.raises(ValueError, match="真实混合检索"):
        semantic.main()
    assert json.loads(config.read_text()) == {"mode": "bm25"}
