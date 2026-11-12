"""Find the bank charge a receipt belongs to."""
from datetime import date

from .vendors import similarity

DATE_WINDOW_DAYS = 7  # bank charges can post a few days after purchase


def _amount_score(receipt_total, receipt_tip, charge) -> float:
    if receipt_total is None or charge is None:
        return 0.0
    diff = abs(charge - receipt_total)
    if diff < 0.01:
        return 1.0
    # Card authorized before the tip was added
    if receipt_tip and abs(charge - (receipt_total - receipt_tip)) < 0.01:
        return 0.8
    if receipt_total > 0 and diff / receipt_total <= 0.25:
        return 0.4 * (1 - diff / receipt_total / 0.25)
    return 0.0


def find_matches(conn, receipt_date, total, vendor, tip=None, include_id=None, limit=5) -> list:
    """Unreceipted transactions that look like this receipt, best first."""
    try:
        d = date.fromisoformat(receipt_date) if receipt_date else None
    except ValueError:
        d = None

    params = []
    where = "NOT EXISTS (SELECT 1 FROM receipts r WHERE r.transaction_id = t.id AND r.status = 'saved')"
    if d:
        where += " AND julianday(t.date) BETWEEN julianday(?) - ? AND julianday(?) + ?"
        params += [d.isoformat(), DATE_WINDOW_DAYS, d.isoformat(), DATE_WINDOW_DAYS]
    rows = conn.execute(
        f"SELECT t.*, c.name AS category FROM transactions t LEFT JOIN categories c ON c.id = t.category_id "
        f"WHERE ({where}) OR t.id = ? ORDER BY t.date DESC LIMIT 200",
        params + [include_id or -1],
    ).fetchall()

    out = []
    for t in rows:
        charge = t["bank_amount"] if t["bank_amount"] is not None else t["amount"]
        a = _amount_score(total, tip, charge)
        v = similarity(vendor or "", t["bank_vendor"] or t["vendor"])
        if d:
            try:
                days = abs((date.fromisoformat(t["bank_date"] or t["date"]) - d).days)
            except ValueError:
                days = DATE_WINDOW_DAYS
            ds = max(0.0, 1 - days / (DATE_WINDOW_DAYS + 1))
        else:
            ds = 0.3
        score = 0.5 * a + 0.3 * v + 0.2 * ds
        if t["id"] == include_id:
            score = max(score, 0.99)
        if score >= 0.35:
            out.append({
                "id": t["id"], "date": t["date"], "vendor": t["vendor"], "amount": t["amount"],
                "category": t["category"], "source": t["source"], "score": round(score, 2),
            })
    out.sort(key=lambda m: m["score"], reverse=True)
    return out[:limit]
