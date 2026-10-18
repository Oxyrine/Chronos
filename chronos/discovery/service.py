"""The shared scan operation used by the API and post-approval attestation."""
import json
import os
from pathlib import Path

from chronos.common import store
from chronos.discovery import cbom_writer, scan
from chronos.risk.service import topology


def rescan() -> dict:
    base = Path(os.environ.get("CHRONOS_REPO", ".")).resolve()
    roots = [base / d for d in os.environ.get("CHRONOS_SCAN_DIRS", "demo,infra").split(",") if (base / d).exists()]
    probe = None
    if os.environ.get("CHRONOS_LIVE_PROBE", "1") == "1":
        probe = scan.live_probe.http_runner if os.environ.get("CHRONOS_PROBE_URL") else scan.live_probe.shell_runner
    result = scan.run(roots, topology(), base=base, probe=probe, use_llm=os.environ.get("CHRONOS_LLM_ASSIST") == "1")
    cbom_writer.validate(result["cbom"])
    store.put("findings", result["findings"])
    store.put("cbom", result["cbom"])
    store.ROOT.mkdir(parents=True, exist_ok=True)
    target = store.ROOT / "cbom.json"
    target.write_text(json.dumps(result["cbom"], indent=2))
    return result
