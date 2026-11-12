"""KaupBudget web server: the JSON API plus the app's pages."""
import base64
import json
import secrets
from datetime import date
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, config, db, reports
from .bank import ingest
from .bank.csv_import import CsvError, parse as parse_csv
from .categorize import suggest
from .extractors import PROVIDERS, current_provider, extract_receipt, has_key
from .images import ACCEPTED, ImageError, to_jpeg
from .matching import find_matches
from .storage import storage
from .vendors import vendor_key

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 25 * 1024 * 1024

app = FastAPI(title="KaupBudget", version=__version__)


@app.on_event("startup")
def _startup():
    db.init_db()


# ---------- Optional password (turn on with KAUP_PASSWORD, e.g. on EC2) ----------
@app.middleware("http")
async def _auth(request: Request, call_next):
    if config.PASSWORD:
        ok = False
        header = request.headers.get("authorization", "")
        if header.lower().startswith("basic "):
            try:
                _, _, pw = base64.b64decode(header[6:]).decode().partition(":")
                ok = secrets.compare_digest(pw, config.PASSWORD)
            except Exception:  # noqa: BLE001
                ok = False
        if not ok:
            return Response("Password required", status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="KaupBudget"'})
    return await call_next(request)


# ---------- Helpers ----------
def _category_names(conn):
    return [r["name"] for r in conn.execute("SELECT name FROM categories WHERE archived = 0 ORDER BY id")]


def _tx_row(conn, tx_id):
    row = conn.execute(
        "SELECT t.*, c.name AS category, "
        "(SELECT r.id FROM receipts r WHERE r.transaction_id = t.id AND r.status = 'saved' "
        " ORDER BY r.id DESC LIMIT 1) AS receipt_id "
        "FROM transactions t LEFT JOIN categories c ON c.id = t.category_id WHERE t.id = ?",
        (tx_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Purchase not found")
    return dict(row)


def _receipt(conn, rid):
    row = conn.execute("SELECT * FROM receipts WHERE id = ?", (rid,)).fetchone()
    if not row:
        raise HTTPException(404, "Receipt not found")
    r = dict(row)
    r["items"] = json.loads(r.pop("items_json") or "[]")
    return r


def _valid_date(s):
    try:
        return date.fromisoformat(s).isoformat()
    except (TypeError, ValueError):
        raise HTTPException(400, "Date must be YYYY-MM-DD")


def _category_id(conn, value):
    if value in (None, ""):
        return None
    if not conn.execute("SELECT 1 FROM categories WHERE id = ?", (int(value),)).fetchone():
        raise HTTPException(400, "Unknown category")
    return int(value)


# ---------- Categories ----------
@app.get("/api/categories")
def list_categories():
    with db.get_conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM categories ORDER BY id")]


@app.post("/api/categories")
def add_category(name: str = Body(..., embed=True)):
    name = name.strip()
    if not name:
        raise HTTPException(400, "Name required")
    with db.get_conn() as c:
        try:
            cur = c.execute("INSERT INTO categories(name) VALUES (?)", (name,))
        except Exception:
            raise HTTPException(400, "That category already exists")
        return {"id": cur.lastrowid, "name": name, "archived": 0}


@app.patch("/api/categories/{cid}")
def edit_category(cid: int, data: dict = Body(...)):
    with db.get_conn() as c:
        if "name" in data and data["name"].strip():
            c.execute("UPDATE categories SET name = ? WHERE id = ?", (data["name"].strip(), cid))
        if "archived" in data:
            c.execute("UPDATE categories SET archived = ? WHERE id = ?", (1 if data["archived"] else 0, cid))
        return dict(c.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone())


# ---------- Transactions ----------
@app.get("/api/transactions")
def list_transactions(month: str | None = None, category_id: str | None = None, q: str | None = None,
                      missing_receipt: bool = False):
    where, args = [], []
    if month:
        where.append("substr(t.date, 1, 7) = ?")
        args.append(month)
    if category_id == "none":
        where.append("t.category_id IS NULL")
    elif category_id:
        where.append("t.category_id = ?")
        args.append(int(category_id))
    if q:
        where.append("(t.vendor LIKE ? OR t.notes LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    sql = (
        "SELECT t.*, c.name AS category, "
        "(SELECT r.id FROM receipts r WHERE r.transaction_id = t.id AND r.status = 'saved' "
        " ORDER BY r.id DESC LIMIT 1) AS receipt_id "
        "FROM transactions t LEFT JOIN categories c ON c.id = t.category_id"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY t.date DESC, t.id DESC LIMIT 2000"
    with db.get_conn() as c:
        rows = [dict(r) for r in c.execute(sql, args)]
    if missing_receipt:
        rows = [r for r in rows if not r["receipt_id"]]
    return rows


@app.post("/api/transactions")
def add_transaction(data: dict = Body(...)):
    vendor = (data.get("vendor") or "").strip()
    if not vendor:
        raise HTTPException(400, "Vendor required")
    with db.get_conn() as c:
        cid = _category_id(c, data.get("category_id"))
        cur = c.execute(
            "INSERT INTO transactions (date, vendor, vendor_key, amount, category_id, category_confirmed, source, notes) "
            "VALUES (?,?,?,?,?,?,'manual',?)",
            (_valid_date(data.get("date")), vendor, vendor_key(vendor), float(data.get("amount") or 0),
             cid, 1 if cid else 0, data.get("notes")),
        )
        return _tx_row(c, cur.lastrowid)


@app.get("/api/transactions/{tx_id}")
def get_transaction(tx_id: int):
    with db.get_conn() as c:
        tx = _tx_row(c, tx_id)
        tx["receipt"] = _receipt(c, tx["receipt_id"]) if tx["receipt_id"] else None
        items = tx["receipt"]["items"] if tx["receipt"] else None
        tx["suggestions"] = suggest(c, tx["vendor"], items)
        return tx


@app.patch("/api/transactions/{tx_id}")
def edit_transaction(tx_id: int, data: dict = Body(...)):
    with db.get_conn() as c:
        _tx_row(c, tx_id)
        sets, args = [], []
        if "vendor" in data and data["vendor"].strip():
            sets += ["vendor = ?", "vendor_key = ?"]
            args += [data["vendor"].strip(), vendor_key(data["vendor"])]
        if "date" in data:
            sets.append("date = ?")
            args.append(_valid_date(data["date"]))
        if "amount" in data:
            sets.append("amount = ?")
            args.append(float(data["amount"]))
        if "notes" in data:
            sets.append("notes = ?")
            args.append(data["notes"])
        if "category_id" in data:
            cid = _category_id(c, data["category_id"])
            sets += ["category_id = ?", "category_confirmed = ?"]
            args += [cid, 1 if cid else 0]
        if sets:
            c.execute(f"UPDATE transactions SET {', '.join(sets)} WHERE id = ?", args + [tx_id])
        return _tx_row(c, tx_id)


@app.delete("/api/transactions/{tx_id}")
def delete_transaction(tx_id: int):
    with db.get_conn() as c:
        for r in c.execute("SELECT id, image_key FROM receipts WHERE transaction_id = ?", (tx_id,)).fetchall():
            storage.delete(r["image_key"])
            c.execute("DELETE FROM receipts WHERE id = ?", (r["id"],))
        c.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    return {"ok": True}


@app.get("/api/months")
def months_with_data():
    with db.get_conn() as c:
        return [r[0] for r in c.execute(
            "SELECT DISTINCT substr(date, 1, 7) m FROM transactions ORDER BY m DESC")]


# ---------- Receipts ----------
def _review_payload(c, rid, transaction_id=None):
    r = _receipt(c, rid)
    return {
        "receipt": r,
        "suggestions": suggest(c, r["vendor"] or "", r["items"], r["suggested_category"]),
        "matches": find_matches(c, r["date"], r["total"], r["vendor"], r["tip"], include_id=transaction_id),
    }


@app.post("/api/receipts/upload")
def upload_receipt(file: UploadFile = File(...), transaction_id: int | None = Query(None)):
    name = file.filename or "receipt"
    if Path(name).suffix.lower() not in ACCEPTED:
        raise HTTPException(400, "Use a PDF, JPEG, PNG or WebP file.")
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(400, "File is too big (25 MB max).")
    try:
        jpeg = to_jpeg(data, name)
    except ImageError as e:
        raise HTTPException(400, str(e))

    with db.get_conn() as c:
        cur = c.execute("INSERT INTO receipts (image_key, original_name) VALUES ('', ?)", (name,))
        rid = cur.lastrowid
        c.execute("UPDATE receipts SET image_key = ? WHERE id = ?", (storage.save(rid, jpeg), rid))
        cats = _category_names(c)

    # The AI call can take a few seconds; don't hold the database open for it.
    with db.get_conn() as c:
        info, provider, error = extract_receipt(c, jpeg, cats)
        c.execute(
            "UPDATE receipts SET vendor=?, date=?, subtotal=?, tax=?, tip=?, total=?, items_json=?, "
            "suggested_category=?, extractor=?, extract_error=? WHERE id = ?",
            (info["vendor"], info["date"], info["subtotal"], info["tax"], info["tip"], info["total"],
             json.dumps(info["items"]), info["suggested_category"], provider, error, rid),
        )
        return _review_payload(c, rid, transaction_id)


@app.post("/api/receipts/{rid}/reread")
def reread_receipt(rid: int, transaction_id: int | None = Query(None)):
    with db.get_conn() as c:
        r = _receipt(c, rid)
        info, provider, error = extract_receipt(c, storage.load(r["image_key"]), _category_names(c))
        c.execute(
            "UPDATE receipts SET vendor=?, date=?, subtotal=?, tax=?, tip=?, total=?, items_json=?, "
            "suggested_category=?, extractor=?, extract_error=? WHERE id = ?",
            (info["vendor"], info["date"], info["subtotal"], info["tax"], info["tip"], info["total"],
             json.dumps(info["items"]), info["suggested_category"], provider, error, rid),
        )
        return _review_payload(c, rid, transaction_id)


@app.get("/api/receipts/{rid}/review")
def review_receipt(rid: int, vendor: str | None = None, date_: str | None = Query(None, alias="date"),
                   total: float | None = None, tip: float | None = None, transaction_id: int | None = None):
    """Refresh suggestions/matches after you edit fields in the review form."""
    with db.get_conn() as c:
        r = _receipt(c, rid)
        v = vendor if vendor is not None else r["vendor"] or ""
        return {
            "suggestions": suggest(c, v, r["items"], r["suggested_category"]),
            "matches": find_matches(c, date_ or r["date"], total if total is not None else r["total"], v,
                                    tip if tip is not None else r["tip"], include_id=transaction_id),
        }


@app.post("/api/receipts/{rid}/save")
def save_receipt(rid: int, data: dict = Body(...)):
    """Confirm a receipt: link it to a bank charge (receipt details win) or create a new purchase."""
    vendor = (data.get("vendor") or "").strip()
    if not vendor:
        raise HTTPException(400, "Vendor required")
    try:
        total = round(float(data.get("total")), 2)
    except (TypeError, ValueError):
        raise HTTPException(400, "Total required")
    d = _valid_date(data.get("date"))

    def num(k):
        try:
            return round(float(data[k]), 2) if data.get(k) not in (None, "") else None
        except (TypeError, ValueError):
            return None

    with db.get_conn() as c:
        _receipt(c, rid)
        cid = _category_id(c, data.get("category_id"))
        tx_id = data.get("transaction_id")
        if tx_id:
            _tx_row(c, int(tx_id))
            # Detach any older saved receipt from this purchase (one receipt per purchase).
            c.execute("UPDATE receipts SET transaction_id = NULL WHERE transaction_id = ? AND id != ?",
                      (int(tx_id), rid))
            c.execute(
                "UPDATE transactions SET vendor=?, vendor_key=?, date=?, amount=?, category_id=?, "
                "category_confirmed=? WHERE id = ?",
                (vendor, vendor_key(vendor), d, total, cid, 1 if cid else 0, int(tx_id)),
            )
        else:
            tx_id = c.execute(
                "INSERT INTO transactions (date, vendor, vendor_key, amount, category_id, category_confirmed, source) "
                "VALUES (?,?,?,?,?,?,'receipt')",
                (d, vendor, vendor_key(vendor), total, cid, 1 if cid else 0),
            ).lastrowid
        c.execute(
            "UPDATE receipts SET status='saved', transaction_id=?, vendor=?, date=?, total=?, "
            "subtotal=?, tax=?, tip=? WHERE id = ?",
            (int(tx_id), vendor, d, total, num("subtotal"), num("tax"), num("tip"), rid),
        )
        return _tx_row(c, int(tx_id))


@app.get("/api/receipts/{rid}/image")
def receipt_image(rid: int):
    with db.get_conn() as c:
        r = _receipt(c, rid)
    path = storage.path(r["image_key"])
    if not path.exists():
        raise HTTPException(404, "Image file is missing")
    return FileResponse(path, media_type="image/jpeg")


@app.delete("/api/receipts/{rid}")
def delete_receipt(rid: int):
    with db.get_conn() as c:
        r = _receipt(c, rid)
        storage.delete(r["image_key"])
        c.execute("DELETE FROM receipts WHERE id = ?", (rid,))
    return {"ok": True}


# ---------- Bank import ----------
@app.post("/api/import/csv")
def import_csv(file: UploadFile = File(...)):
    try:
        rows = parse_csv(file.file.read(MAX_UPLOAD))
    except CsvError as e:
        raise HTTPException(400, str(e))
    with db.get_conn() as c:
        return ingest(c, rows)


# ---------- Reports ----------
@app.get("/api/reports/monthly")
def report_monthly(months: int = Query(12, ge=1, le=60), end: str | None = None):
    with db.get_conn() as c:
        return reports.monthly(c, months, end)


@app.get("/api/reports/category/{cid}")
def report_category(cid: str, months: int = Query(12, ge=1, le=60), end: str | None = None):
    with db.get_conn() as c:
        return reports.category_review(c, None if cid == "none" else int(cid), months, end)


# ---------- Settings ----------
SETTING_KEYS = {"provider", "claude_model", "gemini_model", "ollama_model", "ollama_url",
                "claude_api_key", "gemini_api_key"}
SECRET_KEYS = {"claude_api_key", "gemini_api_key"}


@app.get("/api/settings")
def get_settings():
    with db.get_conn() as c:
        out = {k: db.get_setting(c, k) for k in SETTING_KEYS - SECRET_KEYS}
        out["provider"] = current_provider(c)
        out["providers"] = [{**p, "has_key": has_key(c, p["id"])} for p in PROVIDERS]
        out["data_dir"] = str(config.DATA_DIR)
        out["password_on"] = bool(config.PASSWORD)
        out["version"] = __version__
        return out


@app.put("/api/settings")
def put_settings(data: dict = Body(...)):
    with db.get_conn() as c:
        for k, v in data.items():
            if k not in SETTING_KEYS:
                continue
            if k in SECRET_KEYS and not v:
                continue  # blank field = keep the saved key
            db.set_setting(c, k, (v or "").strip() or None)
    return get_settings()


@app.delete("/api/settings/{key}")
def clear_setting(key: str):
    if key not in SECRET_KEYS:
        raise HTTPException(400, "Can't clear that")
    with db.get_conn() as c:
        db.set_setting(c, key, None)
    return get_settings()


# ---------- Pages ----------
@app.exception_handler(ValueError)
def _value_error(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
