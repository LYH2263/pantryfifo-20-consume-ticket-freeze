import json

from app.ticket import classify

V2 = {
    "v": 2, "item_id": 1, "item_name": "牛奶", "unit": "盒", "qty": 2, "warn_days": 3,
    "deductions": [{"lot_id": 2, "expiry": "2026-09-28", "take": 2, "remain_before": 2, "remain_after": 0}],
}
LEGACY = {"ok": True, "reason": "", "short": 0.0,
          "deductions": [{"lot_id": 2, "take": 2, "expiry": "2026-09-28"},
                         {"lot_id": 5, "take": 1, "expiry": "2026-10-01"}]}


def test_frozen_ticket_roundtrip():
    r = classify(json.dumps(V2, ensure_ascii=False))
    assert r["state"] == "frozen" and r["ticket"] == V2


def test_legacy_ticket_normalized_without_snapshot():
    r = classify(json.dumps(LEGACY))
    assert r["state"] == "legacy"
    t = r["ticket"]
    assert t["qty"] == 3  # 仅由票内 take 合计
    assert t["item_name"] is None and t["warn_days"] is None
    assert t["deductions"][0]["remain_before"] is None
    assert t["deductions"][0]["remain_after"] is None
    assert t["deductions"][1]["lot_id"] == 5


def test_truncated_json_is_corrupt_and_raw_preserved():
    raw = json.dumps(V2, ensure_ascii=False)[:17]
    r = classify(raw)
    assert r["state"] == "corrupt" and r["raw"] == raw


def test_non_ticket_shapes_are_corrupt():
    assert classify(None)["state"] == "corrupt"
    assert classify("")["state"] == "corrupt"
    assert classify("{}")["state"] == "corrupt"
    assert classify('"abc"')["state"] == "corrupt"
    assert classify('[1,2]')["state"] == "corrupt"
