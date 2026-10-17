"""Mosca risk engine (spec 7.4, 9.2-9.4). Pure functions, in-memory, deterministic.

M = X + Y - Z; exposed = M > 0 and some share q of sessions still negotiates a classical key exchange.
M > 0 means migration is urgent under that scenario, not that any record was captured.
"""
import math

from chronos.risk.catalog import kex_class

SCENARIOS = {"early_2030": 4, "base_2033": 7, "late_2035": 9}  # years from 2026; planning scenarios, not predictions
BASE = "base_2033"
Y_YEARS = {"config": 0.25, "library": 0.5, "code_change": 1, "vendor": 3, "hardware": 5}
REACH = {"internet": 1.0, "partner": 0.8, "internal": 0.4}
CURRENT_YEAR = 2026
_KEX_RANK = {"classical": 0, "hybrid": 1, "pq": 2}


def z_years(scenario: str) -> int:
    if scenario in SCENARIOS:
        return SCENARIOS[scenario]
    if scenario.startswith("custom_"):
        return int(scenario.split("_", 1)[1]) - CURRENT_YEAR
    raise ValueError(f"unknown scenario {scenario!r}")


def margin(x: float, y: float, z: float) -> float:
    return round(x + y - z, 4)


def channel_states(topology: dict, findings: list[dict], client_q: dict | None = None) -> dict:
    """Per channel: weakest key-exchange class, fix class of the finding keeping it classical, share q.

    Weakest wins. With several classical findings on one channel the largest Y is used: the channel
    stays classical until all of them are fixed. A channel with no key-exchange finding is treated as
    classical (conservative: a gap in discovery must not read as safety).
    """
    client_q = client_q or {}
    out = {}
    for ch in topology["channels"]:
        cid = ch["id"]
        kex_findings = [f for f in findings if cid in f.get("channels", []) and f["usage"] == "key_exchange"]
        classical = [f for f in kex_findings if f["quantum_status"] == "vulnerable"]
        driving = max(classical, key=lambda f: Y_YEARS[f["fix_class"]]) if classical else None
        classes = ["classical" if f["quantum_status"] == "vulnerable" else kex_class(f["algorithm"]) for f in kex_findings]
        kex = min(classes or ["classical"], key=_KEX_RANK.get)
        q = client_q[cid] if cid in client_q else (1.0 if kex == "classical" else 0.0)
        out[cid] = {
            "kex_class": kex,
            "fix_class": driving["fix_class"] if driving else "config",
            "driving_finding": driving["finding_id"] if driving else None,
            "q": q,
            "reach": ch["reach"],
        }
    return out


def compute_exposures(topology: dict, table_x: dict, states: dict, scenario: str) -> list[dict]:
    """One Exposure (spec 8.4) per (channel, table) for a scenario. table_x: {table: {"x": years, "driving_column": col}}."""
    z = z_years(scenario)
    rows = []
    for ch in topology["channels"]:
        st = states[ch["id"]]
        y = Y_YEARS[st["fix_class"]]
        for t in ch["tables"]:
            if t not in table_x:
                continue
            x = table_x[t]["x"]
            m = margin(x, y, z)
            rows.append({
                "channel": ch["id"], "store_table": t, "scenario": scenario,
                "x_years": x, "y_years": y, "z_years": z, "margin": m,
                "exposed": m > 0 and st["q"] > 0,
                "kex_class": st["kex_class"], "classical_share": st["q"],
                "records": topology["tables"][t]["records"],
                "priority": 0.0, "driving_finding": st["driving_finding"] or "",
                "driving_column": table_x[t].get("driving_column"),
            })
    return rows


def exposure_index(exposures: list[dict], scope: set[str] | None = None) -> float:
    """E_s = sum_t records(t) * max over channels carrying t with M>0 of q_c. Each table counts once, at its worst channel."""
    worst: dict[str, tuple[int, float]] = {}
    for e in exposures:
        if scope is not None and e["channel"] not in scope:
            continue
        if e["margin"] > 0:
            rec, q = worst.get(e["store_table"], (e["records"], 0.0))
            worst[e["store_table"]] = (rec, max(q, e["classical_share"]))
    return round(sum(rec * q for rec, q in worst.values()), 2)


def priorities(topology: dict, findings: list[dict], by_scenario: dict[str, list[dict]]) -> dict[str, float]:
    """Priority 0-100 per finding (spec 9.3). Ties broken by the caller via sort_key (lower Y first)."""
    max_records = max(t["records"] for t in topology["tables"].values())
    reach_of = {c["id"]: c["reach"] for c in topology["channels"]}
    out = {}
    for f in findings:
        scen_hit = 0
        base_m, rec, reach = 0.0, 0, 0.0
        for scen, rows in by_scenario.items():
            hit = [r for r in rows if r["driving_finding"] == f["finding_id"] and r["exposed"]]
            if hit:
                scen_hit += 1
            if scen == BASE and hit:
                base_m = max(r["margin"] for r in hit)
                rec = max(r["records"] for r in hit)
                reach = max(REACH[reach_of[r["channel"]]] for r in hit)
        m = min(base_m / 20, 1.0) if base_m > 0 else 0.0
        v = math.log10(rec + 1) / math.log10(max_records + 1) if rec else 0.0
        r_share = scen_hit / max(len(by_scenario), 1)
        out[f["finding_id"]] = round(100 * (0.45 * m + 0.25 * v + 0.20 * reach + 0.10 * r_share), 1)
    return out


def sort_key(finding: dict, prio: dict[str, float]):
    return (-prio.get(finding["finding_id"], 0.0), Y_YEARS[finding["fix_class"]])


def run_all(topology: dict, table_x: dict, findings: list[dict], client_q: dict | None = None,
            scenarios: list[str] | None = None) -> dict:
    """Everything the dashboard needs in one pass: exposures x scenarios, priorities, ranked findings, E per scenario."""
    scenarios = scenarios or list(SCENARIOS)
    states = channel_states(topology, findings, client_q)
    by_scen = {s: compute_exposures(topology, table_x, states, s) for s in scenarios}
    prio = priorities(topology, findings, by_scen)
    for rows in by_scen.values():
        for r in rows:
            r["priority"] = prio.get(r["driving_finding"], 0.0)
    ranked = sorted(findings, key=lambda f: sort_key(f, prio))
    return {
        "exposures": by_scen,
        "priorities": prio,
        "ranked_findings": [{**f, "priority": prio[f["finding_id"]]} for f in ranked],
        "E": {s: exposure_index(rows) for s, rows in by_scen.items()},
        "states": states,
    }
