"""Glue for the API and eval: latest findings + predictions + topology (+ measured client mix, nginx log) -> exposures."""
import os
import pathlib
import glob

import yaml

from chronos.common import store
from chronos.risk import harvestable, mosca
from chronos.risk.policy import rollup


def topology() -> dict:
    return yaml.safe_load(pathlib.Path(os.environ.get("CHRONOS_TOPOLOGY", "demo/topology.yaml")).read_text())


def already_sent(topo: dict, exposed_tables: set[str], log_path=None) -> dict:
    """R per table from the nginx chronos log: transfers already made over classical sessions (a fix cannot undo these)."""
    log_path = log_path or os.environ.get("CHRONOS_NGINX_LOG")
    paths = [pathlib.Path(p) for p in glob.glob(str(log_path))] if log_path else []
    if not paths:
        return {}
    means = {t: v.get("mean_record_bytes", 500) for t, v in topo["tables"].items()}
    lines = [line for path in sorted(paths) for line in path.read_text().splitlines()]
    return harvestable.transfers(lines, means, margin_positive=exposed_tables)


def compute(findings: list[dict], predictions: list[dict], topo: dict, client_q: dict | None = None,
            scenarios: list[str] | None = None, log_path=None) -> dict:
    out = mosca.run_all(topo, rollup(predictions), findings, client_q, scenarios)
    base = out["exposures"].get(mosca.BASE) or next(iter(out["exposures"].values()))
    out["already_sent"] = already_sent(topo, {e["store_table"] for e in base if e["margin"] > 0}, log_path)
    out["client_mix_measured"] = bool(client_q)
    return out


def latest(scenarios=None) -> dict:
    """Raises LookupError when the scan or the classification has not run: zero exposure must never mean 'not measured'."""
    findings, preds = store.get("findings"), store.get("shelflife")
    if not findings:
        raise LookupError("no findings: POST /scan first")
    if not preds:
        raise LookupError("no shelf-life predictions: POST /shelflife/run first")
    mix = store.get("client_mix") or {}
    return compute(findings, preds, topology(), mix.get("q"), scenarios)
