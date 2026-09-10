"""Exercise installed wheel data and MCP from a temporary directory.

Use --wheel dist/liuyao_mcp-VERSION-py3-none-any.whl before publication,
--plugin after publication, or pass an installed Python/server command.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from mcp import Client
from mcp.client.stdio import StdioServerParameters


async def main():
    env = {k: v for k, v in os.environ.items()
           if not k.startswith('LIUYAO_') and k not in ('PYTHONPATH', 'PYTHONHOME')}
    env.update(PYTHONIOENCODING='utf-8', UV_PYTHON_DOWNLOADS='never')
    command = sys.argv[1] if len(sys.argv) > 1 else sys.executable
    args = sys.argv[2:] if len(sys.argv) > 1 else ['-I', '-m', 'liuyao_mcp.server']
    wheel = None
    if sys.argv[1:2] == ['--wheel']:
        wheel = Path(sys.argv[2]).resolve()
        command = 'uvx'
        args = ['--python', sys.executable, '--from', str(wheel), 'liuyao-mcp']
    elif sys.argv[1:] == ['--plugin']:
        config = json.loads((Path(__file__).resolve().parents[1] / 'plugins/liuyao-assistant/.mcp.json').read_text(encoding='utf8'))
        server = config['mcpServers']['liuyao']
        command, args = server['command'], server['args']
        env.update(server.get('env', {}))
    if Path(command).is_file():
        command = str(Path(command).resolve())
    if wheel or sys.argv[1:] == ['--plugin'] or Path(command).stem.lower() == 'uvx':
        env['UV_CACHE_DIR'] = subprocess.check_output(['uv', 'cache', 'dir'], env=env, text=True).strip()
    report = {'checks': []}
    with tempfile.TemporaryDirectory() as cwd:
        # Keep previous per-user retrieval activation out of the release check.
        env.update(LOCALAPPDATA=str(Path(cwd)/'cache'), XDG_CACHE_HOME=str(Path(cwd)/'cache'))
        if wheel:
            # Check the environment uvx will use, not this client's imports.
            probe = """import hashlib,json
from importlib.metadata import version
from pathlib import Path
import liuyao_mcp
from liuyao_mcp.common import database_path
path=database_path()
assert 'site-packages' in Path(liuyao_mcp.__file__).parts
assert path == (Path(liuyao_mcp.__file__).parent / '_data/knowledge.sqlite').resolve(), (path, liuyao_mcp.__file__)
print(json.dumps({'version':version('liuyao-mcp'),'module':liuyao_mcp.__file__,
                  'database':str(path),'database_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
"""
            checked = subprocess.run([command, *args[:-1], 'python', '-I', '-c', probe],
                                     env=env, cwd=cwd, check=True, stdout=subprocess.PIPE,
                                     text=True, encoding='utf8', timeout=180)
            report['installed'] = json.loads(checked.stdout)
            with zipfile.ZipFile(wheel) as bundle:
                expected = hashlib.sha256(bundle.read('liuyao_mcp/_data/knowledge.sqlite')).hexdigest()
            assert report['installed']['database_sha256'] == expected, report
            assert wheel.name == f"liuyao_mcp-{report['installed']['version']}-py3-none-any.whl"
            report['checks'].append('isolated_installed_wheel_and_bundled_database')
        params = StdioServerParameters(command=command, args=args, env=env, cwd=Path(cwd))
        async with Client(params, read_timeout_seconds=180) as client:
            async def call(name, **arguments):
                response = await client.call_tool(name, arguments)
                assert not response.is_error, response
                data = response.structured_content
                return data.get('result', data)

            listed = await client.list_tools()
            assert {t.name for t in listed.tools} == {'build_chart', 'search_knowledge', 'get_source', 'get_outline', 'get_topics'}
            schema = next(t for t in listed.tools if t.name == 'search_knowledge').input_schema
            assert schema['properties']['include_unknown']['default'] is False
            assert 'require_valid_chart' in schema['properties']
            topics = await call('get_topics')
            assert {'job', 'wealth', 'lost'} <= {item['id'] for item in topics['items']}
            chart = await call('build_chart', line_values=[2]*6, month_branch='卯', day_ganzhi='庚子')
            assert chart['primary']['name'] == '坤' and '| 上爻 |' in chart['display']['markdown']
            report['checks'].append('tool_schema_topics_and_chart')
            reviewed = await call('get_source', evidence_id='page:liuyao_lifa_jinjie:102')
            assert reviewed['text_version'] == 'visually_reviewed_page' and reviewed['pdf_pages'] == [102]
            assert reviewed['text'] and 'unclear' in reviewed
            report['checks'].append('visually_reviewed_page_readback')

            for query, expected in [('入职 财生官 官生世', {'入职', '工作', '财生官', '官生世'}),
                                    ('父母没有发动', {'父母', '未发动'})]:
                found = await call('search_knowledge', query=query, limit=2, max_chars=30000)
                assert expected <= set(found['query_terms']), found['query_terms']
                assert found['retrieval'] == 'bm25' and not found['models']
                if '没有' in query:
                    assert found['query_negations'] and '发动' not in found['query_terms']
                report['corpus_hash'] = found['corpus_hash']
            report['checks'].append('domain_words_and_negated_conditions')

            for query, topic in [('股票 妻财 官鬼 发动', 'wealth'), ('失物 饰品 父母', 'lost')]:
                found = await call('search_knowledge', query=query, kind='case', limit=3, max_chars=60000)
                assert found['items'] and found['include_unknown'] is False
                assert all(topic in item['classification']['roots'] for item in found['items'])
            for options in ({'require_valid_chart': True}, {'features': {'shi_relative': '父母'}}):
                found = await call('search_knowledge', query='工作', kind='case', limit=3,
                                   max_chars=60000, **options)
                assert found['items'] and found['require_valid_chart'] is True
                assert all(item['case']['extraction']['chart_validation'] == 'calculated' for item in found['items'])
            report['checks'].append('topic_relevance_and_valid_chart_filter')

            found = await call('search_knowledge', query='面试 录用', kind='rule', limit=5, max_chars=100000)
            assert found['items']
            for item in found['items']:
                assert item['content_role'] in ('theory', 'case_excerpt')
                assert len(item['related_case_ids']) <= 1
                original = await call('get_source', evidence_id=item['evidence_id'], max_chars=500000)
                assert original['text'] == item['quote']
                assert original['source']['sha256'] == item['source_hash']
                assert original['source_spans'] == item['source_spans']
            header = await call('get_source', evidence_id='rule_liuyao_xiangfa_jinjie_xia_5016')
            found = await call('search_knowledge', query=header['text'], kind='rule', method='xiangfa',
                               limit=20, max_chars=150000)
            assert 'rule_liuyao_xiangfa_jinjie_xia_5016' not in {item['evidence_id'] for item in found['items']}
            previous = await call('get_source', evidence_id='case_zengshan_buyi_5950', max_chars=100000)
            following = await call('get_source', evidence_id='case_zengshan_buyi_5990', max_chars=100000)
            assert '占文书' not in previous['text']
            assert following['structured_case']['cast']['day_ganzhi'] == '丙申'
            assert following['structured_case']['cast']['month_branch'] is None
            assert 'derived' not in following['structured_case']
            assert following['structured_case']['computed_chart_omitted']['reason'] == 'chart_not_validated'
            report['checks'].append('case_boundaries_header_exclusion_and_exact_sources')

            for anchor, values in [(5002, [2, 1, 1, 3, 2, 1]), (5853, [1, 1, 1, 2, 2, 1])]:
                evidence_id = f'case_liuyao_lifa_jinjie_{anchor}'
                fixed = await call('get_source', evidence_id=evidence_id, max_chars=100000)
                raw = await call('get_source', evidence_id=evidence_id, text_version='original', max_chars=100000)
                case = fixed['structured_case']
                assert case['cast']['line_values'] == values
                assert case['extraction']['chart_validation'] == 'calculated'
                assert case['derived']['features']
                assert case['outcome']['independently_verified'] is False
                assert fixed['source']['original_sha256'] == raw['source']['sha256'] != fixed['source']['sha256']
                assert fixed['source_spans'] == raw['source_spans'] and fixed['text'] != raw['text']
            page = await call('get_source', evidence_id='page:liuyao_lifa_jinjie:15')
            assert page['text_version'] == 'visually_reviewed_page' and page['pdf_sha256']
            assert hashlib.sha256(page['text'].encode('utf8')).hexdigest() == page['text_sha256']
            report['checks'].append('pdf_verified_chart_repairs_and_original_ocr')

            outline = await call('get_outline', parent_id='xf_shang_c01')
            assert any(item['node_id'] == 'xf_shang_c01_s02' for item in outline['items'])
            scene = await call('search_knowledge', query='材料审核', method='xiangfa',
                               outline_ids=['xf_shang_c01_s02'], limit=2)
            assert scene['items']
            contextual = await call('get_source', evidence_id=scene['items'][0]['evidence_id'], max_chars=10000)
            assert contextual['outline_context']
            report['checks'].append('outline_and_scene_context')
    report['status'] = 'passed'
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
