"""Reviewable proposal endpoints; verification and approval are separate operations."""
from pathlib import Path
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from chronos.agent import propose
from chronos.api.deps import current_user
from chronos.common import samples, store

router = APIRouter(tags=["agent"])


class ProposalRequest(BaseModel):
    finding_id: str
    mode: str = "compatibility"


@router.post("/proposals")
def create_proposal(body: ProposalRequest, user: dict = Depends(current_user)):
    if samples.use_samples():
        return {"proposal": samples.load("patch_proposal", lambda: [])[0], "sample": True,
                "state": "sample", "diff": "", "note": "Sample evidence; cannot be verified or applied."}
    finding = next((f for f in store.get("findings", []) if f["finding_id"] == body.finding_id), None)
    if finding is None:
        raise HTTPException(404, "finding not found; run a scan first")
    try:
        return propose.create(finding, Path(os.environ.get("CHRONOS_REPO", propose.ROOT)), body.mode)
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/proposals")
def list_proposals():
    if samples.use_samples():
        return [{"proposal": p, "sample": True, "state": "sample", "diff": ""}
                for p in samples.load("patch_proposal", lambda: [])]
    return [propose.get_proposal(pid) for pid in store.get("proposals", [])]


@router.get("/proposals/{proposal_id}")
def read_proposal(proposal_id: str):
    if samples.use_samples():
        proposal = samples.load("patch_proposal", lambda: [])[0]
        if proposal["proposal_id"] != proposal_id:
            raise HTTPException(404, "sample proposal not found")
        return {"proposal": proposal, "sample": True, "state": "sample", "diff": ""}
    try:
        return propose.get_proposal(proposal_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
