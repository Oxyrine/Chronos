"""R: record transfers over classical sessions during a measured run (spec 9.4).

Counts transfers, not distinct records: the same record delivered twice counts twice. Requests rejected
(non-2xx, e.g. strict mode refusing a legacy client) count zero. Reads the nginx `chronos` JSON log.
"""
import json

from chronos.risk.catalog import kex_class

DEFAULT_ROUTES = [  # longest prefix wins
    ("/api/patients", "patients"), ("/api/records", "encounters"), ("/api/encounters", "encounters"),
    ("/api/genomics", "genomics_results"), ("/api/labs", "lab_results"), ("/api/reminders", "appointment_reminders"),
]


def store_for(uri: str, routes=DEFAULT_ROUTES) -> str | None:
    hits = [(len(p), s) for p, s in routes if uri.startswith(p)]
    return max(hits)[1] if hits else None


def transfers(log_lines, mean_record_bytes: dict, routes=DEFAULT_ROUTES, margin_positive: set | None = None) -> dict:
    """Per table: {"R": record transfers on classical sessions, "classical_route_open": bool, "sessions": {class: n}}."""
    out: dict[str, dict] = {}
    for line in log_lines:
        line = line.strip()
        if not line:
            continue
        ev = json.loads(line)
        table = store_for(ev.get("request_uri", ev.get("uri", "")), routes)
        if table is None:
            continue
        cls = kex_class(str(ev.get("ssl_curve", ev.get("group", ""))))
        row = out.setdefault(table, {"R": 0, "classical_route_open": False, "sessions": {"classical": 0, "hybrid": 0, "pq": 0}})
        ok = 200 <= int(ev.get("status", 0)) < 300
        row["sessions"][cls] += 1
        if cls == "classical" and ok:
            row["classical_route_open"] = True
            if margin_positive is None or table in margin_positive:
                row["R"] += int(int(ev.get("bytes_sent", ev.get("bytes", 0))) / mean_record_bytes[table])
    return out
