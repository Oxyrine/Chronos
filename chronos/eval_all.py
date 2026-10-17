"""Writes every spec 10.2 metric to out/metrics.json. The deck's metrics slide is built from that file only.

    python -m chronos.eval_all [--full]      (--full also re-runs leave-one-domain-out, ~3 min)

Inputs that belong to other lanes are optional; a missing one is recorded as pending, never invented:
  demo/ground_truth.yaml + demo/ + demo/topology.yaml              (Person A) -> discovery
  out/runs/{before,after}/{findings.json, shelflife.json, client_mix.json, nginx.log}   -> exposure E and R
"""
import datetime as dt
import json
import pathlib
import sys

import yaml

from chronos.common import samples
from chronos.discovery import evaluate, scan
from chronos.risk import service

OUT = pathlib.Path("out")


def discovery(repo=pathlib.Path(".")) -> dict:
    gt_path, topo_path = repo / "demo/ground_truth.yaml", repo / "demo/topology.yaml"
    if not (gt_path.exists() and topo_path.exists()):
        return {"status": "pending: demo/ground_truth.yaml or demo/topology.yaml not delivered by Lane 1"}
    gt = yaml.safe_load(gt_path.read_text())["assets"]
    roots = [repo / d for d in ("demo", "infra") if (repo / d).exists()]
    res = scan.run(roots, yaml.safe_load(topo_path.read_text()), base=repo)
    res_score = evaluate.score(res["findings"], gt)
    base = evaluate.score_loose(evaluate.grep_baseline(roots, repo), gt)
    return {**res_score, "scan_seconds": res["stats"]["scan_seconds"], "grep_baseline": base,
            "targets": {"recall": 0.90, "precision": 0.85, "scan_seconds": 60},
            "targets_met": res_score["recall"] >= 0.90 and res_score["precision"] >= 0.85 and res["stats"]["scan_seconds"] < 60}


def shelflife(full: bool) -> dict:
    p = OUT / "shelflife_metrics.json"
    if not p.exists():
        return {"status": "pending: run python -m chronos.shelflife.train"}
    m = json.loads(p.read_text())
    test = m.get("test", {})
    out = {"backend": m["backend"], "model_version": m["model_version"], "fixed_split": {k: {kk: vv for kk, vv in m[k].items() if kk != "confusion_matrix"} for k in ("validation", "test", "demo") if k in m},
           "heldout_confusion_matrix": test.get("confusion_matrix"),
           "targets": {"heldout_macro_f1": 0.80, "under_protection_rate": 0.05}}
    out["targets_met"] = bool(test) and test["macro_f1"] >= 0.80 and test["under_protection_rate"] < 0.05
    lodo = OUT / "shelflife_lodo.json"
    if full or not lodo.exists():
        if full:
            from chronos.shelflife.train import leave_one_domain_out
            lodo.write_text(json.dumps(leave_one_domain_out(), indent=1))
    if lodo.exists():
        out["leave_one_domain_out"] = json.loads(lodo.read_text())
    return out


def exposure() -> dict:
    runs = OUT / "runs"
    if not ((runs / "before").exists() and (runs / "after").exists()):
        return {"status": "pending: out/runs/before and out/runs/after (Lane 7 client-mix runs) not present"}
    topo = service.topology()
    res = {}
    for name in ("before", "after"):
        d = runs / name
        mix = json.loads((d / "client_mix.json").read_text()) if (d / "client_mix.json").exists() else {}
        log = d / "nginx.log"
        res[name] = service.compute(json.loads((d / "findings.json").read_text()), json.loads((d / "shelflife.json").read_text()), topo,
                                    mix.get("q"), log_path=log if log.exists() else None)
    e0, e1 = res["before"]["E"]["base_2033"], res["after"]["E"]["base_2033"]
    classical_open = sorted({(e["channel"], e["store_table"]) for e in res["after"]["exposures"]["base_2033"] if e["exposed"]})
    return {"E_before": e0, "E_after": e1, "drop": round(1 - e1 / e0, 4) if e0 else None, "target_drop": 0.70,
            "targets_met": bool(e0) and (1 - e1 / e0) >= 0.70, "client_mix": json.loads((runs / "after" / "client_mix.json").read_text()).get("mix") if (runs / "after" / "client_mix.json").exists() else None,
            "R_before": {t: v["R"] for t, v in res["before"]["already_sent"].items()}, "R_after": {t: v["R"] for t, v in res["after"]["already_sent"].items()},
            "classical_routes_still_open": [{"channel": c, "table": t} for c, t in classical_open],
            "note": "E is an index under the disclosed client mix, not a count of captured records."}


def main(full: bool = False) -> dict:
    m = {"synthetic": True, "measured_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "discovery": discovery(), "shelflife": shelflife(full), "exposure": exposure()}
    bench = OUT / "bench.json"
    m["performance"] = {"discovery_scan_seconds": m["discovery"].get("scan_seconds"),
                        "classify_ms_per_column": m["shelflife"].get("fixed_split", {}).get("test", {}).get("predict_ms_per_column"),
                        "anomaly_and_stream": json.loads(bench.read_text()) if bench.exists() else "pending (P1)"}
    samples.validate("metrics", m)
    OUT.mkdir(exist_ok=True)
    (OUT / "metrics.json").write_text(json.dumps(m, indent=2))
    return m


if __name__ == "__main__":
    print(json.dumps(main("--full" in sys.argv), indent=2)[:3000])
