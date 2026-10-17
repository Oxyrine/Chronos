"""Contract helpers: validate against contracts/*.schema.json, and the CHRONOS_USE_SAMPLES switch."""
import json
import os
import pathlib

import jsonschema

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"


def use_samples() -> bool:
    return os.environ.get("CHRONOS_USE_SAMPLES", "1") == "1"


def sample(kind: str):
    return json.loads((CONTRACTS / "samples" / f"{kind}.json").read_text())


def schema(kind: str) -> dict:
    return json.loads((CONTRACTS / f"{kind}.schema.json").read_text())


def validate(kind: str, obj) -> None:
    jsonschema.validate(obj, schema(kind))


def load(kind: str, producer):
    """Samples while CHRONOS_USE_SAMPLES=1, else the real producer. Routers call only this."""
    return [sample(kind)] if use_samples() else producer()
