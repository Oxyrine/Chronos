"""Configuration safety and real store/router behavior; no live model is needed."""
from concurrent.futures import ThreadPoolExecutor
import copy
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from chronos.agent import eval as agent_eval, llm_client, propose, templates, validator
from chronos.api.routers import agent
from chronos.common import samples, store


@pytest.fixture
def agent_env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "out")
    monkeypatch.setenv("CHRONOS_REPO", str(tmp_path))
    monkeypatch.setenv("CHRONOS_USE_SAMPLES", "0")
    monkeypatch.setenv("CHRONOS_AGENT_MODE", "rules")
    for case in agent_eval.cases()[:4]:
        p = tmp_path / case["finding"]["location"]["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(case["original"].encode())
    return tmp_path


@pytest.mark.parametrize("target,template,directive", [
    ("demo/portal/nginx.conf", templates.T1, "ssl_ecdh_curve X25519MLKEM768:X25519:prime256v1;"),
    ("demo/reminders/nginx.conf", templates.T1, "ssl_ecdh_curve X25519MLKEM768:X25519:prime256v1;"),
    ("demo/ops-ssh/sshd_config", templates.T2, "KexAlgorithms mlkem768x25519-sha256,sntrup761x25519-sha512@openssh.com,curve25519-sha256"),
    ("demo/lab-api/openssl.cnf", templates.T3, "Groups = X25519MLKEM768:X25519"),
])
def test_reviewable_patch_never_changes_target(agent_env, target, template, directive):
    before = (agent_env / target).read_bytes()
    result = propose.create(agent_eval.finding(target))
    samples.validate("patch_proposal", result["proposal"])
    assert result["proposal"]["template_id"] == template
    assert result["proposal"]["model"] == "rules-only"
    assert result["proposal"]["requires_human"] is True
    assert directive in result["rendered"]
    assert (agent_env / target).read_bytes() == before
    assert "--- a/" + target in result["diff"] and "+++ b/" + target in result["diff"]
    validator.validate_stored(result, agent_env)
    assert propose.get_proposal(result["proposal"]["proposal_id"]) == result


def test_strict_tls_has_no_classical_fallback_and_warns(agent_env):
    result = propose.create(agent_eval.finding("demo/portal/nginx.conf"), mode="strict")
    assert "ssl_protocols TLSv1.3;" in result["rendered"]
    assert "ssl_ecdh_curve X25519MLKEM768;" in result["rendered"]
    assert result["proposal"]["compatibility_risk"] == "high"
    assert "reject classical-only clients" in result["proposal"]["rationale"]
    result["proposal"]["compatibility_risk"] = "low"
    with pytest.raises(ValueError, match="high compatibility risk"):
        validator.validate_stored(result, agent_env)


@pytest.mark.parametrize("mutation", ["signature", "encryption", "resistant", "certificate", "java", "live", "wrong-service", "path-escape"])
def test_gate_rejects_non_templatable_findings(agent_env, mutation):
    f = agent_eval.finding("demo/portal/nginx.conf")
    if mutation in ("signature", "encryption"):
        f["usage"] = mutation
    elif mutation == "resistant":
        f["quantum_status"] = "resistant"
    elif mutation == "certificate":
        f["asset_type"] = "certificate"
    elif mutation == "java":
        f["location"]["path"], f["service"] = "demo/billing/Billing.java", "billing"
    elif mutation == "live":
        f["location"]["path"] = "live://portal:8443"
    elif mutation == "wrong-service":
        f["service"] = "lab-api"
    else:
        f["location"]["path"] = "demo/portal/../../etc/passwd"
    with pytest.raises(ValueError):
        propose.create(f)
    assert store.get("proposals", []) == []


def test_model_selection_is_constrained_and_labelled(agent_env):
    def llm(finding, original):
        assert "ssl_ecdh_curve" in original
        return {"template_id": templates.T1, "params": templates.parameters(templates.T1),
                "rationale": "A hybrid handshake protects future sessions; RSA signatures and legacy clients remain.",
                "compatibility_risk": "low"}
    result = propose.create(agent_eval.finding("demo/portal/nginx.conf"), llm=llm)
    assert result["proposal"]["model"] == propose.MODEL
    assert result["fallback_reason"] is None


def test_invalid_model_group_is_rejected_without_persisting(agent_env):
    def malicious(finding, original):
        return {"template_id": templates.T1, "params": {"groups": ["X25519; include /etc/passwd;"], "protocols": ["TLSv1.3"]},
                "rationale": "Just trust me", "compatibility_risk": "low"}
    with pytest.raises(ValueError, match="schema"):
        propose.create(agent_eval.finding("demo/portal/nginx.conf"), llm=malicious)
    assert store.get("proposals", []) == []


def test_timeout_fallback_is_visible(agent_env):
    def unavailable(*args):
        raise TimeoutError("model exceeded budget")
    result = propose.create(agent_eval.finding("demo/portal/nginx.conf"), llm=unavailable)
    assert result["proposal"]["model"] == "rules-only"
    assert "TimeoutError" in result["fallback_reason"]


@pytest.mark.parametrize("mutation", ["diff", "rendered", "target", "original-file", "hash"])
def test_stored_patch_tampering_and_stale_files_are_rejected(agent_env, mutation):
    result = propose.create(agent_eval.finding("demo/portal/nginx.conf"))
    if mutation == "original-file":
        p = agent_env / result["target"]
        p.write_bytes(p.read_bytes() + b"# external edit\n")
    elif mutation == "target":
        result["target"] = "demo/reminders/nginx.conf"
    elif mutation == "hash":
        result["diff_sha256"] = "0" * 64
    else:
        result[mutation] += "\nmalicious payload"
    with pytest.raises(ValueError):
        validator.validate_stored(result, agent_env)


def test_key_material_never_reaches_model(agent_env):
    p = agent_env / "demo/portal/nginx.conf"
    p.write_bytes(p.read_bytes() + b"# -----BEGIN RSA PRIVATE KEY-----\n")
    def must_not_call(*args):
        pytest.fail("model saw key material")
    with pytest.raises(ValueError, match="key material"):
        propose.create(agent_eval.finding("demo/portal/nginx.conf"), llm=must_not_call)


def test_duplicate_directive_fails_closed(agent_env):
    p = agent_env / "demo/portal/nginx.conf"
    p.write_bytes(p.read_bytes() + b"ssl_ecdh_curve X25519;\n")
    with pytest.raises(ValueError, match="exactly one"):
        propose.create(agent_eval.finding("demo/portal/nginx.conf"))


def test_windows_line_endings_preserve_exact_original_binding(agent_env):
    p = agent_env / "demo/portal/nginx.conf"
    p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    record = propose.create(agent_eval.finding("demo/portal/nginx.conf"))
    assert "\r\n" in record["rendered"]
    assert "\n" not in record["rendered"].replace("\r\n", "")
    validator.validate_stored(record, agent_env)


def test_concurrent_requests_have_unique_durable_ids(agent_env):
    f = agent_eval.finding("demo/portal/nginx.conf")
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda _: propose.create(f), range(8)))
    ids = [r["proposal"]["proposal_id"] for r in records]
    assert len(set(ids)) == 8
    assert set(store.get("proposals")) == set(ids)
    assert all(propose.get_proposal(pid)["proposal"]["proposal_id"] == pid for pid in ids)


def test_twenty_case_eval_and_adversarial_cases_are_honest(agent_env):
    report = agent_eval.run(agent_env)
    assert report["cases"] == report["parseable"] == report["correct_template"] == 20
    assert report["validator_bypasses"] == report["granite_cases"] == 0
    assert len(report["adversarial"]) == 10
    assert report["passed"] and report["models_used"] == ["rules-only"]
    assert sum(c["source"] == "real-file" for c in report["results"]) == 4


def test_context_is_limited_to_sixty_lines():
    excerpt = llm_client.context_window("\n".join(f"line-{i}" for i in range(120)), 80)
    assert len(excerpt.splitlines()) == 60
    assert "80: line-79" in excerpt


def test_http_proposals_and_validation(agent_env):
    app = FastAPI()
    app.include_router(agent.router)
    client = TestClient(app)
    f = agent_eval.finding("demo/portal/nginx.conf")
    store.put("findings", [f])
    assert client.post("/proposals", json={"finding_id": "missing"}).status_code == 404
    assert client.post("/proposals", json={"finding_id": f["finding_id"], "mode": "invented"}).status_code == 422
    response = client.post("/proposals", json={"finding_id": f["finding_id"]})
    assert response.status_code == 200
    pid = response.json()["proposal"]["proposal_id"]
    assert client.get("/proposals/" + pid).json() == response.json()
    assert len(client.get("/proposals").json()) == 1


def test_sample_mode_cannot_be_confused_with_evidence(agent_env, monkeypatch):
    monkeypatch.setenv("CHRONOS_USE_SAMPLES", "1")
    app = FastAPI()
    app.include_router(agent.router)
    result = TestClient(app).post("/proposals", json={"finding_id": "anything"}).json()
    assert result["sample"] and result["state"] == "sample" and result["diff"] == ""
    assert store.get("proposals", []) == []
