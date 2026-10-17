"""GET /exposure?scenario=, GET /priorities?scenario=. Recomputes per request (milliseconds): the slider stays live."""
from fastapi import APIRouter, HTTPException, Query

from chronos.common import samples
from chronos.risk import mosca, service

router = APIRouter(tags=["risk"])
SCENARIO_RX = r"^(early_2030|base_2033|late_2035|custom_[0-9]{4})$"


def _compute(scenario: str) -> dict:
    try:
        return service.latest([scenario])
    except LookupError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/exposure")
def exposure(scenario: str = Query("base_2033", pattern=SCENARIO_RX)):
    if samples.use_samples():
        return {"scenario": scenario, "exposures": [samples.sample("exposure")], "E": 0.0, "already_sent": {}, "client_mix_measured": False}
    out = _compute(scenario)
    rows = out["exposures"][scenario]
    return {"scenario": scenario, "exposures": rows, "E": out["E"][scenario], "already_sent": out["already_sent"],
            "client_mix_measured": out["client_mix_measured"],
            "note": "E is an index under the disclosed client mix, not a count of captured records; already_sent cannot be undone by a fix."}


@router.get("/priorities")
def priorities(scenario: str = Query("base_2033", pattern=SCENARIO_RX)):
    if samples.use_samples():
        return [{**samples.sample("finding"), "priority": 94.0}]
    return _compute(scenario)["ranked_findings"]
