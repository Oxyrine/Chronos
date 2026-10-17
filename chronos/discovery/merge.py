"""Merge raw scanner assets into de-duplicated Findings (spec 7.2 merge rule, 8.2 shape)."""
import re

from chronos.discovery.common import service_of
from chronos.risk.catalog import classify


def norm_alg(a: str) -> str:
    return re.sub(r"[^a-z0-9]", "", a.lower())


def key_of(a: dict):
    """Same certificate fingerprint, or same (path, line, algorithm), is one asset."""
    return ("fp", a["fingerprint"], a["path"]) if a.get("fingerprint") else ("loc", a["path"], a["line"], norm_alg(a["algorithm"]))


def merge(raw: list[dict]) -> list[dict]:
    merged: dict = {}
    for a in raw:
        k = key_of(a)
        if k not in merged:
            merged[k] = {**a, "sources": list(a["sources"])}
            continue
        m = merged[k]
        m["sources"] += [s for s in a["sources"] if s not in m["sources"]]
        m["confidence"] = max(m["confidence"], a["confidence"])
        if a["method"] == "deterministic":
            m["method"] = "deterministic"
        m["params"] = {**a["params"], **m["params"]}
    return list(merged.values())


def channels_for(asset: dict, topology: dict) -> list[str]:
    """Channels this asset sits on: live probes name theirs; others match by owning service and protocol."""
    if ch := asset["params"].get("channel"):
        return [ch]
    svc, proto = service_of(asset["path"]), asset["params"].get("protocol")
    out = []
    for c in topology["channels"]:
        if proto in ("ssh", "tls") and c["protocol"] != proto:
            continue
        if c["dst"] == svc or c["src"] == svc:
            out.append(c["id"])
    return out


def to_findings(merged: list[dict], topology: dict) -> list[dict]:
    findings = []
    for i, a in enumerate(sorted(merged, key=lambda a: (a["path"], a["line"] or 0, a["algorithm"])), 1):
        status, weak = classify(a["algorithm"], a["params"])
        if a.get("status"):
            status = a["status"]
        findings.append({
            "finding_id": f"F-{i:04d}",
            "bom_ref": f"crypto/{norm_alg(a['algorithm'])}/{a['path']}" + (f":{a['line']}" if a["line"] else ""),
            "asset_type": a["asset_type"], "usage": a["usage"], "algorithm": a["algorithm"], "params": a["params"],
            "quantum_status": status, "classical_weak": weak, "service": service_of(a["path"]),
            "channels": channels_for(a, topology), "location": {"path": a["path"], **({"line": a["line"]} if a["line"] else {})},
            "fix_class": a["fix_class"], "sources": a["sources"], "confidence": a["confidence"],
            "method": a["method"], "fingerprint": a.get("fingerprint"),
        })
    return findings
