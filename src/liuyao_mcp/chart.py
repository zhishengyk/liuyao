"""Table-driven Wen Wang / Jing Fang chart mechanics; no fortune judgement."""

from datetime import datetime
from zoneinfo import ZoneInfo

from lunar_python import Solar

ENGINE_VERSION = "najia-0.2"
STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
ELEMENTS = "木火土金水"
BRANCH_ELEMENT = dict(zip(BRANCHES, "水土木木土火火土金金土水"))
TRIGRAMS = ("乾", "兑", "离", "震", "巽", "坎", "艮", "坤")
BITS = dict(zip(TRIGRAMS, (7, 3, 5, 1, 6, 2, 4, 0)))
BY_BITS = {v: k for k, v in BITS.items()}
NATURE = dict(zip(TRIGRAMS, "天泽火雷风水山地"))
PALACE_ELEMENT = dict(zip(TRIGRAMS, "金金火木木水土土"))
NAMES = (
    "乾 履 同人 无妄 姤 讼 遁 否",
    "夬 兑 革 随 大过 困 咸 萃",
    "大有 睽 离 噬嗑 鼎 未济 旅 晋",
    "大壮 归妹 丰 震 恒 解 小过 豫",
    "小畜 中孚 家人 益 巽 涣 渐 观",
    "需 节 既济 屯 井 坎 蹇 比",
    "大畜 损 贲 颐 蛊 蒙 艮 剥",
    "泰 临 明夷 复 升 师 谦 坤",
)
HEXAGRAMS = {}
for upper, row in zip(TRIGRAMS, NAMES):
    for lower, name in zip(TRIGRAMS, row.split()):
        bits = BITS[lower] | (BITS[upper] << 3)
        HEXAGRAMS[bits] = {
            "name": name,
            "full_name": f"{upper}为{NATURE[upper]}" if upper == lower else NATURE[upper] + NATURE[lower] + name,
            "upper": upper, "lower": lower,
        }

NAJIA = {
    "乾": ("甲", "壬", "子寅辰午申戌"),
    "兑": ("丁", "丁", "巳卯丑亥酉未"),
    "离": ("己", "己", "卯丑亥酉未巳"),
    "震": ("庚", "庚", "子寅辰午申戌"),
    "巽": ("辛", "辛", "丑亥酉未巳卯"),
    "坎": ("戊", "戊", "寅辰午申戌子"),
    "艮": ("丙", "丙", "辰午申戌子寅"),
    "坤": ("乙", "癸", "未巳卯丑亥酉"),
}
PALACES = {}
for palace, bits in BITS.items():
    for index, (mask, shi) in enumerate(zip((0, 1, 3, 7, 15, 31, 23, 16), (6, 1, 2, 3, 4, 5, 4, 3))):
        PALACES[(bits | bits << 3) ^ mask] = (palace, shi, index)
SIX_SPIRITS = ("青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武")
SPIRIT_START = (0, 0, 1, 1, 2, 3, 4, 4, 5, 5)
HE = {frozenset(pair) for pair in ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未")}
ADVANCE = set(zip("寅巳申亥丑辰未戌", "卯午酉子辰未戌丑"))


def relationship(base: str, other: str) -> str:
    return ("兄弟", "子孙", "妻财", "官鬼", "父母")[(ELEMENTS.index(other) - ELEMENTS.index(base)) % 5]


def relation(a: str, b: str) -> list[str]:
    """Direction is from a to b. These are mechanical relations, not strength."""
    result = []
    if (BRANCHES.index(a) - BRANCHES.index(b)) % 12 == 6:
        result.append("冲")
    if frozenset((a, b)) in HE:
        result.append("合")
    diff = (ELEMENTS.index(BRANCH_ELEMENT[b]) - ELEMENTS.index(BRANCH_ELEMENT[a])) % 5
    result.append(("同五行", "生", "克", "受克", "受生")[diff])
    return result


def day_void(day_ganzhi: str) -> list[str]:
    if len(day_ganzhi) != 2 or day_ganzhi[0] not in STEMS or day_ganzhi[1] not in BRANCHES:
        raise ValueError("day_ganzhi 必须是有效日干支，例如庚子")
    stem, branch = STEMS.index(day_ganzhi[0]), BRANCHES.index(day_ganzhi[1])
    if (stem - branch) % 2:
        raise ValueError("日干支阴阳不配对")
    start = (branch - stem) % 12
    return [BRANCHES[(start + 10) % 12], BRANCHES[(start + 11) % 12]]


def calendar_values(cast_time=None, month_branch=None, day_ganzhi=None, timezone="Asia/Shanghai"):
    calculated = None
    if cast_time:
        if "T" not in cast_time and " " not in cast_time:
            raise ValueError("cast_time 需包含时刻；历史案例可直接传月支和日干支")
        dt = datetime.fromisoformat(cast_time.replace("Z", "+00:00"))
        zone = ZoneInfo(timezone)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=zone)
        local = dt.astimezone(ZoneInfo("Asia/Shanghai"))
        lunar = Solar.fromYmdHms(local.year, local.month, local.day, local.hour, local.minute, local.second).getLunar()
        calculated = {"cast_time": local.isoformat(), "month_ganzhi": lunar.getMonthInGanZhiExact(), "day_ganzhi": lunar.getDayInGanZhi(), "year_ganzhi": lunar.getYearInGanZhiExact()}
        hour_branch = ((local.hour + 1) // 2) % 12
        day_stem = STEMS.index(calculated["day_ganzhi"][0])
        calculated.update({
            "hour_ganzhi": STEMS[(day_stem % 5 * 2 + hour_branch) % 10] + BRANCHES[hour_branch],
            "lunar_date": f"{lunar.getYearInChinese()}年{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}",
            "weekday": "星期" + lunar.getWeekInChinese(),
        })
        if month_branch and month_branch != calculated["month_ganzhi"][1]:
            raise ValueError("时间重算月支与传入月支冲突")
        if day_ganzhi and day_ganzhi != calculated["day_ganzhi"]:
            raise ValueError("时间重算日干支与传入日干支冲突")
        month_branch, day_ganzhi = calculated["month_ganzhi"][1], calculated["day_ganzhi"]
    if not month_branch or len(month_branch) != 1 or month_branch not in BRANCHES:
        raise ValueError("请传完整起卦时间，或有效月支及日干支")
    void = day_void(day_ganzhi or "")
    return {**(calculated or {}), "month_branch": month_branch, "day_ganzhi": day_ganzhi, "void": void, "basis": "calendar_calculated" if calculated else "supplied_ganzhi", "convention": "Asia/Shanghai; 节气换月; 00:00换日; 不换算真太阳时"}


def line_data(bits, palace_element):
    lower, upper = BY_BITS[bits & 7], BY_BITS[bits >> 3]
    result = []
    for i in range(6):
        inner = i < 3
        stems_inner, stems_outer, branches = NAJIA[lower if inner else upper]
        branch = branches[i]
        result.append({"position": i + 1, "yin_yang": "阳" if bits >> i & 1 else "阴", "stem": stems_inner if inner else stems_outer, "branch": branch, "element": BRANCH_ELEMENT[branch], "relative": relationship(palace_element, BRANCH_ELEMENT[branch])})
    return result


def build_chart(line_values: list[int], cast_time: str | None = None, month_branch: str | None = None, day_ganzhi: str | None = None, timezone: str = "Asia/Shanghai") -> dict:
    """六爻从初爻到上爻：6老阴、7少阳、8少阴、9老阳。"""
    if len(line_values) != 6 or any(type(v) is not int or v not in (6, 7, 8, 9) for v in line_values):
        raise ValueError("line_values 必须是从初爻到上爻的六个6/7/8/9整数")
    cal = calendar_values(cast_time, month_branch, day_ganzhi, timezone)
    bits = sum((v % 2) << i for i, v in enumerate(line_values))
    moving = [i + 1 for i, v in enumerate(line_values) if v in (6, 9)]
    changed_bits = bits ^ sum(1 << (p - 1) for p in moving)
    palace, shi, index = PALACES[bits]
    ying = (shi + 2) % 6 + 1
    base = PALACE_ELEMENT[palace]
    lines = line_data(bits, base)
    changed = line_data(changed_bits, base)
    changed_palace, changed_shi, changed_stage = PALACES[changed_bits]
    changed_ying = (changed_shi + 2) % 6 + 1
    for line in changed:
        line.update(shi=line["position"] == changed_shi, ying=line["position"] == changed_ying)
    pure = line_data(BITS[palace] * 9, base)
    present = {line["relative"] for line in lines}
    spirit = SPIRIT_START[STEMS.index(cal["day_ganzhi"][0])]
    for i, line in enumerate(lines):
        line.update({"value": line_values[i], "moving": i + 1 in moving, "shi": i + 1 == shi, "ying": i + 1 == ying, "spirit": SIX_SPIRITS[(spirit + i) % 6], "void": line["branch"] in cal["void"], "month_relations": relation(cal["month_branch"], line["branch"]), "day_relations": relation(cal["day_ganzhi"][1], line["branch"])})
        line["month_break"] = "冲" in line["month_relations"]
        line["day_clash"] = "冲" in line["day_relations"]
        line["hidden"] = pure[i] if pure[i]["relative"] not in present else None
        line["transformation"] = None
        if line["moving"]:
            line["transformation"] = {**changed[i], "to_original_relations": relation(changed[i]["branch"], line["branch"]), "advance": (line["branch"], changed[i]["branch"]) in ADVANCE, "retreat": (changed[i]["branch"], line["branch"]) in ADVANCE}
    shi_ying = relation(lines[shi - 1]["branch"], lines[ying - 1]["branch"])
    return {
        "engine_version": ENGINE_VERSION, "line_order": "bottom_to_top", "line_values": line_values,
        "calendar": cal, "primary": {**HEXAGRAMS[bits], "palace": palace, "palace_element": base, "palace_stage": ("本宫", "一世", "二世", "三世", "四世", "五世", "游魂", "归魂")[index]},
        "changed": {**HEXAGRAMS[changed_bits], "palace": changed_palace, "palace_element": PALACE_ELEMENT[changed_palace], "palace_stage": ("本宫", "一世", "二世", "三世", "四世", "五世", "游魂", "归魂")[changed_stage], "shi_position": changed_shi, "ying_position": changed_ying, "relative_basis": "original_palace_element", "lines": changed}, "shi_position": shi, "ying_position": ying, "lines": lines,
        "features": {"moving_positions": moving, "void_positions": [l["position"] for l in lines if l["void"]], "month_break_positions": [l["position"] for l in lines if l["month_break"]], "day_clash_positions": [l["position"] for l in lines if l["day_clash"]], "shi_relative": lines[shi - 1]["relative"], "ying_relative": lines[ying - 1]["relative"], "shi_ying_relations": shi_ying, "six_clash": all("冲" in relation(lines[i]["branch"], lines[i + 3]["branch"]) for i in range(3)), "six_harmony": all("合" in relation(lines[i]["branch"], lines[i + 3]["branch"]) for i in range(3))},
        "interpretation_boundary": "用神、综合旺衰、成局及应期须检索带出处的理法；日冲不直接等于暗动或日破。",
    }
