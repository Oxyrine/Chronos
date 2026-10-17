"""Discovery recall / precision against demo/ground_truth.yaml (used only for evaluation, never by scanners).

Match rule (to agree with Person A): same path, algorithm family overlaps, and lines within +-2 when both have one.
Recall = ground-truth assets matched by any finding. Precision = findings that match any ground-truth asset.
"""
import re

FAMILIES = {
    "rsa": r"rsa", "ec": r"ecdsa|ecdh|secp|prime256|p-?256|p-?384|nistp|\bec\b|elliptic", "x25519": r"x25519|curve25519",
    "ed25519": r"ed25519", "sha1": r"sha-?1\b|sha1", "md5": r"md5", "aes": r"aes", "dh": r"\bdh\b|diffie|ffdhe",
    "mlkem": r"mlkem|ml-kem|sntrup", "tls": r"tlsv?1\.[0-3]",
}


def families(alg: str) -> set[str]:
    a = alg.lower()
    return {k for k, rx in FAMILIES.items() if re.search(rx, a)}


def matches(finding: dict, gt: dict, tol: int = 2) -> bool:
    if finding["location"]["path"] != gt["path"]:
        return False
    fl, gl = finding["location"].get("line"), gt.get("line")
    if fl and gl and abs(fl - gl) > tol:
        return False
    fa, ga = families(finding["algorithm"]), families(gt["algorithm"])
    return bool(fa & ga) if fa and ga else finding["algorithm"].lower() == gt["algorithm"].lower()


def score(findings: list[dict], gt_assets: list[dict]) -> dict:
    hit_gt = {g["id"] for g in gt_assets if any(matches(f, g) for f in findings)}
    ok_f = {f["finding_id"] for f in findings if any(matches(f, g) for g in gt_assets)}
    return {
        "recall": round(len(hit_gt) / max(len(gt_assets), 1), 3),
        "precision": round(len(ok_f) / max(len(findings), 1), 3),
        "ground_truth": len(gt_assets), "findings": len(findings),
        "missed": sorted(g["id"] for g in gt_assets if g["id"] not in hit_gt),
        "extra": sorted(f["finding_id"] for f in findings if f["finding_id"] not in ok_f),
    }


def grep_baseline(roots, base) -> list[dict]:
    """The spec's baseline: grep -rE 'RSA|ECDSA|BEGIN .* KEY' over the same tree, one hit per matching line."""
    from chronos.discovery.common import iter_files, rel
    rx = re.compile(r"RSA|ECDSA|BEGIN .* KEY")
    out = []
    for root in roots:
        for p in iter_files(root, (".py", ".java", ".conf", ".cnf", ".tf", ".pem", ".key", ".crt", ".yaml", ".yml", ".sh", ".txt", ".md", ".security", ".properties"), ("sshd_config",)):
            for no, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                if m := rx.search(line):
                    out.append({"finding_id": f"G-{len(out) + 1:04d}", "algorithm": m.group(0), "location": {"path": rel(p, base), "line": no}})
    return out


def score_loose(findings: list[dict], gt_assets: list[dict], tol: int = 2) -> dict:
    """Same as score() but ignores the algorithm, because grep cannot name one. Favours the baseline."""
    loose = lambda f, g: f["location"]["path"] == g["path"] and (not g.get("line") or abs(f["location"].get("line", 0) - g["line"]) <= tol)
    hit = {g["id"] for g in gt_assets if any(loose(f, g) for f in findings)}
    ok = {f["finding_id"] for f in findings if any(loose(f, g) for g in gt_assets)}
    return {"recall": round(len(hit) / max(len(gt_assets), 1), 3), "precision": round(len(ok) / max(len(findings), 1), 3), "findings": len(findings)}
