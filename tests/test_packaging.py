from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import sys
import pytest

from liuyao_mcp import common


def test_prebuilt_tools_without_network_or_model_dependencies(tmp_path):
    # A fresh interpreter checks that even importing the server needs no model runtime.
    code = f'import sys; sys.path.insert(0, {str(Path(common.__file__).resolve().parents[1])!r})\n' + '''
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
for kind in ['rule', 'case']:
    result = search_knowledge('入职 财生官 官生世', kind=kind, limit=3, max_chars=60000,
                              require_valid_chart=kind == 'case')
    assert result['items'] and result['retrieval'] == 'bm25' and not result['models'], result
    assert {'入职', '工作', '财生官', '官生世'} <= set(result['query_terms'])
    assert result['include_unknown'] is False
    assert result['topic_filter_applied'] is False
    if kind == 'case':
        assert all(item['case']['extraction']['chart_validation'] == 'calculated' for item in result['items'])
    source = get_source(result['items'][0]['evidence_id'])
    assert source['text'] and source['source']['sha256'] == result['items'][0]['source_hash']
print('offline tools passed')
'''
    env = {k: v for k, v in os.environ.items() if not k.startswith('LIUYAO_')}
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


def release_smoke():
    path = Path(__file__).resolve().parents[1] / 'scripts/smoke_release.py'
    spec = importlib.util.spec_from_file_location('smoke_release_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_smoke_normalizes_runtime_semver_and_installed_pep440_version():
    smoke = release_smoke()
    installed = {'version': '0.7.0a1', 'runtime_version': '0.7.0-alpha.1'}
    smoke.check_installed_version(installed, 'liuyao_mcp-0.7.0a1-py3-none-any.whl', '0.7.0-alpha.1')
    with pytest.raises(AssertionError):
        smoke.check_installed_version(installed, 'liuyao_mcp-0.7.0a2-py3-none-any.whl')
    parsed = smoke.arguments(['--wheel', 'dist/liuyao_mcp-0.7.0a1-py3-none-any.whl', '--offline'])
    assert parsed.offline and parsed.wheel.name == 'liuyao_mcp-0.7.0a1-py3-none-any.whl'
    parsed = smoke.arguments(['uvx', '--offline', '--python', '3.11', '--from', 'package.whl', 'liuyao-mcp'])
    assert parsed.command == ['uvx', '--offline', '--python', '3.11', '--from', 'package.whl', 'liuyao-mcp']


def test_release_smoke_compares_exact_page_local_columns():
    smoke = release_smoke()
    page = {'pdf_pages': [145], 'text': '首行\n甲作者，反馈乙\n末\n'}
    spans = [{'page': 145, 'start_line': 1, 'end_line': 2, 'start_column': 1, 'end_column': 3},
             {'page': 145, 'start_line': 2, 'end_line': 2, 'start_column': 4, 'end_column': 6}]
    assert smoke.selected_page_text(page, spans) == '行\n甲作者\n反馈'
