"""Consume ticket freezing: build an immutable ticket at confirm time, and
classify stored rows as frozen / legacy / drift when reading them back.

Pure functions only — nothing here touches the database, and readers must
never write a repaired ticket back. A corrupted row stays corrupted on disk.
"""
import json

TICKET_VERSION = 2

REQUIRED_TICKET_KEYS = (
    "ticket_version", "item_id", "item_name", "unit", "requested",
    "deductions", "shelf_after", "warn_days", "created_at",
)


def build_ticket(item: dict, requested: float, note: str, deductions: list[dict],
                 remain_after: dict, shelf_after: list[dict], warn_days: int,
                 created_at: str) -> dict:
    """Freeze the face of one successful consume: batch ids, takes, remaining
    snapshot and the warn_days in effect — all pinned as of `created_at`.

    remain_after: {lot_id: qty_remain} for every deducted lot, post-deduction
    (a fully drained lot maps to 0). shelf_after: on-shelf lots still holding
    positive stock for the item, post-deduction.
    """
    frozen_deductions = []
    for d in deductions:
        frozen_deductions.append({
            "lot_id": d["lot_id"],
            "expiry": d.get("expiry"),
            "take": d["take"],
            "remain_after": remain_after[d["lot_id"]],
        })
    return {
        "ticket_version": TICKET_VERSION,
        "item_id": item["id"],
        "item_name": item["name"],
        "unit": item["unit"],
        "requested": float(requested),
        "note": note,
        "deductions": frozen_deductions,
        "shelf_after": [
            {"lot_id": l["id"], "expiry": l.get("expiry"), "remain": l["qty_remain"]}
            for l in sorted(shelf_after, key=lambda l: (l.get("expiry") or "9999-99-99", l["id"]))
        ],
        "warn_days": int(warn_days),
        "created_at": created_at,
    }


def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _valid_frozen(t: dict) -> bool:
    if any(k not in t for k in REQUIRED_TICKET_KEYS):
        return False
    if t["ticket_version"] != TICKET_VERSION:
        return False
    if not _is_num(t["requested"]) or t["requested"] <= 0:
        return False
    if not isinstance(t["deductions"], list) or not t["deductions"]:
        return False
    total = 0.0
    for d in t["deductions"]:
        if not isinstance(d, dict):
            return False
        if not _is_num(d.get("take")) or d["take"] <= 0:
            return False
        if not _is_num(d.get("remain_after")) or d["remain_after"] < 0:
            return False
        if "lot_id" not in d:
            return False
        total += d["take"]
    if abs(total - t["requested"]) > 1e-6:
        return False
    if not isinstance(t["shelf_after"], list):
        return False
    for s in t["shelf_after"]:
        if not isinstance(s, dict) or "lot_id" not in s or not _is_num(s.get("remain")):
            return False
    return True


def _valid_legacy(t: dict) -> bool:
    """Old shape: {ok, reason, deductions:[{lot_id, take, expiry}], short}."""
    if not isinstance(t.get("deductions"), list) or "ok" not in t:
        return False
    for d in t["deductions"]:
        if not isinstance(d, dict) or "lot_id" not in d or not _is_num(d.get("take")):
            return False
    return True


def classify(raw: str) -> dict:
    """Sort a stored result_json into frozen / legacy / drift.

    drift rows carry the raw text back verbatim (state is only a read-time
    label; the stored row is never repaired or rewritten).
    """
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as e:
        return {"state": "drift", "raw": raw, "error": f"json_unreadable: {e}"}
    if not isinstance(data, dict):
        return {"state": "drift", "raw": raw, "error": "not_an_object"}
    if data.get("ticket_version") is not None:
        if _valid_frozen(data):
            return {"state": "frozen", "ticket": data}
        return {"state": "drift", "raw": raw, "error": "ticket_schema_violation"}
    if _valid_legacy(data):
        return {"state": "legacy", "legacy": data}
    return {"state": "drift", "raw": raw, "error": "unrecognized_shape"}
