"""Print bounded source-format samples, without changing the corpus."""
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for source in map(json.loads, (root / "data/sources.jsonl").read_text(encoding="utf-8").splitlines()):
    lines = (root / source["path"]).read_text(encoding="utf-8").splitlines()
    cutoff = next((i for i, line in enumerate(lines) if line.startswith("## 原文逐段校核副本")), len(lines))
    starts = [(i + 1, line) for i, line in enumerate(lines[:cutoff]) if re.search(r"^(?:求测人|占问|例[一二三四五六七八九十百\d]|\*{0,2}例[一二三四五六七八九十\d])", line.strip())]
    print(json.dumps({"source": source["source_id"], "lines": len(lines), "main_lines": cutoff, "starts": len(starts), "samples": starts[:6]}, ensure_ascii=False))
    for start, _ in starts[:1]:
        print("\n".join(f"{i+1}: {lines[i]}" for i in range(start-1, min(start+28, cutoff)) if lines[i].strip()))
