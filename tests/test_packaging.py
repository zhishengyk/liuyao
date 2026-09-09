from pathlib import Path

from liuyao_mcp import common


def test_database_selection(monkeypatch, tmp_path):
    monkeypatch.delenv("LIUYAO_DB", raising=False)
    monkeypatch.delenv("LIUYAO_ROOT", raising=False)
    package = tmp_path / "site-packages/liuyao_mcp"
    bundle = package / "_data/knowledge.sqlite"
    bundle.parent.mkdir(parents=True)
    bundle.touch()
    monkeypatch.setattr(common, "__file__", str(package / "common.py"))
    assert common.database_path() == bundle.resolve()
    monkeypatch.setenv("LIUYAO_ROOT", str(tmp_path / "custom"))
    assert common.database_path() == tmp_path / "custom/data/knowledge.sqlite"
    monkeypatch.setenv("LIUYAO_DB", str(tmp_path / "override.sqlite"))
    assert common.database_path() == tmp_path / "override.sqlite"
