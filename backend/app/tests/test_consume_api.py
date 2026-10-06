import json

import pytest
from fastapi.testclient import TestClient

from app.db import connect
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with TestClient(app) as c:
        yield c


def _rows(sql, args=()):
    c = connect()
    out = [dict(r) for r in c.execute(sql, args)]
    c.close()
    return out


def test_consume_freezes_ticket_against_later_changes(client):
    r = client.post("/api/consume", json={"item_id": 1, "qty": 2, "note": "早餐"})
    assert r.status_code == 200
    cid = r.json()["id"]
    frozen = client.get(f"/api/consumptions/{cid}").json()
    assert frozen["state"] == "frozen"
    t = frozen["ticket"]
    assert t["v"] == 2 and t["item_name"] == "牛奶" and t["warn_days"] == 3
    assert t["deductions"][0]["remain_before"] is not None

    # 之后入库新批 + 改 warn_days:票面必须仍是当时那张
    client.post("/api/lots", json={"item_id": 1, "qty": 9, "expiry": "2027-01-01"})
    c = connect()
    c.execute("UPDATE settings SET value='30' WHERE key='warn_days'")
    c.commit(); c.close()
    again = client.get(f"/api/consumptions/{cid}").json()
    assert again == frozen
    # 全层跟新在架(现世代)
    assert any(l["qty_remain"] == 9 for l in client.get("/api/fridge").json())


def test_failed_consume_leaves_no_ticket(client):
    before = len(_rows("SELECT * FROM consumptions"))
    assert client.post("/api/consume", json={"item_id": 1, "qty": 999}).status_code == 409
    assert client.post("/api/consume", json={"item_id": 1, "qty": 0}).status_code == 400
    assert client.post("/api/consume", json={"item_id": 404, "qty": 1}).status_code == 404
    assert len(_rows("SELECT * FROM consumptions")) == before
    assert len(client.get("/api/consumptions").json()) == before


def test_legacy_row_converges_without_writeback(client):
    legacy = json.dumps({"ok": True, "reason": "", "short": 0.0,
                         "deductions": [{"lot_id": 1, "take": 2, "expiry": "2026-01-01"}]})
    c = connect()
    cur = c.execute("INSERT INTO consumptions(note,result_json,created_at) VALUES (?,?,?)",
                    ("旧票", legacy, "2026-01-02T00:00:00+00:00"))
    c.commit(); cid = cur.lastrowid; c.close()

    d = client.get(f"/api/consumptions/{cid}").json()
    assert d["state"] == "legacy"
    assert d["ticket"]["deductions"][0]["remain_before"] is None
    assert d["ticket"]["qty"] == 2
    lst = client.get("/api/consumptions").json()
    assert [e["state"] for e in lst if e["id"] == cid] == ["legacy"]
    # 读取绝不写回:库中原文一字不动
    assert _rows("SELECT result_json FROM consumptions WHERE id=?", (cid,))[0]["result_json"] == legacy


def test_corrupt_row_marked_drift_consistently_and_untouched(client):
    raw = '{"v":2,"item_id":1,"ded'
    c = connect()
    cur = c.execute("INSERT INTO consumptions(note,result_json,created_at) VALUES (?,?,?)",
                    ("坏票", raw, "2026-01-03T00:00:00+00:00"))
    c.commit(); cid = cur.lastrowid; c.close()

    d = client.get(f"/api/consumptions/{cid}")
    assert d.status_code == 200
    assert d.json()["state"] == "corrupt" and d.json()["raw"] == raw
    lst = client.get("/api/consumptions").json()
    assert [e["state"] for e in lst if e["id"] == cid] == ["corrupt"]
    assert _rows("SELECT result_json FROM consumptions WHERE id=?", (cid,))[0]["result_json"] == raw


def test_missing_consumption_404(client):
    assert client.get("/api/consumptions/9999").status_code == 404
