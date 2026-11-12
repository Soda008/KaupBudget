"""Getting charges in from the bank.

Every source (CSV file now; Plaid / US Bank API later) produces plain dicts:
    {"date": "YYYY-MM-DD", "vendor": str, "amount": float (positive = spent), "ref": str}
and hands them to ingest(), which de-dupes and auto-suggests a category.
"""
from ..categorize import suggest
from ..vendors import vendor_key


def ingest(conn, rows: list[dict]) -> dict:
    imported = skipped = 0
    for r in rows:
        if conn.execute("SELECT 1 FROM transactions WHERE bank_ref = ?", (r["ref"],)).fetchone():
            skipped += 1
            continue
        top = suggest(conn, r["vendor"], n=1)
        # Only pre-fill when there's real history; it stays "unconfirmed" until you pick.
        cat = top[0]["id"] if top and top[0]["score"] >= 0.5 else None
        conn.execute(
            "INSERT INTO transactions (date, vendor, vendor_key, amount, category_id, category_confirmed, "
            "source, bank_ref, bank_date, bank_vendor, bank_amount) VALUES (?,?,?,?,?,0,'bank',?,?,?,?)",
            (r["date"], r["vendor"], vendor_key(r["vendor"]), r["amount"], cat,
             r["ref"], r["date"], r["vendor"], r["amount"]),
        )
        imported += 1
    return {"imported": imported, "skipped": skipped}
