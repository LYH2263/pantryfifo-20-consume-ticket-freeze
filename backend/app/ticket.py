"""票面分类:读侧唯一判定入口,履历列表与详情共用。只读,绝不写回。

三态:
  frozen  — v2 冻结票,批号/take/当时余量快照自足
  legacy  — 旧世代票(无快照字段),缺失字段补 None,绝不按现架现算
  corrupt — JSON 无法解析或形状不识,票面漂移,原文原样保留
"""
import json

TICKET_VERSION = 2


def classify(raw):
    """raw 为 consumptions.result_json 原文,返回 {"state": ..., "ticket"|"raw": ...}。"""
    if not raw:
        return {"state": "corrupt", "raw": raw or ""}
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"state": "corrupt", "raw": raw}
    if isinstance(payload, dict) and payload.get("v") == TICKET_VERSION:
        return {"state": "frozen", "ticket": payload}
    if isinstance(payload, dict) and isinstance(payload.get("deductions"), list):
        return {"state": "legacy", "ticket": _normalize_legacy(payload)}
    return {"state": "corrupt", "raw": raw}


def _normalize_legacy(p: dict) -> dict:
    """旧票规整为 v2 视图形状;快照与物品字段置 None(无快照),qty 仅由票内 take 合计。"""
    deductions = [
        {
            "lot_id": d.get("lot_id"),
            "expiry": d.get("expiry"),
            "take": d.get("take"),
            "remain_before": None,
            "remain_after": None,
        }
        for d in p["deductions"]
        if isinstance(d, dict)
    ]
    takes = [d["take"] for d in deductions if isinstance(d["take"], (int, float))]
    return {
        "v": None,
        "item_id": None,
        "item_name": None,
        "unit": None,
        "qty": sum(takes) if takes else None,
        "warn_days": None,
        "deductions": deductions,
    }
