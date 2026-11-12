"""Receipt image storage.

Local folder for now. Keys are relative paths, so the data folder can move.
An S3 backend for EC2 can be added later with the same three methods.
"""
from datetime import date
from pathlib import Path

from . import config


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)

    def save(self, receipt_id: int, data: bytes) -> str:
        today = date.today()
        key = f"{today:%Y}/{today:%m}/receipt_{receipt_id}.jpg"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("Bad image key")
        return p

    def load(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def delete(self, key: str) -> None:
        try:
            self.path(key).unlink()
        except FileNotFoundError:
            pass


storage = LocalStorage(config.RECEIPTS_DIR)
