"""Build prediction-only global/domain prompts from the reviewed routing plan.

Book passages and historical cases stay in SQLite for targeted rule retrieval.
They are never copied into the production prompt bundle.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def source_content_hash(source_rows, unit_rows, page_rows):
    value = {"sources": source_rows, "chunks": unit_rows, "ocr_pages": page_rows}
    return sha(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode())


def build(database, output, plan_path):
    database, output, plan_path = map(Path, (database, output, plan_path))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        source_rows = list(db.execute("SELECT id,metadata,body FROM sources ORDER BY id"))
        unit_rows = list(db.execute("SELECT id,payload FROM chunks ORDER BY id"))
        page_rows = list(db.execute("SELECT source_id,pdf_page,payload FROM ocr_pages ORDER BY source_id,pdf_page"))
        units = {uid: json.loads(payload) for uid, payload in unit_rows}
        sources = {sid: json.loads(metadata) for sid, metadata, _ in source_rows}

    workflow = sorted(plan["workflow"], key=lambda item: item["step"])
    if [item["step"] for item in workflow] != list(range(1, len(workflow) + 1)):
        raise ValueError("Workflow steps must be consecutive from 1")
    evidence_ids = []
    for item in workflow:
        if not item.get("title") or not item.get("route") or not item.get("evidence_ids"):
            raise ValueError(f"Workflow step {item.get('step')} is incomplete")
        for evidence_id in item["evidence_ids"]:
            if evidence_id not in units:
                raise ValueError(f"Workflow references missing evidence: {evidence_id}")
            evidence_ids.append(evidence_id)

    domain_evidence = {}
    for name, domain in plan["domains"].items():
        baseline = domain.get("baseline_evidence_ids", [])
        queries = domain.get("queries", [])
        if not domain.get("flow") or not baseline or not queries:
            raise ValueError(f"Domain {name} needs flow, baseline_evidence_ids and queries")
        for evidence_id in baseline:
            if evidence_id not in units:
                raise ValueError(f"Domain {name} references missing evidence: {evidence_id}")
        domain_evidence[name] = list(dict.fromkeys(baseline))

    global_parts = [
        "# 生产断卦流程\n\n",
        "先用 `kind=rule` 检索当前事项；需要核对原文时再用 `get_source(evidence_id)`。\n\n",
    ]
    for item in workflow:
        global_parts.extend([
            f"## 第{item['step']}步：{item['title']}\n\n",
            item["route"] + "\n\n",
            "按需核对的规则证据：\n\n",
            *[f"- `{evidence_id}`（{sources[units[evidence_id]['source_id']].get('title', units[evidence_id]['source_id'])}）\n"
              for evidence_id in item["evidence_ids"]],
            "\n",
        ])
    global_parts.extend([
        "## 领域入口\n\n",
        "领域规则必须在最终判向前参与。只加载当前原问对应的领域入口；独立问题原则上分占。\n\n",
        *[f"- [{domain['title']}]({name}/PROMPT.md)：{'、'.join(domain['questions'])}\n"
          for name, domain in plan["domains"].items()],
    ])

    generated = {"GLOBAL.md": "".join(global_parts)}
    for name, domain in plan["domains"].items():
        generated[f"{name}/PROMPT.md"] = (
            f"# {domain['title']}领域入口\n\n"
            f"适用问题：{'、'.join(domain['questions'])}。\n\n"
            "## 最低领域知识\n\n"
            f"{domain['flow']}\n\n"
            "## 必读基础规则\n\n"
            "这些规则不依赖动态排名。首次进入本领域时逐条调用 `get_source(evidence_id)`，读取正文及 `required_contexts`；同一任务已经读过且版本未变的可以复用。\n\n"
            + "".join(f"- `{evidence_id}`（{sources[units[evidence_id]['source_id']].get('title', units[evidence_id]['source_id'])}）\n"
                      for evidence_id in domain_evidence[name])
            + "\n## 固定检索顺序\n\n"
            + "".join(f"{index}. `search_knowledge(query=\"{query}\", kind=\"rule\", topic=\"{name}\")`\n"
                      for index, query in enumerate(domain["queries"], 1))
            + "\n先按 [生产断卦流程](../GLOBAL.md) 锁定原问和核盘；动态查询必须加入当前盘面的具体六亲、爻位、动变、空破墓绝和时间范围。"
              "检查 `query_terms`、`unmatched_query_terms`、`required_contexts` 和适用前提；对拟采用规则逐条 `get_source`，并主动查询可能推翻当前方向的相反规则。"
              "只有用户明确询问时间且结果机制已成立时才执行应期查询。连续补查无新增适用证据时停止并说明缺口。\n"
        )

    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"files_sha256": {}}
    for name in previous.get("files_sha256", {}).keys() - generated.keys():
        path = (output / name).resolve()
        if not path.is_relative_to(output.resolve()):
            raise ValueError("Manifest file escapes generated directory")
        path.unlink(missing_ok=True)
    for name, text in generated.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    selected = set(evidence_ids)
    selected.update(evidence_id for ids in domain_evidence.values() for evidence_id in ids)
    manifest = {
        "schema_version": 2,
        "database_sha256": sha(database.read_bytes()),
        "source_content_sha256": source_content_hash(source_rows, unit_rows, page_rows),
        "plan_sha256": sha(plan_path.read_bytes()),
        "theory_units": len(units),
        "database_only_evidence_ids": sorted(set(units) - selected),
        "all_theory_units_accounted": True,
        "evidence_by_bucket": {"global": sorted(set(evidence_ids)),
                               **{name: ids for name, ids in domain_evidence.items()}},
        "selection_policy": plan["selection_policy"],
        "workflow": workflow,
        "sections": [],
        "files_sha256": {name: sha((output / name).read_bytes()) for name in generated},
        "limitations": [
            "Production prompts intentionally exclude verbatim book passages and all case outcomes.",
            "Evidence IDs route the assistant to targeted rule retrieval from the matching database.",
            "Source correctness and prediction validity remain separate questions.",
        ],
    }
    save_json(manifest_path, manifest)
    return manifest


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=root / "data/knowledge.sqlite")
    parser.add_argument("--output", type=Path, default=root / "plugins/liuyao-assistant/skills/interpret-liuyao/references/source-prompts")
    parser.add_argument("--plan", type=Path, default=Path(__file__).with_name("skill_prompt_plan.json"))
    args = parser.parse_args()
    manifest = build(args.database, args.output, args.plan)
    print(json.dumps({
        "theory_units": manifest["theory_units"],
        "files": len(manifest["files_sha256"]),
        "prompt_evidence_ids": len(manifest["evidence_by_bucket"]["global"]),
        "database_only_theory_units": len(manifest["database_only_evidence_ids"]),
    }))


if __name__ == "__main__":
    main()
