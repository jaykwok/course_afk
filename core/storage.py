"""Atomic files and serialized in-process read/modify/write transactions."""
from __future__ import annotations

from functools import wraps
import json
import os
from pathlib import Path
import tempfile
import threading

_transaction_lock = threading.RLock()


def serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _transaction_lock:
            return function(*args, **kwargs)
    return wrapped


def write_bytes_atomic(path: Path, content: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_text_atomic(path, content: str, *, encoding: str = "utf-8") -> None:
    write_bytes_atomic(Path(path), content.encode(encoding))


def write_json_atomic(path, value) -> None:
    write_text_atomic(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
