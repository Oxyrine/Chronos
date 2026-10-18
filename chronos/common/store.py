"""Tiny JSON-file store under out/store. Each lane writes its latest result; routers and eval read it.

# ponytail: one JSON file per kind, no locking. Move to the SQLite file in chronos-api if two writers ever race.
"""
import json
import os
import pathlib
import tempfile
import threading

_WRITE_LOCK = threading.RLock()

ROOT = pathlib.Path(os.environ.get("CHRONOS_OUT", pathlib.Path(__file__).resolve().parents[2] / "out"))


def path(kind: str) -> pathlib.Path:
    return ROOT / "store" / f"{kind}.json"


def put(kind: str, obj) -> None:
    p = path(kind)
    p.parent.mkdir(parents=True, exist_ok=True)
    # API scans and worker rescans can finish together. Each writer needs its
    # own temporary file; replacement still publishes one complete JSON value.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=p.parent,
                                     prefix=p.name + ".", suffix=".tmp", delete=False) as handle:
        tmp = pathlib.Path(handle.name)
        json.dump(obj, handle, indent=1)
    # These shared synthetic demo artifacts must also be readable by Person B's
    # host-side evaluator. Secrets live in .env/keys, never in this store.
    tmp.chmod(0o644)
    try:
        with _WRITE_LOCK:
            tmp.replace(p)
    finally:
        tmp.unlink(missing_ok=True)


def get(kind: str, default=None):
    p = path(kind)
    return json.loads(p.read_text()) if p.exists() else default
