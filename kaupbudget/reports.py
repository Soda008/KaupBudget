"""Monthly category breakdowns and per-category reviews."""
from datetime import date


def _last_months(n: int, end: str | None = None) -> list[str]:
    if end:
        y, m = map(int, end.split("-"))
    else:
        t = date.today()
        y, m = t.year, t.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def monthly(conn, months: int = 12, end: str | None = None) -> dict:
    ms = _last_months(months, end)
    rows = conn.execute(
        "SELECT substr(t.date, 1, 7) AS month, t.category_id, SUM(t.amount) AS total, COUNT(*) AS n "
        "FROM transactions t WHERE substr(t.date, 1, 7) BETWEEN ? AND ? GROUP BY month, t.category_id",
        (ms[0], ms[-1]),
    ).fetchall()
    cats = conn.execute("SELECT id, name FROM categories ORDER BY id").fetchall()
    idx = {m: i for i, m in enumerate(ms)}
    series = {c["id"]: {"id": c["id"], "name": c["name"], "totals": [0.0] * len(ms)} for c in cats}
    uncategorized = {"id": None, "name": "Uncategorized", "totals": [0.0] * len(ms)}
    for r in rows:
        s = series.get(r["category_id"], uncategorized)
        s["totals"][idx[r["month"]]] = round(s["totals"][idx[r["month"]]] + r["total"], 2)
    out = [s for s in series.values() if any(s["totals"])]
    if any(uncategorized["totals"]):
        out.append(uncategorized)
    month_totals = [round(sum(s["totals"][i] for s in out), 2) for i in range(len(ms))]
    return {"months": ms, "categories": out, "month_totals": month_totals}


def category_review(conn, category_id: int | None, months: int = 12, end: str | None = None) -> dict:
    ms = _last_months(months, end)
    cat_clause = "t.category_id = ?" if category_id is not None else "t.category_id IS NULL"
    cat_args = (category_id,) if category_id is not None else ()
    base = f"FROM transactions t WHERE {cat_clause} AND substr(t.date, 1, 7) BETWEEN ? AND ?"
    args = cat_args + (ms[0], ms[-1])

    by_month = {r["month"]: r for r in conn.execute(
        f"SELECT substr(t.date, 1, 7) AS month, SUM(t.amount) AS total, COUNT(*) AS n {base} GROUP BY month", args)}
    totals = [round(by_month[m]["total"], 2) if m in by_month else 0.0 for m in ms]
    counts = [by_month[m]["n"] if m in by_month else 0 for m in ms]

    vendors = [dict(r) for r in conn.execute(
        f"SELECT t.vendor_key, MIN(t.vendor) AS vendor, SUM(t.amount) AS total, COUNT(*) AS n {base} "
        "GROUP BY t.vendor_key ORDER BY total DESC LIMIT 8", args)]
    missing = conn.execute(
        f"SELECT COUNT(*) {base} AND NOT EXISTS (SELECT 1 FROM receipts r "
        "WHERE r.transaction_id = t.id AND r.status = 'saved')", args).fetchone()[0]

    active = [t for t in totals[:-1] if t]  # finished months with spending
    avg = round(sum(active) / len(active), 2) if active else 0.0
    current = totals[-1]
    name = "Uncategorized"
    if category_id is not None:
        row = conn.execute("SELECT name FROM categories WHERE id = ?", (category_id,)).fetchone()
        name = row["name"] if row else "?"
    return {
        "id": category_id, "name": name, "months": ms, "totals": totals, "counts": counts,
        "average": avg, "current": current,
        "vs_average_pct": round((current - avg) / avg * 100, 1) if avg else None,
        "range_total": round(sum(totals), 2), "top_vendors": vendors, "missing_receipts": missing,
    }
