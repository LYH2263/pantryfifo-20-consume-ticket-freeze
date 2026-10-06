"""Ticket freezing: frozen tickets never move, legacy rows stay read-only,
drift rows are surfaced verbatim, failed confirms leave no ticket behind."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.engines.ticket import build_ticket, classify
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with TestClient(app) as cl:
        yield cl


def raw_db(tmp_path):
    return sqlite3.connect(tmp_path / "pantryfifo.db")


def test_frozen_ticket_survives_new_lots_and_warn_change(client, tmp_path):
    r = client.post("/api/consume", json={"item_id": 1, "qty": 2, "note": "早餐"})
    assert r.status_code == 200
    cid = r.json()["id"]
    t = r.json()["ticket"]
    # FEFO: 2026-09-28 lot drains first, then 2026-10-01
    assert [(d["lot_id"], d["take"], d["remain_after"]) for d in t["deductions"]] == [
        (2, 1, 0), (1, 1, 1)]
    assert t["warn_days"] == 3 and t["item_name"] == "牛奶"

    first = client.get(f"/api/consumptions/{cid}")
    assert first.status_code == 200 and first.json()["state"] == "frozen"

    # new batch inbound + warn_days changed afterwards
    client.post("/api/lots", json={"item_id": 1, "qty": 5, "expiry": "2026-12-01"})
    db = raw_db(tmp_path)
    db.execute("UPDATE settings SET value='30' WHERE key='warn_days'")
    db.commit(); db.close()

    again = client.get(f"/api/consumptions/{cid}")
    assert again.json() == first.json()  # ticket face is pinned, byte for byte
    assert again.json()["ticket"]["warn_days"] == 3
    # ...while the live layer view moved on
    live = client.get("/api/fridge?layer=upper").json()
    assert any(l["qty_remain"] == 5 and l["expiry"] == "2026-12-01" for l in live)


def test_legacy_row_readonly_and_never_rewritten(client, tmp_path):
    legacy = {"ok": True, "reason": "", "short": 0.0,
              "deductions": [{"lot_id": 1, "take": 1, "expiry": "2026-10-01"}]}
    db = raw_db(tmp_path)
    cur = db.execute("INSERT INTO consumptions(note,result_json,created_at) VALUES (?,?,?)",
                     ("旧票", json.dumps(legacy), "2026-09-01T00:00:00+00:00"))
    cid = cur.lastrowid
    db.commit()

    lst = client.get("/api/consumptions").json()
    assert lst[0]["id"] == cid and lst[0]["state"] == "legacy"

    d = client.get(f"/api/consumptions/{cid}").json()
    assert d["state"] == "legacy" and "ticket" not in d
    assert d["legacy"]["deductions"][0]["lot_id"] == 1

    row = db.execute("SELECT result_json FROM consumptions WHERE id=?", (cid,)).fetchone()
    db.close()
    assert json.loads(row[0]) == legacy  # no snapshot backfilled, no rewrite


def test_drift_truncated_json_shown_verbatim_and_listed(client, tmp_path):
    truncated = '{"ticket_version": 2, "item_id": 1, "item_na'
    db = raw_db(tmp_path)
    cur = db.execute("INSERT INTO consumptions(note,result_json,created_at) VALUES (?,?,?)",
                     ("坏票", truncated, "2026-09-02T00:00:00+00:00"))
    cid = cur.lastrowid
    db.commit()

    lst = client.get("/api/consumptions").json()
    assert lst[0]["state"] == "drift"  # list and detail agree

    d = client.get(f"/api/consumptions/{cid}").json()
    assert d["state"] == "drift"
    assert d["raw"] == truncated and d["error"].startswith("json_unreadable")

    row = db.execute("SELECT result_json FROM consumptions WHERE id=?", (cid,)).fetchone()
    db.close()
    assert row[0] == truncated  # not silently repaired


def test_drift_tampered_frozen_ticket(client, tmp_path):
    tampered = build_ticket({"id": 1, "name": "牛奶", "unit": "盒"}, 2, "",
                            [{"lot_id": 1, "take": 1, "expiry": "2026-10-01"}],
                            {1: 1}, [], 3, "2026-09-03T00:00:00+00:00")
    assert tampered["requested"] == 2  # takes sum to 1 → schema violation
    db = raw_db(tmp_path)
    cur = db.execute("INSERT INTO consumptions(note,result_json,created_at) VALUES (?,?,?)",
                     ("", json.dumps(tampered), tampered["created_at"]))
    cid = cur.lastrowid
    db.commit(); db.close()

    d = client.get(f"/api/consumptions/{cid}").json()
    assert d["state"] == "drift" and d["error"] == "ticket_schema_violation"


def test_failed_confirm_leaves_no_ticket(client, tmp_path):
    assert client.post("/api/consume", json={"item_id": 1, "qty": 99}).status_code == 409
    assert client.post("/api/consume", json={"item_id": 1, "qty": 0}).status_code == 400
    assert client.post("/api/consume", json={"item_id": 1, "qty": -2}).status_code == 400
    assert client.get("/api/consumptions").json() == []
    db = raw_db(tmp_path)
    n = db.execute("SELECT COUNT(*) FROM consumptions").fetchone()[0]
    stock = db.execute("SELECT SUM(qty_remain) FROM lots WHERE item_id=1 AND status='on_shelf'").fetchone()[0]
    db.close()
    assert n == 0 and stock == 3  # no fake ticket, no phantom deduction


def test_classify_shapes():
    good = build_ticket({"id": 1, "name": "n", "unit": "u"}, 1, "",
                        [{"lot_id": 7, "take": 1, "expiry": None}],
                        {7: 0}, [{"id": 8, "expiry": "2027-01-01", "qty_remain": 2}],
                        3, "2026-01-01T00:00:00+00:00")
    assert classify(json.dumps(good))["state"] == "frozen"
    assert classify('{"ok": true, "deductions": []}')["state"] == "legacy"
    assert classify('{"ok": true, "deductions": [{"take": "x"}]}')["state"] == "drift"
    assert classify("[1,2,3]")["state"] == "drift"
    assert classify("not json at all")["state"] == "drift"
    missing = {k: v for k, v in good.items() if k != "shelf_after"}
    assert classify(json.dumps(missing))["state"] == "drift"
