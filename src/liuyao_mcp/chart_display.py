"""Render the calculated chart as a source-independent, copyable comparison table."""
from html import escape

from .chart import relation


def line_text(line):
    symbol = "━━━━━━━" if line["yin_yang"] == "阳" else "━━━　━━━"
    marker = "世" if line.get("shi") else "应" if line.get("ying") else ""
    return f"{line['relative']}{line['stem']}{line['branch']}{line['element']} {symbol} {marker}".strip()


def day_stars(day_ganzhi):
    # Only the five yang stems are displayed for 羊刃; yin-stem schools differ.
    yangren = dict(zip("甲丙戊庚壬", "卯午午酉子")).get(day_ganzhi[0])
    for group, horse, blossom in (("寅午戌", "申", "卯"), ("申子辰", "寅", "酉"),
                                  ("巳酉丑", "亥", "午"), ("亥卯未", "巳", "子")):
        if day_ganzhi[1] in group:
            return {"yangren": yangren, "yima": horse, "xianchi": blossom,
                    "basis": "日干取五阳干羊刃；日支三合局取驿马与咸池，仅作参考"}


def palace_label(hexagram, lines):
    marks = [hexagram['palace'] + "宫"]
    if all("冲" in relation(lines[i]['branch'], lines[i+3]['branch']) for i in range(3)):
        marks.append("六冲")
    elif all("合" in relation(lines[i]['branch'], lines[i+3]['branch']) for i in range(3)):
        marks.append("六合")
    if hexagram.get('palace_stage') in ('游魂', '归魂'):
        marks.append(hexagram['palace_stage'])
    return "·".join(marks)


def render_chart(chart, question=None):
    cal = chart['calendar']
    text = ["**六爻排盘**"]
    if question:
        safe_question = escape(question).replace('|', r'\|').replace('\n', ' ')
        text.append("占问：" + safe_question)
    if cal.get('cast_time'):
        text.append(f"时间：{cal['cast_time']}　{cal['weekday']}（{cal['lunar_date']}）")
    ganzhi = []
    if cal.get('year_ganzhi'):
        ganzhi.append(cal['year_ganzhi'] + "年")
    ganzhi += [cal.get('month_ganzhi', cal['month_branch']) + "月", cal['day_ganzhi'] + "日"]
    if cal.get('hour_ganzhi'):
        ganzhi.append(cal['hour_ganzhi'] + "时")
    text.append("干支：" + "　".join(ganzhi) + "（旬空：" + "、".join(cal['void']) + "）")
    stars = day_stars(cal['day_ganzhi'])
    references = (["羊刃—" + stars['yangren']] if stars['yangren'] else [])
    references += ["驿马—" + stars['yima'], "咸池—" + stars['xianchi']]
    text.append("参考神煞：" + "　".join(references))
    primary, changed = chart['primary'], chart['changed']
    table = [f"| 爻位 | 六神 | 伏神 | 本卦：{primary['full_name']}（{palace_label(primary, chart['lines'])}） | 动爻 | 变卦：{changed['full_name']}（{palace_label(changed, changed['lines'])}） |",
             "| --- | --- | --- | --- | --- | --- |"]
    for line in reversed(chart['lines']):
        position = line['position']
        hidden = line['hidden']
        hidden_text = "—" if not hidden else f"{hidden['relative']}{hidden['stem']}{hidden['branch']}{hidden['element']}"
        motion = "× →" if line['value'] == 6 else "○ →" if line['value'] == 9 else "—"
        name = "上爻" if position == 6 else "初爻" if position == 1 else "二三四五"[position-2] + "爻"
        table.append(f"| {name} | {line['spirit']} | {hidden_text} | `{line_text(line)}` | {motion} | `{line_text(changed['lines'][position-1])}` |")
    text.append("\n".join(table))
    text.append("×：老阴变阳；○：老阳变阴。输入爻值从初爻到上爻，表格从上爻到初爻展示。")
    text.append("变卦六亲沿用本卦宫五行，变卦世应按其自身八宫位置标注。神煞不代替取用与理法判断。")
    if not chart['features']['moving_positions']:
        text.append("本卦全静，右列与本卦相同，不另作有动爻的变卦解读。")
    return {"line_order": "top_to_bottom", "shensha": stars, "markdown": "\n\n".join(text)}
