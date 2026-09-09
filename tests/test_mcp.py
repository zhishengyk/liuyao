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
            assert {t.name for t in listed.tools} == {"build_chart","search_knowledge","get_source"}
            assert all(t.annotations.read_only_hint for t in listed.tools)
            chart = await client.call_tool("build_chart",{"line_values":[8]*6,"month_branch":"卯","day_ganzhi":"庚子"})
            assert not chart.is_error
            found = await client.call_tool("search_knowledge",{"query":"旬空 用神","kind":"rule"})
            assert not found.is_error
            data = found.structured_content
            if "result" in data:
                data = data["result"]
            assert data["returned_count"] == 12
            source = await client.call_tool("get_source",{"evidence_id":data["items"][0]["evidence_id"]})
            assert not source.is_error
            bad = await client.call_tool("build_chart",{"line_values":[7],"month_branch":"卯","day_ganzhi":"庚子"})
            assert bad.is_error
    asyncio.run(run())
