"""Explicit concept references, compiled into SQLite with the manual corpus."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .common import database_path, dumps, project_root

VERSION = "rule-references-1"
SCHEMA = "CREATE TABLE IF NOT EXISTS rule_references(reference_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"


def load_mapping(root=None):
    path = Path(root or project_root()) / "data/manual_slices/rule_references.json"
    if not path.is_file():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    if document["schema_version"] != VERSION:
        raise ValueError("unsupported rule reference schema")
    references = document["references"]
    seen = set(references)
    for reference_id, entry in references.items():
        for alias in entry.get("legacy_ids", []):
            if alias in seen:
                raise ValueError(f"duplicate rule reference or alias: {alias}")
            seen.add(alias)
        targets = entry["target_ids"]
        if (not isinstance(targets, list)
                or any(not isinstance(target, str) or not target.strip() for target in targets)
                or len(set(targets)) != len(targets)):
            raise ValueError(f"invalid rule reference targets: {reference_id}")
        if entry["status"] not in ("mapped", "unresolved"):
            raise ValueError(f"invalid rule reference status: {reference_id}")
    return references


def store_mapping(db, root=None):
    """Store the reviewed mapping; the caller owns the database transaction."""
    references = load_mapping(root)
    db.execute(SCHEMA)
    db.execute("DELETE FROM rule_references")
    db.executemany("INSERT INTO rule_references VALUES (?, ?)",
                   ((key, dumps(entry)) for key, entry in references.items()))
    return len(references)


def resolve(db, reference_id):
    """Resolve only explicit bindings to approved manual rule units in this DB.

    A target set is complete only when every target passes. Chapter navigation
    and legacy identifiers never substitute for approved source text.
    """
    result = {"reference_id": reference_id, "status": "unavailable",
              "source_rule_ids": [], "target_checks": []}
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rule_references'").fetchone():
        return {**result, "reason": "reference_registry_unavailable"}
    row = db.execute("SELECT reference_id, payload FROM rule_references WHERE reference_id=?",
                     (reference_id,)).fetchone()
    if row is None:
        # ponytail: 35 concepts; keep aliases in the payload instead of a second table.
        row = next((candidate for candidate in db.execute("SELECT reference_id, payload FROM rule_references")
                    if reference_id in json.loads(candidate[1]).get("legacy_ids", [])), None)
    if row is None:
        return {**result, "reason": "unknown_reference"}
    entry = json.loads(row[1])
    result.update(reference_id=row[0], concept=entry["concept"], source_id=entry["source_id"],
                  locator=entry.get("locator"), source_scope=entry.get("source_scope"),
                  source_support=entry.get("source_support"),
                  algorithm_boundary=entry.get("algorithm_boundary"),
                  mapping_status=entry["status"])
    if reference_id != row[0]:
        result["legacy_alias"] = reference_id
    if entry["status"] != "mapped" or not entry["target_ids"]:
        return {**result, "reason": "unresolved_reference"}
    for target_id in entry["target_ids"]:
        target = db.execute("SELECT payload FROM chunks WHERE id=?", (target_id,)).fetchone()
        check = {"evidence_id": target_id, "status": "unavailable"}
        if target is None:
            check["reason"] = "rule_target_missing"
        else:
            unit = json.loads(target[0])
            review = unit.get("review", {})
            if (unit.get("content_role") != "theory"
                    or unit.get("extraction", {}).get("method") != "approved_manual_slices"):
                check["reason"] = "not_manual_rule"
            elif (review.get("status") != "approved"
                  or any(not isinstance(review.get(key), str) or not review[key].strip()
                         for key in ("basis", "reviewer"))):
                check["reason"] = "target_not_approved"
            elif unit.get("source_id") != entry["source_id"]:
                check["reason"] = "target_source_mismatch"
            else:
                check.update(status="available", source_id=unit["source_id"],
                             chapter=unit["chapter"], canonical_spans=unit["canonical_spans"])
        result["target_checks"].append(check)
    if all(check["status"] == "available" for check in result["target_checks"]):
        result.update(status="available", source_rule_ids=list(entry["target_ids"]))
    else:
        result["reason"] = "unavailable_targets"
    return result


def resolve_rule_reference(reference_id, db_path=None):
    path = Path(db_path or database_path()).resolve()
    if not path.is_file():
        return {"reference_id": reference_id, "status": "unavailable",
                "reason": "database_unavailable", "source_rule_ids": [], "target_checks": []}
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        return resolve(db, reference_id)
