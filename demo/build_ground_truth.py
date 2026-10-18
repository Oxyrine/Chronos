"""Independent inventory of deliberately planted assets, not scanner output.

Run after runtime key generation. Missing optional billing JKS is reported as a cut.
Generated key locations have no line constraint; source lines are resolved from exact anchors.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def build():
    assets = []
    def add(path, algorithm, kind="algorithm", status="vulnerable", anchor=None, **params):
        item = {"id": f"A-{len(assets)+1:03d}", "path": path, "asset_type": kind,
                "algorithm": algorithm, "params": params, "quantum_status": status}
        if anchor:
            matches = [i for i, line in enumerate((ROOT/path).read_text().splitlines(),1) if anchor in line]
            if len(matches) != 1:
                raise ValueError(f"ground-truth anchor is not unique: {path}: {anchor}")
            item["line"] = matches[0]
        assets.append(item)
    for svc in ("portal", "reminders", "partner-lab"):
        add(f"demo/{svc}/nginx.conf", "TLSv1.3 TLSv1.2", "protocol", "resistant", "ssl_protocols")
        add(f"demo/{svc}/nginx.conf", "X25519MLKEM768:X25519:prime256v1" if svc=="partner-lab" else "X25519:prime256v1", "protocol", "resistant" if svc=="partner-lab" else "vulnerable", "ssl_ecdh_curve")
    for svc in ("portal", "reminders", "partner-lab", "records-db", "chronos-nginx"):
        for filename, kind in (("server.crt", "certificate"),("server.key", "related-crypto-material"),("ca.pem", "certificate")):
            path = f"demo/{svc}/certs/{filename}"
            if (ROOT/path).exists():
                add(path, "RSA", kind, key_bits=2048)
    for filename,kind in (("ca.pem","certificate"),("ca.key","related-crypto-material")):
        path=f"demo/ca/{filename}"
        if (ROOT/path).exists(): add(path,"RSA",kind,key_bits=2048)
    add("demo/records-db/postgresql.conf", "prime256v1", "protocol", anchor="ssl_ecdh_curve")
    add("demo/ops-ssh/sshd_config", "curve25519-sha256,ecdh-sha2-nistp256", "protocol", anchor="KexAlgorithms")
    for name in ("ssh_host_rsa_key", "probe_key"):
        path=f"demo/ops-ssh/certs/{name}"
        if (ROOT/path).exists(): add(path,"RSA","related-crypto-material",key_bits=2048)
    for svc in ("lab-api", "infra"):
        add(f"demo/{svc}/openssl.cnf", "X25519:P-256", "protocol", anchor="Groups =")
    python = "demo/lab-api/crypto_utils.py"
    for alg,anchor,status in (("RSA","wrapping_key =","vulnerable"),("RSA-OAEP","wrapped =","vulnerable"),("ECDSA","signer =","vulnerable"),("SHA-1",'"etag": hashlib.sha1',"weakened")):
        add(python,alg,status=status,anchor=anchor)
    # Include resistant primitives as well as migration candidates.
    add(python,"AES-256-GCM",status="resistant",anchor="aes_key =",key_bits=256)
    java = "demo/billing/Billing.java"
    for alg,anchor,status in (("RSA","KeyPairGenerator keys =","vulnerable"),("SHA256withRSA","Signature signer =","vulnerable"),("AES-ECB","Cipher legacy =","resistant"),("SHA-1","MessageDigest etag =","weakened")):
        add(java,alg,status=status,anchor=anchor)
    jks="demo/billing/billing.jks"
    if (ROOT/jks).exists():
        add(jks,"RSA","related-crypto-material",key_bits=2048)
        add(jks,"RSA","certificate",key_bits=2048)
    add("demo/infra/terraform/main.tf","RSA","related-crypto-material",anchor='resource "tls_private_key"',key_bits=2048)
    add("demo/infra/java.security","x25519,secp256r1","protocol",anchor="jdk.tls.namedGroups=")
    for svc,port,alg in (("portal",8443,"X25519"),("reminders",8444,"X25519"),("ops-ssh",2222,"curve25519-sha256")):
        add(f"live://{svc}:{port}",alg,"protocol")
    return {"assets":assets,"notes":["Baseline inventory: regenerate after a reset, not after a patch; retain before findings separately.","AES-256-GCM is inventoried at its key-generation call.","Live partner-lab probe is excluded because the measured channel is the pinned lab-api client."]}

if __name__ == "__main__":
    out=ROOT/"demo/ground_truth.yaml"
    result=build()
    out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(f"Inventory: {len(result['assets'])} assets; billing JKS present: {(ROOT/'demo/billing/billing.jks').exists()}")
