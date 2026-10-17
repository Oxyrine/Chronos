"""Quantum status lookup (spec 9.1) driven by catalog.yaml. Shared by discovery and the risk engine."""
import functools
import pathlib
import re

import yaml

_HERE = pathlib.Path(__file__).parent


@functools.lru_cache(maxsize=1)
def _catalog():
    raw = yaml.safe_load((_HERE / "catalog.yaml").read_text())
    rules = [(re.compile(r["match"], re.I), r["status"]) for r in raw["rules"]]
    weak = [re.compile(p, re.I) for p in raw["classical_weak"]]
    return rules, weak


def classify(algorithm: str, params: dict | None = None) -> tuple[str, bool]:
    """Return (quantum_status, classical_weak). Unknown algorithms are treated as vulnerable (conservative)."""
    params = params or {}
    name = algorithm.strip().lower()
    rules, weak = _catalog()
    status = next((st for rx, st in rules if rx.search(name)), "vulnerable")
    bits = params.get("key_bits")
    if name.startswith("aes") and bits == 128:
        status = "weakened"
    classical_weak = any(rx.search(name) for rx in weak)
    if name.startswith("rsa") and isinstance(bits, int) and bits < 2048:
        classical_weak = True
    return status, classical_weak


def kex_class(group: str) -> str:
    """Key-exchange class of a negotiated TLS group / SSH KEX name: classical | hybrid | pq."""
    g = group.strip().lower()
    if g in ("0x11ec", "0x11eb", "0x11ed"):  # codepoints nginx may print instead of names
        return "hybrid"
    if re.search(r"mlkem|ml-kem|sntrup|kyber", g):
        has_classical = re.search(r"x25519|x448|secp|ecdh|curve25519|p256|p384", g)
        return "hybrid" if has_classical else "pq"
    return "classical"
