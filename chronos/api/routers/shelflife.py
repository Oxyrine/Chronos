"""POST /shelflife/run, GET /shelflife, POST /shelflife/{table}/{column}/override."""
import datetime as dt
import json
import pathlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from chronos.api.deps import current_user
from chronos.common import samples, store
from chronos.risk.policy import load_policy
from chronos.shelflife import model as M, serve

router = APIRouter(tags=["shelflife"])


class Override(BaseModel):
    category: str
    reason: str = ""


@router.post("/shelflife/run")
def run():
    if samples.use_samples():
        return {"job_id": "J-sample", "columns": 1}
    preds = serve.classify_database(M.CategoryModel.load(), overrides=store.get("overrides", {}))
    store.put("shelflife", preds)
    return {"job_id": f"J-{dt.datetime.now(dt.timezone.utc):%H%M%S}", "columns": len(preds)}


@router.get("/shelflife")
def shelflife():
    return samples.load("shelflife_prediction", lambda: store.get("shelflife", []))


@router.post("/shelflife/{table}/{column}/override")
def override(table: str, column: str, body: Override, user: dict = Depends(current_user)):
    """A human correction. Logged to out/overrides.jsonl (the attested ledger entry is the API shell's job)."""
    if body.category not in load_policy()["categories"]:
        raise HTTPException(422, "unknown category")
    ov = store.get("overrides", {})
    ov[f"{table}.{column}"] = {"category": body.category, "by": user["sub"], "reason": body.reason}
    store.put("overrides", ov)
    with open(pathlib.Path(store.ROOT) / "overrides.jsonl", "a") as f:
        f.write(json.dumps({"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "table": table, "column": column, **ov[f"{table}.{column}"]}) + "\n")
    return ov[f"{table}.{column}"]
