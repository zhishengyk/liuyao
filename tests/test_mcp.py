import asyncio
import os
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters


def test_real_stdio_protocol():
    async def run():
        params = StdioServerParameters(command=sys.executable,args=["-m","liuyao_mcp.server"],env={**os.environ,"PYTHONIOENCODING":"utf-8"})
        async with Client(params) as client:
            listed = await client.list_tools()
            assert {t.name for t in listed.tools} == {"build_chart","search_knowledge","get_source","get_outline","get_topics"}
            assert all(t.annotations.read_only_hint for t in listed.tools)
            search_schema = next(t.input_schema for t in listed.tools if t.name == 'search_knowledge')
            assert search_schema['properties']['case_text_scope']['enum'] == ['initial', 'full']
            full = await client.call_tool('search_knowledge', {'query': '父母', 'kind': 'case',
                                                             'case_text_scope': 'full', 'limit': 1})
            assert not full.is_error
            full_data = full.structured_content
            full_data = full_data.get('result', full_data)
            assert full_data['case_text_scope'] == 'full' and full_data['returned_count'] == 1
            wrong_scope = await client.call_tool('search_knowledge', {'query': '', 'kind': 'rule',
                                                                    'case_text_scope': 'full'})
            assert wrong_scope.is_error
            outline = await client.call_tool('get_outline', {})
            assert not outline.is_error
            navigation = outline.structured_content
            navigation = navigation.get('result', navigation)
            assert len(navigation['items']) == 6
            book = next(item for item in navigation['items']
                        if item['source_id'] == 'liuyao_xiangfa_jinjie_shang')
            children = await client.call_tool('get_outline', {'parent_id': book['node_id'], 'limit': 2})
            assert not children.is_error
            child_data = children.structured_content
            child_data = child_data.get('result', child_data)
            assert len(child_data['items']) == 2
            assert all(item['parent_id'] == book['node_id'] for item in child_data['items'])
            scoped = await client.call_tool('search_knowledge', {'query': '', 'method': 'xiangfa', 'limit': 2,
                                                                'outline_ids': [book['node_id']]})
            assert not scoped.is_error
            scoped_data = scoped.structured_content
            assert scoped_data.get('result', scoped_data)['returned_count'] == 2
            assert all(item['source_id'] == book['source_id']
                       for item in scoped_data.get('result', scoped_data)['items'])
            chart = await client.call_tool("build_chart",{"line_values":[2]*6,"month_branch":"卯","day_ganzhi":"庚子"})
            assert not chart.is_error
            hidden = await client.call_tool('build_chart',{'line_values':[2,2,1,1,1,1],
                'month_branch':'辰','day_ganzhi':'甲子','yongshen_positions':[1],'yongshen_scope':'hidden'})
            assert not hidden.is_error
            selected=hidden.structured_content
            selected=selected.get('result',selected)
            assert selected['patterns']['yongshen_refs']==[{'scope':'hidden','position':1,'branch':'子'}]
            found = await client.call_tool("search_knowledge",{"query":"旬空 用神","kind":"rule"})
            assert not found.is_error
            data = found.structured_content
            if "result" in data:
                data = data["result"]
            assert data["returned_count"] == 12
            source = await client.call_tool("get_source",{"evidence_id":data["items"][0]["evidence_id"]})
            assert not source.is_error
            bad = await client.call_tool("build_chart",{"line_values":[1],"month_branch":"卯","day_ganzhi":"庚子"})
            assert bad.is_error
            counts = await client.call_tool('build_chart',{'line_values':[0,1,1,2,1,1],'month_branch':'申','day_ganzhi':'壬午'})
            assert not counts.is_error
            normalized=counts.structured_content
            normalized=normalized.get('result',normalized)
            assert normalized['line_values']==[0,1,1,2,1,1]
            boolean = await client.call_tool('build_chart',{'line_values':[True]*6,'month_branch':'申','day_ganzhi':'壬午'})
            assert boolean.is_error
            old = await client.call_tool('build_chart',{'line_values':[8]*6,'month_branch':'卯','day_ganzhi':'庚子'})
            assert old.is_error
    asyncio.run(run())
