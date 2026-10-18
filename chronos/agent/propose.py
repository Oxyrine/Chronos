"""Gate findings, constrain model decisions, and persist reviewable immutable patches."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import time

import jsonschema

from chronos.common import store
from . import llm_client
from .templates import T1, T2, T3, parameters
from .validator import eligible, read_target, sha256, validate_proposal, validate_stored

ROOT = Path(__file__).resolve().parents[2]
MODEL = "granite-3.3-2b-instruct-q8_0-be"


@contextmanager
def _lock():
    """Cross-process lock for the shared proposal index (API has multiple threads)."""
    lock = store.ROOT / ".proposal-lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 10
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                raise RuntimeError("proposal store is busy; retry")
            time.sleep(0.02)
    try:
        yield
    finally:
        lock.rmdir()


def decision(finding: dict, original: str, mode: str = "compatibility", llm=None) -> tuple[dict, str, str | None]:
    template, _ = eligible(finding)
    params = parameters(template, mode)
    rationale = {
        T1: "Enable hybrid ML-KEM key exchange. Classical clients remain accepted in compatibility mode; RSA certificate signatures remain unchanged.",
        T2: "Prefer hybrid SSH key exchange while retaining classical fallback for legacy clients. The RSA host signature remains unchanged.",
        T3: "Enable hybrid ML-KEM on this outbound TLS client. Certificate validation remains required; application RSA-OAEP is a separate remaining risk.",
    }[template]
    if mode == "strict":
        rationale = "Require TLS 1.3 hybrid ML-KEM key exchange and reject classical-only clients. RSA certificate signatures remain unchanged."
    result = {"template_id": template, "params": params, "rationale": rationale,
              "compatibility_risk": "high" if mode == "strict" else "low"}
    engine = os.environ.get("CHRONOS_AGENT_MODE", "rules")
    if engine not in ("rules", "granite", "rationale"):
        raise ValueError("CHRONOS_AGENT_MODE must be rules, granite or rationale")
    if engine == "rules" and llm is None:
        return result, "rules-only", None
    try:
        reply = llm(finding, original) if llm else llm_client.generate(finding, original, mode)
    except jsonschema.ValidationError as exc:
        raise ValueError("Granite response violates the constrained template schema") from exc
    except (OSError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        return result, "rules-only", f"Granite unavailable or invalid response ({type(exc).__name__})"
    try:
        jsonschema.validate(reply, llm_client.SCHEMA)
    except jsonschema.ValidationError as exc:
        raise ValueError("model response violates the constrained template schema") from exc
    if reply["template_id"] != template:
        raise ValueError("model selected a template that does not match the finding")
    if reply["params"] != params:
        raise ValueError("model parameters do not match the requested compatibility mode")
    if engine == "rationale":
        result["rationale"] = reply["rationale"]
        return result, "rules+" + MODEL + "-rationale", None
    return reply, MODEL, None


def create(finding: dict, root: Path | None = None, mode: str = "compatibility", llm=None) -> dict:
    root = Path(root or os.environ.get("CHRONOS_REPO", ROOT))
    _, target = eligible(finding)
    original = read_target(root, target)
    started = time.perf_counter()
    choice, model, fallback = decision(finding, original, mode, llm)
    with _lock():
        ids = store.get("proposals", [])
        number = max([int(p[2:]) for p in ids] + [0]) + 1
        if number > 9999:
            raise ValueError("proposal id space exhausted")
        pid = f"P-{number:04d}"
        proposal = {**choice, "proposal_id": pid, "finding_id": finding["finding_id"],
                    "requires_human": True, "model": model}
        rendered, diff = validate_proposal(proposal, finding, original)
        record = {"proposal": proposal, "target": target, "original_sha256": sha256(original),
                  "rendered": rendered, "diff": diff, "diff_sha256": sha256(diff),
                  "finding": finding, "state": "proposed", "latency_s": time.perf_counter() - started,
                  "fallback_reason": fallback,
                  "residual_risks": [
                      "Classical clients remain accepted in compatibility mode; use the measured client mix.",
                      "RSA certificate and SSH host signatures remain vulnerable to a future quantum adversary.",
                      "The portal-app to records-db link remains classical and is outside the modeled E channels.",
                      "The lab RSA-OAEP application encryption requires a separate code migration.",
                  ],
                  "attestation_scope": "A signature proves who attested to which evidence, not that the patch is secure in every respect."}
        validate_stored(record, root)
        store.put("proposal_" + pid, record)
        store.put("proposals", ids + [pid])
    return record


def get_proposal(proposal_id: str) -> dict:
    import re
    if not re.fullmatch(r"P-[0-9]{4}", proposal_id):
        raise LookupError("invalid proposal id")
    record = store.get("proposal_" + proposal_id)
    if record is None:
        raise LookupError("proposal not found")
    return record
