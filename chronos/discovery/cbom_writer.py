"""Findings -> CycloneDX 1.6 CBOM (spec 8.1), validated offline against the vendored schema."""
import datetime as dt
import hashlib
import json
import pathlib
import uuid

import referencing
from jsonschema import Draft7Validator
from referencing.jsonschema import DRAFT7

VENDOR = pathlib.Path(__file__).resolve().parents[2] / "contracts" / "vendor"
PRIMITIVE = {"key_exchange": "key-agree", "signature": "signature", "hash": "hash", "symmetric": "block-cipher", "encryption": "pke"}
MATERIAL = {"private-key", "public-key"}


def _algorithm_props(f: dict) -> dict:
    p = f["params"]
    alg = f["algorithm"].upper()
    primitive = "pke" if alg.startswith("RSA") and f["usage"] in ("key_exchange", "encryption") else PRIMITIVE.get(f["usage"], "other")
    out = {"primitive": primitive, "executionEnvironment": "software-plain-ram", "implementationPlatform": "s390x",
           "nistQuantumSecurityLevel": 0 if f["quantum_status"] == "vulnerable" else 1}
    if p.get("key_bits"):
        out["parameterSetIdentifier"] = str(p["key_bits"])
    if p.get("curve"):
        out["curve"] = str(p["curve"])
    return out


def component(f: dict) -> dict:
    t = f["asset_type"]
    props: dict = {"assetType": t}
    p = f["params"]
    if t == "algorithm":
        props["algorithmProperties"] = _algorithm_props(f)
    elif t == "protocol":
        props["protocolProperties"] = {"type": p.get("protocol") if p.get("protocol") in ("tls", "ssh") else "other",
                                       **({"version": p["versions"][0]} if p.get("versions") else {})}
    elif t == "certificate":
        props["certificateProperties"] = {k: v for k, v in {
            "subjectName": p.get("subject"), "issuerName": p.get("issuer"), "notValidBefore": p.get("not_before"),
            "notValidAfter": p.get("not_after"), "certificateFormat": p.get("certificate_format")}.items() if v}
    else:
        props["relatedCryptoMaterialProperties"] = {"type": p.get("material", "other") if p.get("material") in MATERIAL else "other",
                                                    **({"size": p["key_bits"]} if p.get("key_bits") else {})}
    name = f["algorithm"] + (f"-{p['key_bits']}" if p.get("key_bits") and f["asset_type"] != "protocol" else "")
    occ = {"location": f["location"]["path"], **({"line": f["location"]["line"]} if f["location"].get("line") else {})}
    return {
        "type": "cryptographic-asset", "bom-ref": f["bom_ref"], "name": name, "cryptoProperties": props,
        "evidence": {"occurrences": [occ]},
        "properties": [
            {"name": "chronos:finding_id", "value": f["finding_id"]},
            {"name": "chronos:quantum_status", "value": f["quantum_status"]},
            {"name": "chronos:classical_weak", "value": str(f["classical_weak"]).lower()},
            {"name": "chronos:sources", "value": ",".join(f["sources"])},
            {"name": "chronos:method", "value": f.get("method", "deterministic")},
        ],
    }


def build(findings: list[dict], now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    comps = {}
    for f in findings:
        comps.setdefault(f["bom_ref"], component(f))  # bom-ref must be unique
    return {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'chronos/' + hashlib.sha256(json.dumps(sorted(comps)).encode()).hexdigest())}",
        "metadata": {"timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "tools": {"components": [{"type": "application", "name": "chronos", "version": "0.1.0"}]}},
        "components": list(comps.values()),
    }


def validate(cbom: dict) -> None:
    """Raises jsonschema.ValidationError if the CBOM is not valid CycloneDX 1.6."""
    reg = referencing.Registry()
    for p in VENDOR.glob("*.json"):
        doc = json.loads(p.read_text())
        res = referencing.Resource.from_contents(doc, default_specification=DRAFT7)
        reg = reg.with_resource(p.name, res)
        if doc.get("$id"):
            reg = reg.with_resource(doc["$id"], res)
    schema = json.loads((VENDOR / "bom-1.6.schema.json").read_text())
    Draft7Validator(schema, registry=reg).validate(cbom)
