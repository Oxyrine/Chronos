"""Meta endpoints for metrics and verified run statistics."""
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response

from chronos.common import samples

router = APIRouter(tags=["meta"])


@router.get("/metrics")
def get_metrics():
    """Serves the latest measured benchmark and accuracy metrics."""
    out_dir = Path(os.environ.get("CHRONOS_OUT", "out"))
    metrics_path = out_dir / "metrics.json"
    
    if metrics_path.exists():
        try:
            data = json.loads(metrics_path.read_text(encoding="utf-8"))
            return Response(
                content=json.dumps(data),
                media_type="application/json",
                headers={"Cache-Control": "no-store"}
            )
        except Exception as exc:
            raise HTTPException(500, f"failed to read metrics: {exc}") from exc

    if samples.use_samples():
        return samples.sample("metrics")

    raise HTTPException(404, "metrics have not been generated yet")
