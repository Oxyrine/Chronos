import json

import pytest

from chronos.common import samples
from chronos.discovery import cbom_writer, certs_keys, configs, evaluate, java_src, live_probe, llm_assist, merge, python_ast, scan


@pytest.fixture
def topo():
    t = samples.sample("topology")
    t["channels"].append({"id": "billing->bank", "src": "billing", "dst": "bank", "protocol": "tls", "reach": "partner", "tables": ["lab_results"]})
    return t


def by(assets, **kw):
    return [a for a in assets if all(a.get(k) == v for k, v in kw.items())]


def test_certs_keys_finds_cert_and_key(demo_tree):
    root, fp = demo_tree
    found = certs_keys.scan(root, root)
    certs = by(found, asset_type="certificate", path="demo/portal/portal.pem")
    assert len(certs) == 1 and certs[0]["algorithm"] == "RSA" and certs[0]["params"]["key_bits"] == 2048
    assert certs[0]["fingerprint"] == fp and certs[0]["params"]["signature_algorithm"] == "sha256WithRSAEncryption"
    assert by(found, asset_type="related-crypto-material", path="demo/portal/portal.pem")[0]["params"]["key_bits"] == 2048
    ec = by(found, path="demo/ops-ssh/ca.der")[0]
    assert ec["algorithm"] == "ECDSA" and ec["params"]["curve"] == "secp256r1"


def test_configs(demo_tree):
    root, _ = demo_tree
    found = configs.scan(root, root)
    nginx = by(found, path="demo/portal/nginx.conf", usage="key_exchange")[0]
    assert nginx["algorithm"] == "X25519:prime256v1" and nginx["status"] == "vulnerable" and nginx["line"] == 6
    assert by(found, path="demo/portal/nginx.conf", usage="protocol")[0]["status"] == "resistant"
    assert by(found, path="demo/ops-ssh/sshd_config")[0]["params"]["groups"] == ["curve25519-sha256", "ecdh-sha2-nistp256"]
    assert by(found, path="demo/lab-api/openssl.cnf")[0]["algorithm"] == "X25519:P-256"
    tf = by(found, path="infra/terraform/main.tf")[0]
    assert tf["algorithm"] == "RSA" and tf["params"]["key_bits"] == 2048 and tf["line"] == 1


def test_hybrid_list_is_resistant_but_records_classical_fallback():
    out = configs.scan_text("ssl_ecdh_curve X25519MLKEM768:X25519:prime256v1;\n", "demo/portal/nginx.conf", "nginx.conf")
    assert out[0]["status"] == "resistant" and out[0]["params"]["classical_accepted"] is True
    out = configs.scan_text("KexAlgorithms mlkem768x25519-sha256,sntrup761x25519-sha512@openssh.com,curve25519-sha256\n", "p", "sshd_config")
    assert out[0]["status"] == "resistant"


def test_python_ast(demo_tree):
    root, _ = demo_tree
    found = python_ast.scan(root, root)
    algs = {(a["algorithm"], a["line"]) for a in found}
    assert ("RSA", 5) in algs and ("ECDSA", 6) in algs and ("RSA-OAEP", 9) in algs and ("SHA-1", 12) in algs
    assert by(found, algorithm="RSA-OAEP")[0]["params"]["key_bits"] == 2048 and by(found, algorithm="RSA-OAEP")[0]["usage"] == "key_exchange"
    assert by(found, algorithm="ECDSA")[0]["params"]["curve"] == "secp256r1"


def test_java_src(demo_tree):
    root, _ = demo_tree
    found = java_src.scan(root, root)
    assert by(found, algorithm="RSA")[0]["params"]["key_bits"] == 2048
    assert {a["algorithm"] for a in found} >= {"RSA", "SHA256withRSA", "AES-ECB", "SHA-1"}


def test_ground_truth_never_read(demo_tree):
    root, _ = demo_tree
    assert not any("ground_truth" in a["path"] for a in certs_keys.scan(root, root) + configs.scan(root, root))


def test_live_probe_parses_openssl_and_ssh():
    tls = "CONNECTION ESTABLISHED\nProtocol version: TLSv1.3\nCiphersuite: TLS_AES_256_GCM_SHA384\nNegotiated TLS1.3 group: X25519MLKEM768\n"
    assert live_probe.parse_s_client(tls) == {"group": "X25519MLKEM768", "protocol": "TLSv1.3"}
    assert live_probe.parse_ssh("debug1: kex: algorithm: mlkem768x25519-sha256\n")["group"] == "mlkem768x25519-sha256"
    topo = samples.sample("topology")
    fake = lambda cmd: tls if cmd[0] == "openssl" else "debug1: kex: algorithm: curve25519-sha256"
    out = live_probe.scan(topo, fake)
    assert by(out, algorithm="X25519MLKEM768")[0]["status"] == "resistant"
    assert by(out, algorithm="curve25519-sha256")[0]["status"] == "vulnerable"


def test_llm_assist_confidence_floor_and_failure():
    reply = {"assets": [{"algorithm": "RSA-1024", "usage": "encryption", "line": 3, "confidence": 0.9},
                        {"algorithm": "maybe-DES", "usage": "encryption", "line": 4, "confidence": 0.5}]}
    out = llm_assist.scan_files({"x.go": "rsa"}, lambda p: reply)
    assert [a["algorithm"] for a in out] == ["RSA-1024"] and out[0]["method"] == "ai"

    def boom(_):
        raise RuntimeError("llm down")
    assert llm_assist.scan_files({"x.go": "rsa"}, boom) == []


def test_merge_dedupes_and_unions_sources():
    a = {"path": "p", "line": 3, "algorithm": "RSA", "sources": ["python_ast"], "confidence": 1.0, "method": "deterministic", "params": {}, "fingerprint": None}
    b = {**a, "sources": ["cbomkit-theia"], "confidence": 0.8}
    m = merge.merge([a, b])
    assert len(m) == 1 and m[0]["sources"] == ["python_ast", "cbomkit-theia"]
    c = {**a, "fingerprint": "ab", "line": None}
    d = {**c, "line": 9, "sources": ["certs_keys"]}
    assert len(merge.merge([c, d])) == 1  # same cert fingerprint in same file = one asset


def test_full_scan_findings_cbom_and_contracts(demo_tree, topo):
    root, _ = demo_tree
    res = scan.run(root, topo, probe=None)
    for f in res["findings"]:
        samples.validate("finding", {k: f[k] for k in samples.sample("finding")})
    cbom_writer.validate(res["cbom"])
    for c in res["cbom"]["components"]:
        samples.validate("cbom_component", c)
    f = {x["bom_ref"]: x for x in res["findings"]}
    portal_kex = next(x for x in res["findings"] if x["service"] == "portal" and x["usage"] == "key_exchange")
    assert portal_kex["channels"] == ["internet->portal"] and portal_kex["quantum_status"] == "vulnerable" and portal_kex["fix_class"] == "config"
    ssh_kex = next(x for x in res["findings"] if x["service"] == "ops-ssh" and x["usage"] == "key_exchange")
    assert ssh_kex["channels"] == ["clinician->ops-ssh"]
    sha1 = next(x for x in res["findings"] if x["algorithm"] == "SHA-1" and x["location"]["path"].endswith(".py"))
    assert sha1["classical_weak"] and sha1["quantum_status"] == "resistant"
    assert res["stats"]["scan_seconds"] < 60 and len(f) == len(res["findings"])


def test_bad_cbom_fails_validation(demo_tree, topo):
    root, _ = demo_tree
    cbom = scan.run(root, topo)["cbom"]
    cbom["components"][0]["cryptoProperties"]["assetType"] = "nonsense"
    import jsonschema
    with pytest.raises(jsonschema.ValidationError):
        cbom_writer.validate(cbom)


def test_recall_precision_against_planted_truth(demo_tree, topo):
    root, _ = demo_tree
    findings = scan.run(root, topo)["findings"]
    gt = [
        {"id": "GT1", "path": "demo/portal/nginx.conf", "line": 6, "algorithm": "X25519"},
        {"id": "GT2", "path": "demo/portal/portal.pem", "algorithm": "RSA-2048"},
        {"id": "GT3", "path": "demo/ops-ssh/sshd_config", "line": 2, "algorithm": "curve25519-sha256"},
        {"id": "GT4", "path": "demo/lab-api/crypto_utils.py", "line": 9, "algorithm": "RSA-OAEP"},
        {"id": "GT5", "path": "demo/lab-api/crypto_utils.py", "line": 6, "algorithm": "ECDSA P-256"},
        {"id": "GT6", "path": "demo/billing/Billing.java", "line": 9, "algorithm": "SHA-1"},
        {"id": "GT7", "path": "demo/billing/Billing.java", "line": 8, "algorithm": "AES-ECB"},
        {"id": "GT8", "path": "infra/terraform/main.tf", "line": 1, "algorithm": "RSA"},
        {"id": "GT9", "path": "demo/nowhere.conf", "line": 1, "algorithm": "RSA"},  # planted but unfindable: recall must show the miss
    ]
    s = evaluate.score(findings, gt)
    assert s["missed"] == ["GT9"] and s["recall"] == pytest.approx(8 / 9, abs=0.01)
    assert s["precision"] >= 0.5
