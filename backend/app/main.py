import json
from datetime import date, datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect
from app.engines.fefo import consume_fefo, expire_lots
from app.engines.ticket import build_ticket, classify

app = FastAPI(title="Pantryfifo", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

@app.get("/api/health")
def health(): return {"ok": True, "project": "pantryfifo"}

@app.get("/api/items")
def items():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM items")]; c.close(); return rows

@app.get("/api/fridge")
def fridge(layer: str | None = None):
    c = connect()
    q = """SELECT lots.*, items.name, items.layer, items.unit FROM lots
           JOIN items ON items.id=lots.item_id WHERE lots.status='on_shelf'"""
    args = []
    if layer:
        q += " AND items.layer=?"; args.append(layer)
    rows = [dict(r) for r in c.execute(q, args)]; c.close(); return rows

@app.get("/api/alerts")
def alerts():
    c = connect()
    warn = int(c.execute("SELECT value FROM settings WHERE key='warn_days'").fetchone()["value"])
    today = date.today().isoformat()
    rows = [dict(r) for r in c.execute(
        """SELECT lots.*, items.name, items.layer FROM lots JOIN items ON items.id=lots.item_id
           WHERE status='on_shelf' AND qty_remain>0 AND expiry IS NOT NULL""")]
    c.close()
    out = []
    for r in rows:
        if r["expiry"] <= today:
            r["level"] = "expired"
            out.append(r)
        else:
            # simple day diff via fromisoformat
            delta = (date.fromisoformat(r["expiry"]) - date.today()).days
            if delta <= warn:
                r["level"] = "soon"; r["days_left"] = delta; out.append(r)
    return out

class LotIn(BaseModel):
    item_id: int
    qty: float
    expiry: str

@app.post("/api/lots")
def inbound(body: LotIn):
    c = connect()
    item = c.execute("SELECT id FROM items WHERE id=?", (body.item_id,)).fetchone()
    if not item: c.close(); raise HTTPException(404, "item")
    cur = c.execute(
        "INSERT INTO lots(item_id,qty_in,qty_remain,expiry,status,data_quality) VALUES (?,?,?,?,?,?)",
        (body.item_id, body.qty, body.qty, body.expiry, "on_shelf", "clean"))
    c.commit(); lid = cur.lastrowid; c.close(); return {"id": lid}

class ConsumeIn(BaseModel):
    item_id: int
    qty: float
    note: str = ""

@app.post("/api/consume")
def consume(body: ConsumeIn):
    c = connect()
    try:
        item = c.execute("SELECT * FROM items WHERE id=?", (body.item_id,)).fetchone()
        if not item:
            raise HTTPException(404, "item")
        lots = [dict(r) for r in c.execute(
            "SELECT * FROM lots WHERE item_id=? AND status='on_shelf' AND qty_remain>0", (body.item_id,))]
        result = consume_fefo(lots, body.qty)
        if not result["ok"] and result["reason"] == "qty_non_positive":
            raise HTTPException(400, result["reason"])
        if not result["ok"]:
            raise HTTPException(409, result)
        # success path only from here: deduct, freeze the ticket, commit once —
        # a failed confirm writes nothing and leaves no openable ticket behind
        remain = {l["id"]: float(l["qty_remain"]) for l in lots}
        for d in result["deductions"]:
            remain[d["lot_id"]] = round(remain[d["lot_id"]] - d["take"], 6)
        for d in result["deductions"]:
            if remain[d["lot_id"]] <= 0:
                c.execute("UPDATE lots SET status='consumed', qty_remain=0 WHERE id=?", (d["lot_id"],))
            else:
                c.execute("UPDATE lots SET qty_remain=? WHERE id=?", (remain[d["lot_id"]], d["lot_id"]))
        shelf_after = [dict(r) for r in c.execute(
            "SELECT * FROM lots WHERE item_id=? AND status='on_shelf' AND qty_remain>0", (body.item_id,))]
        warn = int(c.execute("SELECT value FROM settings WHERE key='warn_days'").fetchone()["value"])
        now = datetime.now(timezone.utc).isoformat()
        ticket = build_ticket(dict(item), body.qty, body.note, result["deductions"],
                              remain, shelf_after, warn, now)
        cur = c.execute("INSERT INTO consumptions(note,result_json,created_at) VALUES (?,?,?)",
                        (body.note, json.dumps(ticket, ensure_ascii=False), now))
        cid = cur.lastrowid
        c.commit()
    except HTTPException:
        c.rollback()
        raise
    except Exception:
        c.rollback()
        raise HTTPException(500, "consume_failed")
    finally:
        c.close()
    return {"id": cid, "ticket": ticket}

@app.get("/api/consumptions")
def consumptions():
    """History list. Read-only: rows are classified, never repaired or rewritten."""
    c = connect()
    rows = [dict(r) for r in c.execute("SELECT * FROM consumptions ORDER BY id DESC")]
    c.close()
    out = []
    for r in rows:
        info = classify(r["result_json"])
        entry = {"id": r["id"], "note": r["note"], "created_at": r["created_at"], "state": info["state"]}
        if info["state"] == "frozen":
            t = info["ticket"]
            entry["summary"] = {"item_name": t["item_name"], "requested": t["requested"], "unit": t["unit"]}
        elif info["state"] == "legacy":
            entry["summary"] = {"takes": len(info["legacy"]["deductions"])}
        out.append(entry)
    return out

@app.get("/api/consumptions/{cid}")
def consumption_detail(cid: int):
    """Ticket detail. Read-only: drift rows are returned verbatim with their raw
    payload; nothing is recomputed from current shelf state or written back."""
    c = connect()
    r = c.execute("SELECT * FROM consumptions WHERE id=?", (cid,)).fetchone()
    c.close()
    if not r:
        raise HTTPException(404, "consumption")
    info = classify(r["result_json"])
    return {"id": r["id"], "note": r["note"], "created_at": r["created_at"], **info}

@app.post("/api/expire-sweep")
def expire_sweep():
    c = connect()
    lots = [dict(r) for r in c.execute("SELECT * FROM lots WHERE status='on_shelf'")]
    ids = expire_lots(lots, date.today().isoformat())
    for i in ids:
        c.execute("UPDATE lots SET status='expired' WHERE id=?", (i,))
    c.commit(); c.close(); return {"expired_ids": ids}

@app.get("/api/settings")
def settings():
    c = connect(); rows = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; c.close(); return rows
