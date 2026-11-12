"""Import charges from a bank CSV export (US Bank and most others)."""
import csv
import hashlib
import io
from collections import Counter
from datetime import datetime

DATE_COLS = ("date", "transaction date", "posted date", "posting date", "trans. date")
DESC_COLS = ("name", "description", "payee", "merchant", "transaction description")
MEMO_COLS = ("memo", "details")
AMOUNT_COLS = ("amount", "transaction amount")
DEBIT_COLS = ("debit", "withdrawal", "withdrawals")


class CsvError(ValueError):
    pass


def _pick(headers, options):
    low = {h.lower().strip(): h for h in headers if h}
    for o in options:
        if o in low:
            return low[o]
    return None


def _date(s):
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _num(s):
    s = (s or "").strip().replace("$", "").replace(",", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def parse(data: bytes) -> list[dict]:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    dcol, ncol, mcol = _pick(headers, DATE_COLS), _pick(headers, DESC_COLS), _pick(headers, MEMO_COLS)
    acol, debcol = _pick(headers, AMOUNT_COLS), _pick(headers, DEBIT_COLS)
    if not dcol or not ncol or not (acol or debcol):
        raise CsvError(f"Couldn't find date / description / amount columns. Found: {', '.join(headers)}")

    raw = []
    for row in reader:
        d = _date(row.get(dcol))
        if not d:
            continue
        if debcol and _num(row.get(debcol)):
            amt = -abs(_num(row.get(debcol)))
        else:
            amt = _num(row.get(acol)) if acol else None
        if amt is None:
            continue
        raw.append((d, (row.get(ncol) or "").strip(), amt, (row.get(mcol) or "").strip() if mcol else ""))

    # Most banks (US Bank included) show spending as negative. If nothing is negative,
    # assume the file lists spending as positive numbers.
    spend_negative = any(a < 0 for _, _, a, _ in raw)
    seen = Counter()
    out = []
    for d, name, amt, memo in raw:
        spent = -amt if spend_negative else amt
        if spent <= 0:
            continue  # deposits, refunds, payments to the card
        base = f"{d}|{name}|{amt:.2f}|{memo}"
        seen[base] += 1  # identical rows on the same day stay distinct
        ref = "csv:" + hashlib.sha1(f"{base}|{seen[base]}".encode()).hexdigest()[:20]
        out.append({"date": d, "vendor": name or memo or "Unknown", "amount": round(spent, 2), "ref": ref})
    return out
