"""Tiny JSON-file store under out/store. Each lane writes its latest result; routers and eval read it.

# ponytail: one JSON file per kind, no locking. Move to the SQLite file in chronos-api if two writers ever race.
"""
import json
import os
import pathlib

ROOT = pathlib.Path(os.environ.get("CHRONOS_OUT", pathlib.Path(__file__).resolve().parents[2] / "out"))


def path(kind: str) -> pathlib.Path:
    return ROOT / "store" / f"{kind}.json"


def put(kind: str, obj) -> None:
    p = path(kind)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(p)


def get(kind: str, default=None):
    p = path(kind)
    return json.loads(p.read_text()) if p.exists() else default
