"""SQLite storage. One file, no server needed (works locally and on EC2)."""
import sqlite3
from contextlib import contextmanager

from . import config

DEFAULT_CATEGORIES = [
    "Groceries",
    "Eating Out",
    "Gas & Auto",
    "Shopping",
    "Bills & Utilities",
    "Health",
    "Entertainment",
    "Other",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    archived  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
    id                 INTEGER PRIMARY KEY,
    date               TEXT NOT NULL,          -- YYYY-MM-DD
    vendor             TEXT NOT NULL,
    vendor_key         TEXT NOT NULL,          -- normalized, for learning/matching
    amount             REAL NOT NULL,          -- positive = money spent
    category_id        INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    category_confirmed INTEGER NOT NULL DEFAULT 0,  -- 1 = you picked it (feeds learning)
    source             TEXT NOT NULL DEFAULT 'manual', -- bank | receipt | manual
    bank_ref           TEXT UNIQUE,            -- de-dupes bank imports
    bank_date          TEXT,
    bank_vendor        TEXT,
    bank_amount        REAL,
    notes              TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_tx_date   ON transactions(date);
CREATE INDEX IF NOT EXISTS ix_tx_vendor ON transactions(vendor_key);

CREATE TABLE IF NOT EXISTS receipts (
    id                 INTEGER PRIMARY KEY,
    transaction_id     INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    image_key          TEXT NOT NULL,          -- path relative to the receipts folder
    original_name      TEXT,
    status             TEXT NOT NULL DEFAULT 'pending',  -- pending | saved
    vendor             TEXT,
    date               TEXT,
    subtotal           REAL,
    tax                REAL,
    tip                REAL,
    total              REAL,
    items_json         TEXT,
    suggested_category TEXT,
    extractor          TEXT,
    extract_error      TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_receipt_tx ON receipts(transaction_id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as c:
        c.execute("PRAGMA journal_mode = WAL")
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            c.executemany("INSERT INTO categories(name) VALUES (?)", [(n,) for n in DEFAULT_CATEGORIES])


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row and row["value"] is not None else default


def set_setting(conn, key, value) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
