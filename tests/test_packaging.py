from pathlib import Path
import os
import shutil
import subprocess
import sys

from liuyao_mcp import common


def test_prebuilt_tools_without_network_or_model_dependencies(tmp_path):
    # A fresh interpreter checks that even importing the server needs no model runtime.
    code = '''
import importlib.abc
import socket
import sys

class NoModels(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'transformers', 'huggingface_hub', 'numpy'}:
            raise ImportError('Model dependency unavailable in offline release: ' + fullname)

def no_network(*args, **kwargs):
    raise AssertionError('Offline tools attempted a network connection')

sys.meta_path.insert(0, NoModels())
socket.socket.connect = no_network
socket.socket.connect_ex = no_network
socket.getaddrinfo = no_network

from liuyao_mcp.server import build_chart, search_knowledge, get_source

assert build_chart([2] * 6, month_branch='卯', day_ganzhi='庚子')
for kind, count in [('rule', 12), ('case', 8)]:
    result = search_knowledge('工作 官鬼 求职', kind=kind, max_chars=150000)
    assert result['returned_count'] == count, result
    source = get_source(result['items'][0]['evidence_id'])
    assert source['text']
print('offline tools passed')
'''
    env = {k: v for k, v in os.environ.items() if k != 'LIUYAO_RETRIEVAL_MODE'}
    database = tmp_path / 'knowledge.sqlite'
    shutil.copyfile(common.database_path(), database)
    env.update(LIUYAO_ROOT=str(tmp_path), LIUYAO_DB=str(database))
    result = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-c', code], cwd=tmp_path,
                            env=env, capture_output=True, text=True, encoding='utf8', timeout=60)
    assert result.returncode == 0, result.stderr
    assert 'offline tools passed' in result.stdout


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


def test_source_checkout_prefers_live_database(monkeypatch,tmp_path):
    monkeypatch.delenv("LIUYAO_ROOT",raising=False)
    monkeypatch.delenv("LIUYAO_DB",raising=False)
    package=tmp_path/"src/liuyao_mcp"
    (package/"_data").mkdir(parents=True)
    (package/"_data/knowledge.sqlite").touch()
    (tmp_path/"data").mkdir()
    (tmp_path/"data/sources.jsonl").touch()
    monkeypatch.setattr(common,"__file__",str(package/"common.py"))
    assert common.database_path()==tmp_path/"data/knowledge.sqlite"
    assert common.runtime_root()==tmp_path


def test_packaged_model_state_is_persistent(monkeypatch,tmp_path):
    monkeypatch.delenv("LIUYAO_ROOT",raising=False)
    monkeypatch.delenv("LIUYAO_DB",raising=False)
    monkeypatch.setenv("LOCALAPPDATA",str(tmp_path/"cache"))
    package=tmp_path/"environment/lib/site-packages/liuyao_mcp"
    (package/"_data").mkdir(parents=True)
    (package/"_data/knowledge.sqlite").touch()
    monkeypatch.setattr(common,"__file__",str(package/"common.py"))
    assert common.runtime_root()==tmp_path/"cache/liuyao-mcp"
    assert common.retrieval_data_dir()==tmp_path/"cache/liuyao-mcp/data"
