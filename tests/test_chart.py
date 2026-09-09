import json
from pathlib import Path
import re

import pytest
from lunar_python import Solar

from liuyao_mcp.chart import BITS, HEXAGRAMS, PALACES, build_chart, day_void
from liuyao_mcp.common import project_root


def test_64_palace_names_against_book_table():
    manifest = [json.loads(l) for l in (project_root()/"data/sources.jsonl").read_text(encoding="utf8").splitlines()]
    text = (project_root()/manifest[0]["path"]).read_text(encoding="utf8")
    rows = re.findall(r"^\| ([乾坤震巽坎离艮兑])宫八卦 \| 性质属. \|(.+)\|\s*$", text, re.M)
    assert len(rows) == 8
    checked = set()
    for palace, cells in rows:
        expected = [c.strip().replace("盅", "蛊") for c in cells.split("|")]
        assert len(expected) == 8
        actual = sorted([(stage, bits) for bits, (p, _, stage) in PALACES.items() if p == palace])
        assert [HEXAGRAMS[bits]["name"] for _, bits in actual] == expected
        checked.update(bits for _, bits in actual)
    assert len(checked) == 64


def test_static_kun_source_example():
    chart = build_chart([2]*6, month_branch="卯", day_ganzhi="庚子")
    assert chart["shi_position"] == 6 and chart["ying_position"] == 3
    assert [(l["relative"], l["branch"]) for l in chart["lines"]] == [("兄弟","未"),("父母","巳"),("官鬼","卯"),("兄弟","丑"),("妻财","亥"),("子孙","酉")]
    assert chart["calendar"]["void"] == ["辰", "巳"]
    assert chart["features"]["month_break_positions"] == [6]
    assert [l["spirit"] for l in chart["lines"]] == ["白虎","玄武","青龙","朱雀","勾陈","螣蛇"]


def test_book_kuai_to_xu_and_original_palace_relatives():
    # 自修宝典: 巳月乙卯，泽天夬四爻亥水动，化子孙申金。
    c = build_chart([1,1,1,3,1,2], month_branch="巳", day_ganzhi="乙卯")
    assert c["primary"]["name"] == "夬" and c["changed"]["name"] == "需"
    line = c["lines"][3]
    assert (line["relative"], line["branch"], line["transformation"]["relative"], line["transformation"]["branch"]) == ("妻财","亥","子孙","申")
    assert c["shi_position"] == 5 and c["ying_position"] == 2


def test_hidden_line_against_book_yu_case():
    # 自修宝典遗失字画例：雷地豫初爻妻财未土，父母子水伏于其下。
    c = build_chart([2,2,2,1,2,0], month_branch="未", day_ganzhi="乙亥")
    assert c["primary"]["name"] == "豫"
    hidden = c["lines"][0]["hidden"]
    assert (hidden["position"],hidden["relative"],hidden["branch"]) == (1,"父母","子")
    from liuyao_mcp.chart_display import render_chart
    assert '| 初爻 | 青龙 | 父母庚子水 |' in render_chart(c)['markdown']


def test_all_hexagram_motion_patterns():
    for bits in range(64):
        for moves in range(64):
            values = [(3 if moves>>i&1 else 1) if bits>>i&1 else (0 if moves>>i&1 else 2) for i in range(6)]
            c = build_chart(values, month_branch="子", day_ganzhi="甲子")
            assert c["changed"]["name"] == HEXAGRAMS[bits^moves]["name"]
            assert len(c["lines"]) == 6
            assert len([l for l in c["lines"] if l["shi"]]) == 1


def test_midnight_and_jieqi_boundaries():
    a = build_chart([1]*6, cast_time="2026-09-09T22:59:00+08:00")
    b = build_chart([1]*6, cast_time="2026-09-09T23:01:00+08:00")
    c = build_chart([1]*6, cast_time="2026-09-10T00:01:00+08:00")
    assert a["calendar"]["day_ganzhi"] == b["calendar"]["day_ganzhi"] != c["calendar"]["day_ganzhi"]
    from datetime import datetime, timedelta
    jie = Solar.fromYmd(2026,9,1).getLunar().getJieQiTable()["白露"]
    point = datetime.fromisoformat(jie.toYmdHms())
    before = build_chart([1]*6, cast_time=(point-timedelta(seconds=1)).isoformat())
    after = build_chart([1]*6, cast_time=(point+timedelta(seconds=1)).isoformat())
    assert before["calendar"]["month_branch"] == "申"
    assert after["calendar"]["month_branch"] == "酉"


def test_screenshot_xun_to_xiaoxu_display():
    from liuyao_mcp.chart_display import render_chart
    chart = build_chart([0,1,1,2,1,1],cast_time="2026-09-05T01:27:00+08:00")
    assert [chart['calendar'][k] for k in ('year_ganzhi','month_ganzhi','day_ganzhi','hour_ganzhi')] == ['丙午','丙申','壬午','辛丑']
    assert chart['calendar']['lunar_date'] == '二〇二六年七月廿四'
    assert chart['calendar']['void'] == ['申','酉']
    assert chart['primary']['name']=='巽' and chart['changed']['name']=='小畜'
    assert (chart['shi_position'],chart['ying_position'])==(6,3)
    assert (chart['changed']['shi_position'],chart['changed']['ying_position'])==(1,4)
    expected = [('兄弟','辛','卯','白虎'),('子孙','辛','巳','螣蛇'),('妻财','辛','未','勾陈'),
                ('官鬼','辛','酉','朱雀'),('父母','辛','亥','青龙'),('妻财','辛','丑','玄武')]
    assert [(l['relative'],l['stem'],l['branch'],l['spirit']) for l in reversed(chart['lines'])]==expected
    display=render_chart(chart,'当前项目的前景如何？')
    assert [display['shensha'][k] for k in ('yangren','yima','xianchi')]==['子','申','卯']
    assert display['markdown'].index('| 上爻 |') < display['markdown'].index('| 初爻 |')
    assert '父母甲子水 ━━━━━━━ 世' in display['markdown']
    assert display['markdown'].count('× →')==1 and '○ →' not in display['markdown']
    assert chart['features']['moving_positions']==[1]


def test_static_display_and_unknown_civil_date():
    from liuyao_mcp.chart_display import render_chart
    chart=build_chart([2]*6,month_branch='卯',day_ganzhi='庚子')
    display=render_chart(chart,'测试 | <br>')
    assert '本卦全静' in display['markdown'] and '时间：' not in display['markdown']
    assert r'测试 \| &lt;br&gt;' in display['markdown']


def test_line_values_are_zero_to_three_throughout():
    values=[0,1,1,2,1,3]
    chart=build_chart(values,month_branch='申',day_ganzhi='壬午')
    assert chart['line_values']==values
    assert [line['value'] for line in chart['lines']]==values
    assert chart['features']['moving_positions']==[1,6]
    assert 'input_format' not in chart and 'input_values' not in chart
    for invalid in ([6,7,7,8,7,9], [0,7,7,8,7,7]):
        with pytest.raises(ValueError,match='0/1/2/3'):
            build_chart(invalid,month_branch='申',day_ganzhi='壬午')


@pytest.mark.parametrize("values,kwargs", [([1]*5,{}),([True]*6,{}),([1]*6,{}),([1]*6,{"month_branch":"卯","day_ganzhi":"甲丑"}),([1]*6,{"cast_time":"2026-09-09"}),([1]*6,{"cast_time":"2026-09-09T12:00:00+08:00","month_branch":"子"})])
def test_bad_inputs(values,kwargs):
    with pytest.raises(ValueError):
        build_chart(values,**kwargs)
