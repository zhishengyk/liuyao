"""Run with python -m liuyao_mcp.server (stdout is MCP protocol only)."""
import argparse
from typing import Any, Literal
from pydantic import StrictInt

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from . import __version__

from .chart import build_chart as calculate_chart
from .chart_display import render_chart
from .patterns import review_checks
from .retrieval import get_source as read_source, search_knowledge as retrieve, get_outline as browse_outline, get_topics as browse_topics, connect as connect_knowledge
from .rule_references import resolve as resolve_rule_reference

INSTRUCTIONS = """六爻助手提供排盘和可回查的规则原文。生产预测使用当前问题、事前背景、盘面和 kind=rule 的理论证据。
固定顺序：明确对象、关系、动作和时限；缺问意先询问，独立事项原则上分占；核对时间和盘面；在判向前按事项检索领域取用与例外；静卦结合日月和旺爻，动卦先还原动爻及本位变爻再核日月效力；综合用神、元神、忌神和领域规则，不用单点救应短路成败；理法定向后再以六神、爻位等补细节；最后按实际机制取应期，无可靠触发则明确应期不可定。允许可判断、倾向但条件不足、不可判断三种结论，不强制 yes/no。"""
mcp = MCPServer("liuyao", title="六爻助手", instructions=INSTRUCTIONS, version=__version__)
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def checked(function, *args):
    try:
        return function(*args)
    except (ValueError, FileNotFoundError) as exc:
        raise ToolError(str(exc)) from exc


_HEX_IDENTITY = ('name', 'full_name', 'upper', 'lower', 'palace', 'palace_element', 'palace_stage')
_FEATURE_KEEP = ('moving_positions', 'void_positions', 'month_break_positions', 'day_clash_positions',
                 'shi_relative', 'ying_relative', 'shi_ying_relations', 'six_clash', 'six_harmony')


def _mini_hex(hexagram):
    return {key: hexagram[key] for key in _HEX_IDENTITY if key in hexagram}


def _compact_features(features):
    return {key: features[key] for key in _FEATURE_KEEP if key in features}


def _compute_patterns(chart):
    """Attach runtime-only pattern enrichment to a full chart dict (shared by build/inspect)."""
    references = set(chart['patterns']['source_rule_ids'])
    try:
        with connect_knowledge() as db:
            resolved = {ref: resolve_rule_reference(db, ref) for ref in sorted(references)}
    except FileNotFoundError:
        resolved = {ref: {'reference_id': ref, 'status': 'unavailable', 'reason': 'database_unavailable',
                          'source_rule_ids': [], 'target_checks': []} for ref in sorted(references)}
    chart['patterns']['resolved_references'] = resolved
    chart['patterns']['review_checks'] = review_checks(chart)
    return chart


def _bounded_checks(checks, cap_bytes=12000):
    """Keep check text/conditions/queries but strip oversized trigger_facts to bound inspect_chart size."""
    try:
        import json as _json
    except ImportError:  # pragma: no cover
        _json = None
    out = []
    for check in checks:
        copy = dict(check)
        if _json is not None and len(_json.dumps(copy, ensure_ascii=False)) > 2000:
            trigger = copy.get('trigger_facts')
            if isinstance(trigger, dict):
                copy['trigger_facts'] = {'referenced_keys': sorted(trigger.keys())}
            out.append(copy)
        else:
            out.append(copy)
    return out[:cap] if isinstance(cap, int) and cap > 0 else out


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def build_chart(line_values: list[StrictInt], cast_time: str | None = None, month_branch: str | None = None, day_ganzhi: str | None = None, timezone: str = "Asia/Shanghai", question: str | None = None, yongshen_positions: list[StrictInt] | None = None, yongshen_scope: Literal['primary','hidden','changed'] = 'primary', detail: Literal['compact','full'] = 'compact') -> dict[str, Any]:
    """排盘。line_values按初爻到上爻，统一用0老阴、1少阳、2少阴、3老阳。给完整时间或历史月支+日干支。display.markdown包含六神、伏神、本变卦、动爻和世应。根据取用依据传yongshen_positions；yongshen_scope默认primary本卦显爻，hidden为同位伏神，changed只指实际动爻所化变爻，不包含变卦中其他静爻。伏神与变爻返回旬空、日月关系；其moving=null表示明动字段不适用，不能当作静爻或无作用。detail默认compact：只返回盘面事实、lines、features摘要、display与patterns.facts及review_check_ids，用于agent上下文，体积约5-10KB；需要具体审查条目时调用inspect_chart，需要来源时用get_source。detail=full返回全部patterns（resolved_references、完整review_checks、life_stages、combination_checks），供程序测试、人工调试与完整审计；批量agent默认使用compact。"""
    chart = checked(calculate_chart, line_values, cast_time, month_branch, day_ganzhi, timezone, yongshen_positions, yongshen_scope)
    if detail == 'full':
        chart = _compute_patterns(chart)
        return {**chart, "display": render_chart(chart, question)}
    checks = review_checks(chart)
    compact = {
        "line_values": chart["line_values"],
        "calendar": chart["calendar"],
        "primary": _mini_hex(chart["primary"]),
        "changed": _mini_hex(chart["changed"]),
        "shi_position": chart["shi_position"],
        "ying_position": chart["ying_position"],
        "lines": chart["lines"],
        "features": _compact_features(chart["features"]),
        "relation_semantics": chart["relation_semantics"],
        "patterns": {
            "version": chart["patterns"]["version"],
            "facts": chart["patterns"]["facts"],
            "source_rule_ids": chart["patterns"]["source_rule_ids"],
            "yongshen_refs": chart["patterns"].get("yongshen_refs", []),
            "yongshen_candidates_supplied": chart["patterns"].get("yongshen_candidates_supplied", []),
            "review_check_ids": [c["check_id"] for c in checks],
        },
        "display": render_chart(chart, question),
    }
    return compact


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def inspect_chart(line_values: list[StrictInt], cast_time: str | None = None, month_branch: str | None = None, day_ganzhi: str | None = None, timezone: str = "Asia/Shanghai", question: str | None = None, yongshen_positions: list[StrictInt] | None = None, yongshen_scope: Literal['primary','hidden','changed'] = 'primary', max_review_checks: int = 10) -> dict[str, Any]:
    """compact排盘后的条件核查：返回与当前盘相关的patterns.facts、有界数量的review_checks（含trigger_facts/conditions_to_check/suggested_queries）及facts涉及来源的resolved_references；体积有界（max_review_checks默认10）。需要原文再调get_source。参数与build_chart一致。"""
    chart = _compute_patterns(checked(calculate_chart, line_values, cast_time, month_branch, day_ganzhi, timezone, yongshen_positions, yongshen_scope))
    checks = chart['patterns']['review_checks']
    if isinstance(max_review_checks, int) and max_review_checks > 0:
        checks = checks[:max_review_checks]
    fact_refs = {fact.get('source_rule_id') for fact in chart['patterns']['facts'] if fact.get('source_rule_id')}
    resolved = {ref: value for ref, value in chart['patterns']['resolved_references'].items() if ref in fact_refs}
    return {
        "calendar": chart["calendar"],
        "primary": _mini_hex(chart["primary"]),
        "changed": _mini_hex(chart["changed"]),
        "shi_position": chart["shi_position"],
        "ying_position": chart["ying_position"],
        "lines": chart["lines"],
        "features": _compact_features(chart["features"]),
        "patterns": {
            "version": chart["patterns"]["version"],
            "facts": chart["patterns"]["facts"],
            "review_checks": checks,
            "resolved_references": resolved,
        },
        "display": render_chart(chart, question),
    }


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def search_knowledge(query: str, kind: Literal["rule", "case"] = "rule", method: Literal["all", "lifa", "xiangfa"] = "all", topic: str | None = None, author: str | None = None, features: dict | None = None, limit: int | None = None, exclude_ids: list[str] | None = None, exclude_case_ids: list[str] | None = None, max_chars: int = 40000, retrieval_mode: Literal["bm25","hybrid","hybrid_rerank"] | None = None, outline_ids: list[str] | None = None, subtopic: str | None = None, include_common: bool = True, include_unknown: bool = False, require_valid_chart: bool = False) -> dict[str, Any]:
    """检索人工规则或历史案例。生产案例检索只使用并返回事前问题、事前背景、盘面和机械特征；不返回作者断语、事后反馈、结局或复盘。预测方法优先kind=rule并用get_source回查。"""
    try:
        return retrieve(query, kind, method, topic, author, features, limit, exclude_ids, exclude_case_ids, max_chars,retrieval_mode=retrieval_mode,outline_ids=outline_ids,subtopic=subtopic,include_common=include_common,include_unknown=include_unknown,require_valid_chart=require_valid_chart,case_text_scope="initial",prediction_safe=True)
    except (ValueError,FileNotFoundError) as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_topics(topic: str | None = None) -> dict[str, Any]:
    """可选浏览两级事项ID；不传参数列大类，传大类列小类。ID用于显式topic/subtopic筛选，非检索前置步骤；manual库未人工标注的资料保持unknown。象法按场景检索。"""
    return checked(browse_topics, topic)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_outline(source_id: str | None = None, parent_id: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """浏览当前已入库的书籍和人工单位导航。不传参数列书籍，source_id或parent_id列子节点；manual_unit_label为整理标签，不等同原书章题。node_id可用于outline_ids或get_source；同一单位可关联同事件多盘，导航不代表全书切片完成。"""
    return checked(browse_outline, source_id, parent_id, limit, offset)


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_source(evidence_id: str, context_lines: int = 0, offset: int = 0, max_chars: int = 40000, text_version: Literal['corrected','original'] = 'corrected') -> dict[str, Any]:
    """回查同版规则原文或生产提示词。案例ID只返回事前问题、事前背景、盘面和机械特征；作者断语、反馈、结局与复盘不通过生产MCP返回。"""
    try:
        return read_source(evidence_id, context_lines, offset, max_chars, text_version=text_version, prediction_safe=True)
    except (ValueError,FileNotFoundError) as exc:
        raise ToolError(str(exc)) from exc


@mcp.prompt()
def interpret_liuyao(question: str) -> str:
    return INSTRUCTIONS + "\n用户占问：" + question


def self_check():
    """Read-only smoke checks against the actual manual corpus, not a release gate."""
    import json
    from .common import database_path

    with connect_knowledge() as db:
        info = dict(db.execute("SELECT key,value FROM build_info WHERE key!='coverage_report'"))
        assert info.get('mode') == 'manual-corpus'
        assert info.get('coverage_status') in ('complete', 'incomplete')
        counts = {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                  for table in ('chunks', 'cases', 'ocr_pages')}
        quality_counts = dict(db.execute("SELECT json_extract(payload,'$.quality.status'),COUNT(*) FROM cases GROUP BY json_extract(payload,'$.quality.status')"))
        context_row = db.execute("SELECT id,payload FROM chunks WHERE json_array_length(json_extract(payload,'$.required_contexts'))>0 LIMIT 1").fetchone()
        valid_case = db.execute("SELECT evidence_id FROM evidence_metadata WHERE kind='case' AND chart_valid=1 AND searchable=1 LIMIT 1").fetchone()
    assert context_row is not None and valid_case is not None
    chart = build_chart([2] * 6, month_branch="卯", day_ganzhi="庚子")
    assert chart['primary']['name'] == '坤' and len(chart['lines']) == 6 and chart['display']['markdown']
    assert 'review_check_ids' in chart['patterns'] and 'resolved_references' not in chart['patterns']
    full = build_chart([2] * 6, month_branch="卯", day_ganzhi="庚子", detail='full')
    assert 'resolved_references' in full['patterns'] and full['patterns']['review_checks']
    inspected = inspect_chart([2] * 6, month_branch="卯", day_ganzhi="庚子")
    assert inspected['patterns']['facts'] and isinstance(inspected['patterns']['review_checks'], list)
    checked_rules = {}
    for method, query in (('lifa', '取用 用神'), ('xiangfa', '六神 取象')):
        found = search_knowledge(query, method=method, limit=2, max_chars=150000, retrieval_mode='bm25')
        assert found['returned_count'] > 0 and not found['topic_filter_applied']
        item = found['items'][0]
        source = get_source(item['evidence_id'], max_chars=150000)
        assert item['review_status'] == 'approved' and source['text'] == item['quote']
        assert source['source']['sha256'] == item['source_hash']
        assert all('start_column' in span and 'end_column' in span for span in source['source_spans'])
        checked_rules[method] = item['evidence_id']
    context_unit = json.loads(context_row['payload'])
    context_source = get_source(context_row['id'], max_chars=500000)
    assert context_source['required_contexts'] and not context_source.get('required_contexts_omitted')
    assert [item['text'] for item in context_source['required_contexts']] == [item['text'] for item in context_unit['required_contexts']]
    browsed = search_knowledge('', outline_ids=[context_unit['outline']['node_id']], limit=1, max_chars=150000, retrieval_mode='bm25')
    assert browsed['items'][0]['evidence_id'] == context_row['id'] and browsed['items'][0]['required_contexts']
    case = get_source(valid_case[0], max_chars=500000)['structured_case']
    assert all(key not in case for key in ('quality', 'author_yongshen', 'interpretations', 'outcome', 'post_feedback_analysis'))
    assert case['extraction']['chart_validation'] == 'calculated' and case['extraction']['source_chart_independently_verified']
    recomputed = build_chart(case['cast']['line_values'], month_branch=case['cast']['month_branch'], day_ganzhi=case['cast']['day_ganzhi'])
    assert recomputed['primary']['name'] == case['derived']['primary']['name']
    assert recomputed['features']['moving_positions'] == case['features']['moving_positions']
    available = next(ref for ref, result in full['patterns']['resolved_references'].items() if result['status'] == 'available')
    reference = get_source(available)
    assert reference['kind'] == 'rule_reference' and reference['targets']
    assert get_source(reference['targets'][0], max_chars=150000)['text']
    books = get_outline()['items']
    assert books and get_outline(source_id=books[0]['source_id'])['items']
    return {'version': __version__, 'database': str(database_path().resolve()), 'status': 'passed',
            'scope': 'manual_corpus_smoke_check', 'retrieval': 'bm25', 'counts': counts,
            'case_quality': quality_counts,
            'corpus_hash': info['corpus_hash'], 'coverage_status': info['coverage_status'],
            'release_status': 'blocked_incomplete_corpus' if info['coverage_status'] != 'complete' else 'not_assessed_by_self_check',
            'checked_rules': checked_rules, 'required_context_rule': context_row['id'],
            'checked_case': valid_case[0], 'checked_rule_reference': available, 'outline_books': len(books)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--self-check", action="store_true", help="Read-only smoke check of the current manual corpus; incomplete coverage is not releasable")
    args = parser.parse_args()
    if args.self_check:
        import json
        print(json.dumps(self_check(), ensure_ascii=False))
        return
    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport="streamable-http", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
