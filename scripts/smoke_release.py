"""Exercise the manual-corpus contract over real, isolated MCP stdio.

Use --wheel PATH before publication, --plugin for the published plugin launcher,
--offline for cached uvx execution, or pass an explicit server command. This is
release smoke coverage, not a claim that the legacy full test suite passes.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit
import zipfile

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from packaging.utils import parse_wheel_filename
from packaging.version import Version

CONTEXT_RULE = 'liuyao_xiangfa_jinjie_shang.manual.p0186_tiger_parent_accident'
UNCALCULATED_CASE = 'zengshan_buyi.manual.L05990C0000.case'
CORRECTED_CASE = 'liuyao_lifa_jinjie.manual.p0145_child_health'

# This runs in uvx's installed environment, with model imports and network calls
# blocked inside that interpreter; installation itself may need network access.
INSTALLED_PROBE = r"""import hashlib,importlib.abc,json,socket,sys
from importlib.metadata import version
from pathlib import Path
class NoModels(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch','transformers','huggingface_hub','numpy'}:
            raise ImportError('Offline release imported model dependency: '+fullname)
def no_network(*args, **kwargs):
    raise AssertionError('Offline package tools attempted network access')
sys.meta_path.insert(0, NoModels())
socket.socket.connect = no_network
socket.socket.connect_ex = no_network
socket.getaddrinfo = no_network
import liuyao_mcp
from liuyao_mcp.common import database_path
from liuyao_mcp.server import self_check
path = database_path()
assert 'site-packages' in Path(liuyao_mcp.__file__).parts
assert path == (Path(liuyao_mcp.__file__).parent/'_data/knowledge.sqlite').resolve()
check = self_check()
print(json.dumps({'version':version('liuyao-mcp'),'runtime_version':liuyao_mcp.__version__,
                  'module':liuyao_mcp.__file__,'database':str(path),
                  'database_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                  'offline_self_check':check},ensure_ascii=False))
"""


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--wheel', type=Path)
    mode.add_argument('--plugin', action='store_true')
    parser.add_argument('--offline', action='store_true', help='Require cached uvx installation and launch')
    parser.add_argument('command', nargs=argparse.REMAINDER, help='Explicit server command and arguments')
    parsed = parser.parse_args(argv)
    if (parsed.wheel or parsed.plugin) and parsed.command:
        parser.error('choose --wheel, --plugin, or a server command')
    return parsed


def check_installed_version(installed, wheel_name=None, plugin_version=None):
    actual = Version(installed['version'])
    assert actual == Version(installed['runtime_version']), installed
    if wheel_name:
        name, expected, _, _ = parse_wheel_filename(wheel_name)
        assert name == 'liuyao-mcp' and actual == expected, (wheel_name, installed)
    if plugin_version:
        assert actual == Version(plugin_version), (plugin_version, installed)


def selected_page_text(page, spans):
    """Read exact page-local columns to compare page and case APIs."""
    lines = page['text'].split('\n')
    result = []
    for span in spans:
        assert span['page'] == page['pdf_pages'][0]
        selected = lines[span['start_line']-1:span['end_line']]
        start, end = span.get('start_column', 0), span.get('end_column', len(selected[-1]))
        if len(selected) == 1:
            selected[0] = selected[0][start:end]
        else:
            selected[0], selected[-1] = selected[0][start:], selected[-1][:end]
        result.append('\n'.join(selected))
    return '\n'.join(result)


async def main(argv=None):
    options = arguments(argv)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('LIUYAO_') and key not in ('PYTHONPATH', 'PYTHONHOME')}
    env.update(PYTHONIOENCODING='utf-8', UV_PYTHON_DOWNLOADS='never',
               UV_CONCURRENT_INSTALLS='1', UV_LINK_MODE='copy')
    root = Path(__file__).resolve().parents[1]
    wheel, plugin_version = options.wheel.resolve() if options.wheel else None, None
    mode = 'custom_command' if options.command else 'installed_python'
    if wheel:
        command, args = 'uvx', ['--python', sys.executable, '--from', str(wheel), 'liuyao-mcp']
        mode = 'wheel'
    elif options.plugin:
        plugin = root/'plugins/liuyao-assistant'
        server = json.loads((plugin/'.mcp.json').read_text(encoding='utf8'))['mcpServers']['liuyao']
        plugin_version = json.loads((plugin/'.codex-plugin/plugin.json').read_text(encoding='utf8'))['version']
        command, args = server['command'], list(server['args'])
        env.update(server.get('env', {}))
        mode = 'plugin_manifest_launcher'
    else:
        command, *args = options.command or [sys.executable, '-I', '-m', 'liuyao_mcp.server']
    if Path(command).is_file():
        command = str(Path(command).resolve())
    uvx = Path(command).stem.lower() == 'uvx'
    if options.offline:
        if not uvx:
            raise ValueError('--offline requires a uvx launcher; custom Python offline checks belong in test_packaging')
        if '--offline' not in args:
            args.insert(0, '--offline')
    if uvx:
        assert '--from' in args and 'liuyao-mcp' in args, 'uvx requires an explicit package source and liuyao-mcp entry point'
        if 'UV_CACHE_DIR' not in env:
            env['UV_CACHE_DIR'] = subprocess.check_output(['uv', 'cache', 'dir'], env=env, text=True).strip()
        package_source = args[args.index('--from')+1]
        remote = urlsplit(package_source).scheme in ('http', 'https')
        if not remote and wheel is None:
            candidate = Path(package_source)
            if candidate.suffix == '.whl' and candidate.is_file():
                wheel = candidate.resolve()
        wheel_name = Path(unquote(urlsplit(package_source).path)).name if remote else Path(package_source).name
    report = {'scope': 'manual_release_smoke', 'launch_mode': mode, 'checks': [],
              'legacy_full_suite': 'not_covered', 'codex_session_registration': 'not_assessed',
              'offline_uvx_requested': uvx and ('--offline' in args or env.get('UV_OFFLINE', '').lower() in ('1', 'true'))}
    with tempfile.TemporaryDirectory(prefix='liuyao-release-smoke-') as cwd:
        env.update(LOCALAPPDATA=str(Path(cwd)/'cache'), XDG_CACHE_HOME=str(Path(cwd)/'cache'))
        if uvx:
            prefix = args[:args.index('liuyao-mcp')]
            probe = subprocess.run([command, *prefix, 'python', '-I', '-X', 'utf8', '-c', INSTALLED_PROBE],
                                   cwd=cwd, env=env, check=True, capture_output=True, text=True,
                                   encoding='utf8', timeout=240)
            installed = report['installed'] = json.loads(probe.stdout)
            check_installed_version(installed, wheel_name if wheel_name.endswith('.whl') else None, plugin_version)
            if wheel:
                with zipfile.ZipFile(wheel) as bundle:
                    expected = hashlib.sha256(bundle.read('liuyao_mcp/_data/knowledge.sqlite')).hexdigest()
                assert installed['database_sha256'] == expected, installed
            check = installed['offline_self_check']
            assert check['status'] == 'passed'
            if check['coverage_status'] == 'incomplete':
                assert Version(installed['version']).is_prerelease, 'Incomplete corpus must use a prerelease version'
                assert check['release_status'] == 'blocked_incomplete_corpus'
            report.update(coverage_status=check['coverage_status'], corpus_hash=check['corpus_hash'])
            report['checks'] += ['isolated_site_packages_and_bundled_database', 'installed_tools_without_network_or_model_imports']
            if options.plugin:
                report['plugin_version'] = plugin_version
                report['checks'].append('plugin_config_downloaded_package_and_version')
        params = StdioServerParameters(command=command, args=args, env=env, cwd=Path(cwd))
        async with Client(params, read_timeout_seconds=180) as client:
            async def call(name, **kwargs):
                response = await client.call_tool(name, kwargs)
                assert not response.is_error, response
                data = response.structured_content
                return data.get('result', data)

            listed = await client.list_tools()
            tools = {tool.name: tool for tool in listed.tools}
            assert set(tools) == {'build_chart', 'search_knowledge', 'get_source', 'get_outline', 'get_topics'}
            search_schema = tools['search_knowledge'].input_schema['properties']
            assert search_schema['include_unknown']['default'] is False
            assert {'require_valid_chart', 'features', 'topic', 'subtopic', 'outline_ids'} <= set(search_schema)
            assert tools['build_chart'].input_schema['properties']['line_values']['items']['type'] == 'integer'
            topics = await call('get_topics')
            assert {'job', 'wealth', 'lost'} <= {item['id'] for item in topics['items']}
            chart = await call('build_chart', line_values=[2]*6, month_branch='卯', day_ganzhi='庚子')
            assert chart['primary']['name'] == '坤' and '| 上爻 |' in chart['display']['markdown']
            report['checks'].append('five_mcp_tool_schemas_topics_and_chart')

            hidden = await call('build_chart', line_values=[2,2,1,1,1,1], month_branch='辰',
                                day_ganzhi='甲子', yongshen_positions=[1], yongshen_scope='hidden')
            assert hidden['patterns']['yongshen_refs'][0]['scope'] == 'hidden'
            assert hidden['lines'][0]['hidden']['moving'] is None
            changed = await call('build_chart', line_values=[3,1,1,1,1,1], month_branch='辰',
                                 day_ganzhi='甲子', yongshen_positions=[1], yongshen_scope='changed')
            assert changed['patterns']['yongshen_refs'][0]['scope'] == 'changed'
            found = await call('search_knowledge', query='', kind='case', limit=2, max_chars=150000,
                               features={'yongshen_relative':'父母','yongshen_scope':'hidden'})
            assert found['items']
            for item in found['items']:
                features = item['case']['features']
                assert '父母' in features['yongshen_reported']
                assert any(candidate['relative']=='父母' and candidate['scope']=='hidden'
                           for candidate in features['yongshen_candidates'])
                assert item['case']['extraction']['chart_validation'] == 'calculated'
            report['checks'].append('hidden_changed_selection_and_author_yongshen_retrieval')

            for query, expected in [('入职 财生官 官生世', {'入职', '工作', '财生官', '官生世'}),
                                    ('父母没有发动', {'父母', '未发动'}),
                                    ('戊 未 土 生 克', {'戊', '未', '土', '生', '克'})]:
                found = await call('search_knowledge', query=query, limit=2, max_chars=30000)
                assert expected <= set(found['query_terms']), found['query_terms']
                assert found['retrieval'] == 'bm25' and not found['models']
                assert not found['topic_filter_applied']
                if '没有' in query:
                    assert found['query_negations'] and '发动' not in found['query_terms']
                if 'corpus_hash' in report:
                    assert found['corpus_hash'] == report['corpus_hash'], 'Corpus changed between installation probe and MCP'
                report['corpus_hash'] = found['corpus_hash']
            report['checks'].append('domain_tokens_negation_and_topic_hints')

            for query, topic in [('股票 妻财 官鬼 发动', 'wealth'), ('失物 饰品 父母', 'lost')]:
                found = await call('search_knowledge', query=query, kind='case', topic=topic,
                                   include_common=False, limit=3, max_chars=150000)
                assert found['items'] and found['topic_filter_applied'] and found['include_unknown'] is False
                assert all(topic in item['classification']['roots'] for item in found['items'])
            valid = await call('search_knowledge', query='孩子 腹痛', kind='case', limit=3, max_chars=150000, require_valid_chart=True)
            assert valid['items'] and all(item['case']['extraction']['chart_validation']=='calculated' for item in valid['items'])
            assert CORRECTED_CASE in {item['evidence_id'] for item in valid['items']}
            missing = await call('get_source', evidence_id=UNCALCULATED_CASE, max_chars=150000)
            case = missing['structured_case']
            assert case['cast']['day_ganzhi'] == '丙申' and case['cast']['month_branch'] is None
            assert case['extraction']['chart_validation'] == 'not_run' and 'derived' not in case
            assert case['computed_chart_omitted']['reason'] == 'chart_not_validated'
            assert '占文书' in case['question']['raw']
            report['checks'].append('explicit_topic_filter_and_unverified_chart_boundary')

            for method, query in [('lifa', '取用 用神'), ('xiangfa', '六神 取象')]:
                found = await call('search_knowledge', query=query, kind='rule', method=method, limit=2, max_chars=150000)
                assert found['items']
                for item in found['items']:
                    source = await call('get_source', evidence_id=item['evidence_id'], max_chars=500000)
                    assert item['review_status']=='approved' and item['content_role']=='theory'
                    assert source['text']==item['quote'] and source['source']['sha256']==item['source_hash']
                    assert source['source_spans']==item['source_spans']
                    assert all('start_column' in span and 'end_column' in span for span in source['source_spans'])
                    assert source['source']['text_schema']=='canonical-1'
            contextual = await call('get_source', evidence_id=CONTEXT_RULE, max_chars=150000)
            assert contextual['required_contexts'] and not contextual.get('required_contexts_omitted')
            context = contextual['required_contexts'][0]
            assert '具体所测的事情' in context['text'] and context['source_spans'] and context['canonical_spans']
            node = contextual['outline']['node_id']
            selected = await call('search_knowledge', query='', kind='rule', outline_ids=[node], limit=2, max_chars=150000)
            assert selected['items'][0]['evidence_id']==CONTEXT_RULE and selected['items'][0]['required_contexts']
            report['checks'].append('approved_manual_rules_exact_columns_and_required_contexts')

            references = chart['patterns']['resolved_references']
            alias = next(key for key, result in references.items() if result['status']=='available')
            reference = await call('get_source', evidence_id=alias)
            assert reference['kind']=='rule_reference' and reference['status']=='available' and reference['targets']
            for target in reference['targets']:
                source = await call('get_source', evidence_id=target, max_chars=150000)
                assert source['text'] and source['review']['status']=='approved'
            report['checks'].append('mechanical_aliases_resolve_approved_manual_targets')

            page = await call('get_source', evidence_id='page:liuyao_lifa_jinjie:145', max_chars=150000)
            fixed = await call('get_source', evidence_id=CORRECTED_CASE, max_chars=150000)
            case = fixed['structured_case']
            assert page['text_version']=='visually_reviewed_page' and page['review_status']=='visually_checked'
            assert hashlib.sha256(page['text'].encode('utf8')).hexdigest()==page['text_sha256']
            assert case['cast']['line_values']==[2,2,0,1,2,2]
            assert (case['derived']['primary']['name'], case['derived']['changed']['name'])==('豫','小过')
            assert case['extraction']['chart_validation']=='calculated' and case['extraction']['source_chart_independently_verified']
            assert '雷地豫' in fixed['text'] and '雷山小过' in fixed['text']
            assert selected_page_text(page, case['parts']['chart']['canonical_spans'])==case['parts']['chart']['exact_text']
            rejected = await client.call_tool('get_source', {'evidence_id':CORRECTED_CASE,'text_version':'original'})
            assert rejected.is_error, 'PDF canonical spans must not masquerade as an old OCR line mapping'
            report['checks'].append('page145_canonical_yu_to_xiaoguo_and_no_old_ocr_mapping')

            books = await call('get_outline')
            assert books['items']
            children = await call('get_outline', source_id=contextual['source']['source_id'], limit=100)
            assert children['items'] and all(item['title_basis']=='manual_unit_label' for item in children['items'])
            report['checks'].append('actual_manual_outline_without_legacy_node_counts')
    report['status'] = 'passed'
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    asyncio.run(main())
