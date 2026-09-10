"""Exercise an installed distribution over stdio, outside the source checkout."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

from mcp import Client
from mcp.client.stdio import StdioServerParameters


async def main():
    env = {k: v for k, v in os.environ.items() if k not in ("LIUYAO_ROOT", "LIUYAO_DB", "LIUYAO_RETRIEVAL_MODE", "PYTHONPATH")}
    env["PYTHONIOENCODING"] = "utf-8"
    command = sys.argv[1] if len(sys.argv) > 1 else sys.executable
    if Path(command).is_file():
        command = str(Path(command).resolve())
    args = sys.argv[2:] if len(sys.argv) > 1 else ["-m", "liuyao_mcp.server"]
    if sys.argv[1:] == ['--plugin']:
        config = json.loads((Path(__file__).resolve().parents[1] / 'plugins/liuyao-assistant/.mcp.json').read_text(encoding='utf8'))
        server = config['mcpServers']['liuyao']
        command, args = server['command'], server['args']
        env.update(server.get('env', {}))
    with tempfile.TemporaryDirectory() as cwd:
        params = StdioServerParameters(command=command, args=args, env=env, cwd=Path(cwd))
        async with Client(params, read_timeout_seconds=180) as client:
            listed = await client.list_tools()
            assert {t.name for t in listed.tools} == {"build_chart", "search_knowledge", "get_source", "get_outline"}
            outline = await client.call_tool('get_outline', {'parent_id': 'xf_shang_c01'})
            assert not outline.is_error, outline
            outline_data = outline.structured_content
            assert len(outline_data.get('result', outline_data)['items']) == 7
            scene = await client.call_tool('search_knowledge', {'query': '材料审核', 'method': 'xiangfa',
                                                               'outline_ids': ['xf_shang_c01_s02'], 'limit': 2})
            assert not scene.is_error, scene
            scene_data = scene.structured_content
            scene_data = scene_data.get('result', scene_data)
            assert scene_data['returned_count'] == 2
            contextual = await client.call_tool('get_source', {'evidence_id': scene_data['items'][0]['evidence_id'], 'max_chars': 10000})
            assert not contextual.is_error, contextual
            context_data = contextual.structured_content
            assert context_data.get('result', context_data)['outline_context']
            chart = await client.call_tool("build_chart", {"line_values": [2]*6, "month_branch": "卯", "day_ganzhi": "庚子"})
            assert not chart.is_error, chart
            chart_data = chart.structured_content
            chart_data = chart_data.get('result',chart_data)
            assert '| 上爻 |' in chart_data['display']['markdown']
            for kind, count in (("rule", 12), ("case", 8)):
                result = await client.call_tool("search_knowledge", {"query": "工作 官鬼 用神", "kind": kind, "max_chars": 150000})
                assert not result.is_error, result
                data = result.structured_content
                data = data.get("result", data)
                assert data["returned_count"] == count, data
                assert data["retrieval"] == "bm25" and not data.get("models"), data
                source = await client.call_tool("get_source", {"evidence_id": data["items"][0]["evidence_id"]})
                assert not source.is_error, source
                original = source.structured_content
                original = original.get("result", original)
                assert original["source"]["sha256"] == data["items"][0]["source_hash"]
                if kind == "rule":
                    assert original["text"] == data["items"][0]["quote"]
    print("Installed release: chart, directory, scene/rule/case retrieval and source lookup passed.")


if __name__ == "__main__":
    asyncio.run(main())
