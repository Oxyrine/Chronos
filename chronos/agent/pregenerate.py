"""Pre-generate proposals right after a scan (spec section 15 fallback for a slow Granite).

Every vulnerable key-exchange finding on a templatable file gets one proposal, so the demo's
Remediation screen never waits on the model. Findings that already have a proposal are skipped.
The report records which engine actually produced each proposal; a Granite timeout falls back
to rules and is reported as such, never relabelled.

Run (inside chronos-api, llm profile up):
  CHRONOS_AGENT_MODE=granite python -m chronos.agent.pregenerate
"""
import argparse
import json
import os
from pathlib import Path
import statistics

from chronos.common import store
from . import llm_client, propose
from .validator import eligible


def existing_findings() -> set[str]:
    return {(store.get("proposal_" + pid) or {}).get("proposal", {}).get("finding_id")
            for pid in store.get("proposals", [])}


def run(root: Path, mode: str = "compatibility", warm: bool = True) -> dict:
    engine = os.environ.get("CHRONOS_AGENT_MODE", "rules")
    warm_s = None
    if warm and engine != "rules":
        try:
            warm_s = llm_client.warm()
        except (OSError, TimeoutError) as exc:
            warm_s = f"warm-up failed ({type(exc).__name__})"
    done, rows = existing_findings(), []
    for finding in store.get("findings", []):
        try:
            eligible(finding)
        except ValueError:
            continue
        if finding["finding_id"] in done:
            rows.append({"finding_id": finding["finding_id"], "skipped": "proposal exists"})
            continue
        try:
            record = propose.create(finding, root, mode)
            rows.append({"finding_id": finding["finding_id"], "proposal_id": record["proposal"]["proposal_id"],
                         "template_id": record["proposal"]["template_id"], "model": record["proposal"]["model"],
                         "fallback_reason": record["fallback_reason"], "latency_s": round(record["latency_s"], 3)})
        except (ValueError, LookupError) as exc:
            rows.append({"finding_id": finding["finding_id"], "error": str(exc).splitlines()[0]})
    created = [r for r in rows if "proposal_id" in r]
    latencies = sorted(r["latency_s"] for r in created)
    return {"engine": engine, "mode": mode, "warm_s": warm_s, "created": len(created),
            "granite": sum(r["model"] != "rules-only" for r in created),
            "fallbacks": sum(r["fallback_reason"] is not None for r in created),
            "latency_s": {"p50": statistics.median(latencies), "max": latencies[-1]} if latencies else None,
            "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("CHRONOS_REPO", propose.ROOT)))
    parser.add_argument("--mode", choices=["compatibility", "strict"], default="compatibility")
    parser.add_argument("--no-warm", action="store_true")
    args = parser.parse_args()
    report = run(args.root, args.mode, not args.no_warm)
    store.put("pregenerate_report", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
