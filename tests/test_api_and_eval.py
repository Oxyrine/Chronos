"""Router + eval integration on the mini St. Aster tree: scan -> classify -> exposures, end to end through the HTTP layer."""
import json
import time

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from chronos import eval_all
from chronos.api.routers import risk, scan as scan_router, shelflife as shelflife_router
from chronos.common import samples, store
from chronos.risk import mosca, service
from chronos.shelflife import model as M, serve
from chronos.shelflife.profile import profile_values
from data import gen_schemas
from data.semantics import SEMANTICS


def app():
    a = FastAPI()
    for r in (scan_router.router, shelflife_router.router, risk.router):
        a.include_router(r)
    return TestClient(a)


@pytest.fixture
def real_env(tmp_path, monkeypatch, demo_tree):
    root, _ = demo_tree
    topo = samples.sample("topology")
    (tmp_path / "topology.yaml").write_text(yaml.safe_dump(topo))
    monkeypatch.setenv("CHRONOS_USE_SAMPLES", "0")
    monkeypatch.setenv("CHRONOS_OUT", str(tmp_path / "out"))
    monkeypatch.setattr(store, "ROOT", tmp_path / "out")
    monkeypatch.setenv("CHRONOS_TOPOLOGY", str(tmp_path / "topology.yaml"))
    monkeypatch.setenv("CHRONOS_REPO", str(root))
    monkeypatch.setenv("CHRONOS_LIVE_PROBE", "0")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_sample_mode_serves_contract_shapes(monkeypatch):
    monkeypatch.setenv("CHRONOS_USE_SAMPLES", "1")
    c = app()
    samples.validate("finding", c.get("/findings").json()[0])
    samples.validate("shelflife_prediction", c.get("/shelflife").json()[0])
    samples.validate("exposure", c.get("/exposure").json()["exposures"][0])
    assert c.get("/priorities").json()[0]["priority"] == 94.0


def test_scan_then_exposure_through_http(real_env):
    c = app()
    sid = c.post("/scan").json()["scan_id"]
    for _ in range(100):
        st = c.get(f"/scan/{sid}").json()
        if st["status"] != "running":
            break
        time.sleep(0.1)
    assert st["status"] == "done", st
    assert c.get("/cbom").json()["specVersion"] == "1.6"
    assert {f["service"] for f in c.get("/findings", params={"status": "vulnerable"}).json()} >= {"portal", "ops-ssh"}
    # classify with fake predictions in the store (no DB here), then ask for exposures
    store.put("shelflife", [{"table": "patients", "column": "blood_group", "category": "clinical", "policy_years": 50},
                            {"table": "appointment_reminders", "column": "patient_id", "category": "pseudonymous_id", "policy_years": 10}])
    r = c.get("/exposure", params={"scenario": "base_2033"}).json()
    portal = [e for e in r["exposures"] if e["channel"] == "internet->portal" and e["store_table"] == "patients"]
    assert portal and portal[0]["exposed"] and portal[0]["margin"] == pytest.approx(43.25) and r["E"] > 0
    assert c.get("/exposure", params={"scenario": "nonsense"}).status_code == 422
    assert c.get("/exposure", params={"scenario": "custom_2031"}).status_code == 200
    ranked = c.get("/priorities").json()
    assert ranked == sorted(ranked, key=lambda f: -f["priority"])


def test_exposure_without_inputs_is_a_clear_409(real_env):
    r = app().get("/exposure")
    assert r.status_code == 409 and "scan" in r.json()["detail"]


def test_override_validates_and_is_logged(real_env):
    c = app()
    assert c.post("/shelflife/t/c/override", json={"category": "bogus"}).status_code == 422
    r = c.post("/shelflife/otp_codes/code/override", json={"category": "contact", "reason": "sent to phone"})
    assert r.status_code == 200 and r.json()["by"] == "secops"
    assert store.get("overrides")["otp_codes.code"]["category"] == "contact"
    assert (real_env / "out" / "overrides.jsonl").read_text().count("\n") == 1


# ---- serve path: SQL runner contract, with a fake database that answers from synthetic values ----
class FakeDb:
    """Answers the exact SQL profile.py emits, from synthetic values, so the serve path is exercised without Postgres."""
    def __init__(self):
        import random
        r = random.Random(1)
        self.tables = {"otp_codes": {"phone": "phone", "code": "otp_code", "expires_at": "expires_at"},
                       "genomics_results": {"patient_id": "person_id", "variant_hgvs": "variant"}}
        self.vals = {(t, c): [SEMANTICS[s][3](r) for _ in range(200)] for t, cols in self.tables.items() for c, s in cols.items()}

    def __call__(self, sql: str) -> str:
        if "information_schema.tables" in sql:
            return json.dumps(sorted(self.tables))
        if "information_schema.columns" in sql:
            t = sql.split("table_name = '")[1].split("'")[0]
            return json.dumps({"columns": [{"name": c, "type": "text"} for c in self.tables[t]], "row_count": 10000, "fk_tables": []})
        if "row_to_json(r)" in sql and "random() LIMIT" in sql:
            t, c = sql.split('FROM "')[1].split('"')[0], sql.split('SELECT "')[1].split('"')[0]
            return json.dumps(profile_values(self.vals[(t, c)]))
        raise AssertionError(sql[:80])


def test_serve_path_profiles_in_db_and_rolls_up():
    corpus = gen_schemas.generate(scale=0.25)
    mdl = M.CategoryModel().fit(corpus)
    preds = serve.classify_database(mdl, run=FakeDb())
    from chronos.risk.policy import rollup
    tx = rollup(preds)
    assert set(tx) == {"otp_codes", "genomics_results"}
    assert tx["otp_codes"]["x"] >= 10 and tx["otp_codes"]["driving_column"] != "code"  # a phone column outlives the 1-day code
    assert tx["genomics_results"]["x"] >= 50


def test_eval_exposure_before_after(real_env, monkeypatch):
    topo = samples.sample("topology")
    pred = [{"table": t, "column": "c", "category": "clinical", "policy_years": 50} for t in topo["tables"]]
    mk = lambda alg, st: [{**samples.sample("finding"), "finding_id": f"F-{i:04d}", "channels": [c["id"]], "algorithm": alg, "quantum_status": st,
                           "usage": "key_exchange", "fix_class": "config"} for i, c in enumerate(topo["channels"], 1)]
    for name, alg, st, q in [("before", "X25519", "vulnerable", 1.0), ("after", "X25519MLKEM768", "resistant", 0.3)]:
        d = real_env / "out" / "runs" / name
        d.mkdir(parents=True)
        (d / "findings.json").write_text(json.dumps(mk(alg, st)))
        (d / "shelflife.json").write_text(json.dumps(pred))
        (d / "client_mix.json").write_text(json.dumps({"mix": {"hybrid_capable": 70, "legacy": 30}, "q": {c["id"]: q for c in topo["channels"]}}))
    (real_env / "out" / "runs" / "before" / "nginx.log").write_text(json.dumps(
        {"request_uri": "/api/patients/1", "status": 200, "bytes_sent": 4920, "ssl_curve": "X25519"}) + "\n")
    out = eval_all.exposure()
    assert out["drop"] == pytest.approx(0.70) and out["targets_met"]
    assert out["R_before"]["patients"] == 10 and out["R_after"] == {}
    assert out["classical_routes_still_open"], "legacy clients keep a classical route open and the report must say so"
