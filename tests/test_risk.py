import json
import time

import pytest

from chronos.common import samples
from chronos.risk import catalog, harvestable, mosca
from chronos.risk.policy import rollup

# (X, Y, Z, expected margin, expected exposed given q>0): hand-worked
CASES = [
    (50, 0.25, 7, 43.25, True),    # patients, config fix, base
    (10, 0.25, 7, 3.25, True),     # otp_codes via phone
    (1, 0.25, 7, -5.75, False),    # scheduling expires first
    (0.003, 0.25, 4, -3.747, False),
    (75, 1, 9, 67, True),          # genomics, code change, late
    (10, 0.25, 9, 1.25, True),     # barely exposed in late scenario
    (8, 0.25, 9, -0.75, False),    # barely safe
    (10, 3, 9, 4, True),           # vendor fix
    (1, 5, 4, 2, True),            # hardware fix makes even a 1y table urgent
    (0, 0.25, 7, -6.75, False),
]


@pytest.mark.parametrize("x,y,z,m,exposed", CASES)
def test_margin_rule(x, y, z, m, exposed):
    got = mosca.margin(x, y, z)
    assert got == pytest.approx(m)
    assert (got > 0) == exposed


def test_scenarios_and_custom_year():
    assert [mosca.z_years(s) for s in ("early_2030", "base_2033", "late_2035")] == [4, 7, 9]
    assert mosca.z_years("custom_2040") == 14
    with pytest.raises(ValueError):
        mosca.z_years("tomorrow")


def finding(fid, channels, fix="config", alg="X25519", status="vulnerable", usage="key_exchange"):
    return {**samples.sample("finding"), "finding_id": fid, "channels": channels, "fix_class": fix,
            "algorithm": alg, "quantum_status": status, "usage": usage}


@pytest.fixture
def world():
    topo = samples.sample("topology")
    preds = [  # patients: blood_group clinical drives 50y; reminders: patient_id pseudonymous drives 10y
        {"table": "patients", "column": "full_name", "category": "identity", "policy_years": 30},
        {"table": "patients", "column": "blood_group", "category": "clinical", "policy_years": 50},
        {"table": "appointment_reminders", "column": "sms_text", "category": "scheduling", "policy_years": 1},
        {"table": "appointment_reminders", "column": "patient_id", "category": "pseudonymous_id", "policy_years": 10},
        {"table": "encounters", "column": "diagnosis_icd10", "category": "clinical", "policy_years": 50},
        {"table": "genomics_results", "column": "variant_hgvs", "category": "genetic", "policy_years": 75},
        {"table": "lab_results", "column": "value", "category": "clinical", "policy_years": 50},
    ]
    findings = [finding("F-0001", ["internet->portal"]), finding("F-0002", ["internet->reminders"]),
                finding("F-0003", ["lab-api->partner-lab"]), finding("F-0004", ["clinician->ops-ssh"], alg="curve25519-sha256")]
    return topo, rollup(preds), findings


def test_patients_over_portal_exposed_in_all_scenarios(world):
    topo, tx, findings = world
    out = mosca.run_all(topo, tx, findings)
    for scen, rows in out["exposures"].items():
        r = next(r for r in rows if r["channel"] == "internet->portal" and r["store_table"] == "patients")
        assert r["exposed"], scen
    base = next(r for r in out["exposures"]["base_2033"] if r["channel"] == "internet->portal" and r["store_table"] == "patients")
    assert base["margin"] == pytest.approx(43.25) and base["x_years"] == 50 and base["driving_column"] == "blood_group"


def test_portal_outranks_reminders_twin(world):
    topo, tx, findings = world
    out = mosca.run_all(topo, tx, findings)
    p = out["priorities"]
    assert p["F-0001"] > p["F-0002"] + 20  # same crypto, different data, very different urgency
    assert [f["finding_id"] for f in out["ranked_findings"]].index("F-0001") < [f["finding_id"] for f in out["ranked_findings"]].index("F-0002")


def test_otp_codes_exposed_via_phone_not_code():
    preds = [{"table": "otp_codes", "column": "phone", "category": "contact", "policy_years": 10},
             {"table": "otp_codes", "column": "code", "category": "auth_secret", "policy_years": 0.003}]
    tx = rollup(preds)
    assert tx["otp_codes"]["x"] == 10 and tx["otp_codes"]["driving_column"] == "phone"
    topo = {"channels": [{"id": "internet->portal", "src": "internet", "dst": "portal", "protocol": "tls", "reach": "internet", "tables": ["otp_codes"]}],
            "tables": {"otp_codes": {"records": 10000}}}
    out = mosca.run_all(topo, tx, [finding("F-0001", ["internet->portal"])])
    base = out["exposures"]["base_2033"][0]
    assert base["exposed"] and base["margin"] == pytest.approx(3.25) and base["driving_column"] == "phone"


def test_hybrid_channel_with_q_zero_not_exposed(world):
    topo, tx, findings = world
    fixed = [finding("F-0001", ["internet->portal"], alg="X25519MLKEM768", status="resistant")] + findings[1:]
    out = mosca.run_all(topo, tx, fixed, client_q={"internet->portal": 0.0})
    row = next(r for r in out["exposures"]["base_2033"] if r["channel"] == "internet->portal" and r["store_table"] == "patients")
    assert row["kex_class"] == "hybrid" and not row["exposed"]


def test_E_drops_after_fix_with_disclosed_mix(world):
    topo, tx, findings = world
    before = mosca.run_all(topo, tx, findings)["E"]["base_2033"]
    fixed = [finding("F-0001", ["internet->portal"], alg="X25519MLKEM768", status="resistant"),
             finding("F-0002", ["internet->reminders"], alg="X25519MLKEM768", status="resistant")] + findings[2:]
    after = mosca.run_all(topo, tx, fixed, client_q={"internet->portal": 0.30, "internet->reminders": 0.30})["E"]["base_2033"]
    assert after < before
    # patients (50k) at q=0.3 plus untouched channels; the portal tables must contribute 0.3x not 1x
    assert mosca.exposure_index(mosca.run_all(topo, tx, fixed, client_q={"internet->portal": 0.30})["exposures"]["base_2033"],
                                scope={"internet->portal"}) == pytest.approx(0.3 * (50000 + 200000 + 60000))


def test_E_counts_each_table_once_at_worst_channel(world):
    topo, tx, findings = world
    rows = mosca.run_all(topo, tx, findings)["exposures"]["base_2033"]
    e = mosca.exposure_index(rows)
    tables = {r["store_table"]: r["records"] for r in rows if r["exposed"]}
    assert e == pytest.approx(sum(tables.values()))  # q=1 everywhere, each table once


def test_recompute_under_500ms(world):
    topo, tx, findings = world
    t = time.perf_counter()
    mosca.run_all(topo, tx, findings)
    assert time.perf_counter() - t < 0.5


def test_catalog():
    assert catalog.classify("RSA-OAEP", {"key_bits": 2048}) == ("vulnerable", False)
    assert catalog.classify("RSA", {"key_bits": 1024}) == ("vulnerable", True)
    assert catalog.classify("X25519MLKEM768")[0] == "resistant"
    assert catalog.classify("X25519")[0] == "vulnerable"
    assert catalog.classify("ECDSA")[0] == "vulnerable"
    assert catalog.classify("AES", {"key_bits": 128})[0] == "weakened"
    assert catalog.classify("AES-256")[0] == "resistant"
    assert catalog.classify("SHA-1") == ("resistant", True)
    assert catalog.classify("AES/ECB/PKCS5Padding")[1] is True
    assert catalog.kex_class("X25519MLKEM768") == "hybrid" and catalog.kex_class("0x11ec") == "hybrid"
    assert catalog.kex_class("mlkem768x25519-sha256") == "hybrid" and catalog.kex_class("secp256r1") == "classical"


def test_R_counts_transfers_on_classical_2xx_only():
    lines = [json.dumps(e) for e in [
        {"request_uri": "/api/patients/1", "status": 200, "bytes_sent": 4920, "ssl_curve": "X25519"},       # 10 records
        {"request_uri": "/api/patients/1", "status": 200, "bytes_sent": 4920, "ssl_curve": "X25519"},       # same again: counts twice
        {"request_uri": "/api/patients/2", "status": 200, "bytes_sent": 4920, "ssl_curve": "X25519MLKEM768"},  # hybrid
        {"request_uri": "/api/patients/3", "status": 421, "bytes_sent": 100, "ssl_curve": "X25519"},         # rejected
    ]]
    r = harvestable.transfers(lines, {"patients": 492})["patients"]
    assert r["R"] == 20 and r["classical_route_open"] and r["sessions"] == {"classical": 3, "hybrid": 1, "pq": 0}
