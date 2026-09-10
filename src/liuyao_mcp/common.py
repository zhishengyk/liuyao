import hashlib
import html
import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

TERMS = "用神 元神 原神 忌神 仇神 世爻 应爻 世应 官鬼 妻财 父母 兄弟 子孙 旬空 空亡 月破 日破 月建 日辰 动爻 静爻 变爻 伏神 飞神 回头生 回头克 化进神 化退神 进神 退神 六神 六亲 青龙 朱雀 勾陈 螣蛇 白虎 玄武 三合 三刑 六合 六冲 暗动 反吟 伏吟 入墓 出空 填实 旺相 休囚 求职 工作 感情 婚姻 财运 求财 应期 理法 象法".split()
ALIASES = {"空亡": "旬空", "原神": "元神", "螣蛇": "腾蛇", "求职": "工作", "录用": "工作", "应聘": "工作", "面试": "工作", "找工作": "工作", "工作机会": "工作", "感情": "婚姻", "恋爱": "婚姻", "回头生": "回头生", "化进": "进神", "化退": "退神"}
TOPICS = {
    "job": ("工作", "求职", "应聘", "录用", "升职", "职位", "面试", "升官", "功名", "上班", "实习"),
    "relationship": ("感情", "女友", "男友", "结婚", "婚姻", "恋爱", "姻缘", "离婚"),
    "wealth": ("求财", "财运", "生意", "买卖", "投资", "赚钱", "钱财", "店", "借钱", "创业"),
    "health": ("病", "身体", "手术", "医院", "重症", "瘟症"),
    "study": ("考试", "考学", "升学", "成绩", "学习"),
    "lost": ("丢失", "失物", "不见", "失盗", "遗失", "走失"),
    "travel": ("出行", "出差", "旅行", "远行", "行人"),
    "children": ("怀孕", "备孕", "生育", "产期"),
    "lawsuit": ("诉讼", "法院", "官司", "强制执行"),
}


def project_root():
    return Path(os.environ.get("LIUYAO_ROOT", Path(__file__).resolve().parents[2])).resolve()


def database_path():
    if "LIUYAO_DB" in os.environ:
        return Path(os.environ["LIUYAO_DB"]).resolve()
    bundled = Path(__file__).parent / "_data/knowledge.sqlite"
    if "LIUYAO_ROOT" in os.environ or (project_root()/"data/sources.jsonl").is_file():
        return project_root()/"data/knowledge.sqlite"
    if "LIUYAO_ROOT" not in os.environ and bundled.is_file():
        return bundled.resolve()
    return project_root() / "data/knowledge.sqlite"


def runtime_root():
    """Keep model state out of uvx's replaceable package environment."""
    root = project_root()
    if "LIUYAO_ROOT" in os.environ or (root/"data/sources.jsonl").is_file():
        return root
    if (Path(__file__).parent/"_data/knowledge.sqlite").is_file():
        base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or Path.home()/".cache")
        return base/"liuyao-mcp"
    return root


def retrieval_data_dir(db_path=None):
    if db_path is not None:
        return Path(db_path).resolve().parent
    if runtime_root() != project_root():
        return runtime_root()/"data"
    return database_path().parent


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def plain(text):
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"[\s*_`\\]+", " ", text).strip()


def normalized(text):
    return re.sub(r"[^\w\u4e00-\u9fff]", "", plain(text)).lower()


def topic_of(text):
    scores = {k: sum(word in text for word in words) for k, words in TOPICS.items()}
    return max(scores, key=scores.get) if max(scores.values(), default=0) else None


@lru_cache(maxsize=1)
def tokenizer():
    import jieba
    jieba.setLogLevel(logging.ERROR)
    t = jieba.Tokenizer()
    for term in TERMS + list(ALIASES):
        t.add_word(term, freq=100000)
    return t


def tokens(text):
    words = [w.lower() for w in tokenizer().cut(plain(text), HMM=False) if re.fullmatch(r"[\w\u4e00-\u9fff]+", w)]
    # Canonical aliases are extra tokens; quoted source text is never changed.
    return words + [ALIASES[w] for w in words if w in ALIASES and ALIASES[w] != w]


def case_search_text(case):
    """Shared BM25/dense/reranker input. Author conclusions and outcomes excluded."""
    features = case.get("features", {})
    parts = [case["question"]["raw"] or ""]
    labels = {"topic":"占类", "shi_relative":"世爻六亲", "ying_relative":"应爻六亲", "shi_ying_relations":"世应关系", "moving_positions":"动爻位置", "void_positions":"旬空爻位", "month_break_positions":"月破爻位", "yongshen_reported":"作者取用候选", "pattern_names":"结构格局"}
    for key,label in labels.items():
        value = features.get(key)
        if value is not None:
            parts.append(f"{label}：{dumps(value)}")
    if case.get("derived") and case["extraction"]["chart_validation"] != "conflict":
        parts.append("本卦："+case["derived"]["primary"]["full_name"])
        for line in case["derived"]["lines"]:
            parts.append(f"第{line['position']}爻：{line['relative']}{line['branch']}" + (" 旬空" if line["void"] else "") + (" 月破" if line["month_break"] else "") + (" 发动" if line["moving"] else ""))
    return "\n".join(parts)
