import json
import re


def _blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def _norm(name):
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def main(input):
    records = json.loads(input.get("records_json") or "[]") or []
    seen = set()
    groups = {}
    total = 0
    for r in records:
        rid = r.get("Record ID") or r.get("transaction_id")
        if rid in seen:
            continue
        # (a) no receipt yet: matched is false and exempt is not true
        missing_receipt = (r.get("matched") is False) and (r.get("exempt") is not True)
        # (b) any blank coding field (exempt rows included)
        missing = [f for f in ("project_code", "cost_code", "reason") if _blank(r.get(f))]
        if not missing_receipt and not missing:
            continue
        seen.add(rid)  # de-duplicate rows qualifying under (a) and (b)
        parts = (["receipt"] if missing_receipt else []) + missing
        item = {
            "record_id": r.get("Record ID"),
            "transaction_id": r.get("transaction_id"),
            "cardholder_name": (r.get("cardholder_name") or "").strip(),
            "transaction_date": str(r.get("transaction_date") or ""),
            "merchant": r.get("merchant") or "",
            "amount": "" if r.get("amount") is None else str(r.get("amount")),
            "missing_receipt": missing_receipt,
            "missing_fields": ", ".join(missing),
            "missing_summary": ", ".join(parts),
            "previously_sent": r.get("sent_in_package") is True,
        }
        key = _norm(r.get("cardholder_name"))
        g = groups.setdefault(key, {
            "normalized_name": key,
            "cardholder_name": re.sub(r"\s+", " ", item["cardholder_name"]),
            "items": [],
        })
        g["items"].append(item)
        total += 1
    out = []
    for g in groups.values():
        g["item_count"] = len(g["items"])
        out.append(g)
    return {"open_item_count": total, "group_count": len(out), "groups": out}
