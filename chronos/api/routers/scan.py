"""POST /scan, GET /scan/{id}, GET /cbom, GET /findings. Mount with app.include_router(router)."""
import threading
import uuid

from fastapi import APIRouter, HTTPException

from chronos.common import samples, store
from chronos.discovery.service import rescan

router = APIRouter(tags=["discovery"])
_SCANS: dict[str, dict] = {}


def _run(scan_id: str) -> None:
    try:
        res = rescan()
        _SCANS[scan_id] = {"scan_id": scan_id, "status": "done", **res["stats"]}
    except Exception as e:  # surface to the poller instead of dying silently in the thread
        _SCANS[scan_id] = {"scan_id": scan_id, "status": "failed", "error": str(e)}


@router.post("/scan")
def start_scan():
    sid = f"S-{uuid.uuid4().hex[:8]}"
    if samples.use_samples():
        _SCANS[sid] = {"scan_id": sid, "status": "done", "findings": 1, "raw_assets": 1, "scan_seconds": 0.0}
        return {"scan_id": sid}
    _SCANS[sid] = {"scan_id": sid, "status": "running"}
    threading.Thread(target=_run, args=(sid,), daemon=True).start()
    return {"scan_id": sid}


@router.get("/scan/{scan_id}")
def scan_status(scan_id: str):
    if scan_id not in _SCANS:
        raise HTTPException(404, "unknown scan")
    return _SCANS[scan_id]


@router.get("/cbom")
def cbom():
    if samples.use_samples():
        return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1, "components": [samples.sample("cbom_component")]}
    c = store.get("cbom")
    if c is None:
        raise HTTPException(404, "no scan has run yet")
    return c


@router.get("/findings")
def findings(status: str | None = None, service: str | None = None):
    rows = samples.load("finding", lambda: store.get("findings", []))
    return [f for f in rows if (not status or f["quantum_status"] == status) and (not service or f["service"] == service)]
