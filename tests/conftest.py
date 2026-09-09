import pytest


@pytest.fixture(autouse=True)
def fast_baseline_mode(monkeypatch):
    # Fast correctness tests use BM25 or explicit model mocks. Real-model acceptance
    # is semantic activate + compare_retrieval.py, whose artifacts are retained.
    monkeypatch.setenv("LIUYAO_RETRIEVAL_MODE","bm25")
