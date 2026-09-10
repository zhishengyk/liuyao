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
            outline = await client.call_tool('get_outline', {'parent_id': 'xf_shang_c01'})
            assert not outline.is_error
            navigation = outline.structured_content
            navigation = navigation.get('result', navigation)
            assert len(navigation['items']) == 7
            scoped = await client.call_tool('search_knowledge', {'query': '', 'method': 'xiangfa', 'limit': 2,
                                                                'outline_ids': ['xf_shang_c01_s04']})
            assert not scoped.is_error
            scoped_data = scoped.structured_content
            assert scoped_data.get('result', scoped_data)['returned_count'] == 2
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
