"""Fail closed on template mismatch, path escapes, invented groups and stale files."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from chronos.common.samples import validate
from .templates import T1, T2, T3, check_parameters, parameters, render

MAX_FILE_BYTES = 65536
KEY_MATERIAL = re.compile(r"-----BEGIN[^\r\n]*\bKEY-----|[A-Za-z0-9+/]{128,}={0,2}", re.IGNORECASE)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def no_key_material(text: str) -> None:
    if KEY_MATERIAL.search(text):
        raise ValueError("key material or long encoded data is forbidden")


def eligible(finding: dict) -> tuple[str, str]:
    if finding.get("usage") != "key_exchange" or finding.get("quantum_status") != "vulnerable":
        raise ValueError("only vulnerable key-exchange findings can be proposed")
    if finding.get("asset_type") != "protocol":
        raise ValueError("this asset needs manual remediation")
    target = finding.get("location", {}).get("path", "")
    if not isinstance(target, str) or "\\" in target or ":" in target:
        raise ValueError("target must be a repository-relative POSIX path")
    path = PurePosixPath(target)
    if path.is_absolute() or ".." in path.parts or str(path) != target:
        raise ValueError("target path is not canonical")
    parts = path.parts
    if len(parts) != 3 or parts[0] != "demo":
        raise ValueError("target is outside the approved demo files")
    service, name = parts[1:]
    if finding.get("service") != service:
        raise ValueError("finding service and path disagree")
    if service in ("portal", "reminders") and name == "nginx.conf":
        return T1, target
    if service == "ops-ssh" and name == "sshd_config":
        return T2, target
    if service == "lab-api" and name == "openssl.cnf":
        return T3, target
    raise ValueError("no enabled template for this file; manual remediation required")


def read_target(root: Path, target: str) -> str:
    root = root.resolve()
    path = root / target
    cursor = root
    for part in PurePosixPath(target).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("symlink targets are forbidden")
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("target is not a regular file inside the repository")
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("target exceeds 64 KiB")
    text = resolved.read_bytes().decode("utf-8")
    if "\r" in text.replace("\r\n", ""):
        raise ValueError("target contains a lone carriage return")
    no_key_material(text)
    return text


def validate_proposal(proposal: dict, finding: dict, original: str, diff: str | None = None) -> tuple[str, str]:
    validate("patch_proposal", proposal)
    template, target = eligible(finding)
    if proposal["finding_id"] != finding["finding_id"] or proposal["template_id"] != template:
        raise ValueError("proposal is not bound to the eligible finding/template")
    check_parameters(template, proposal["params"])
    if template == T1 and proposal["params"] == parameters(T1, "strict") and proposal["compatibility_risk"] != "high":
        raise ValueError("strict TLS rejects legacy clients and must show high compatibility risk")
    no_key_material(json.dumps(proposal))
    if len(proposal["rationale"]) > 1000:
        raise ValueError("rationale exceeds 1000 characters")
    no_key_material(original)
    rendered, expected_diff = render(template, proposal["params"], original, target)
    if diff is not None and diff != expected_diff:
        raise ValueError("diff does not match the deterministic single-file renderer")
    no_key_material(expected_diff)
    return rendered, expected_diff


def validate_stored(record: dict, root: Path) -> None:
    finding = record["finding"]
    _, target = eligible(finding)
    if record["target"] != target:
        raise ValueError("stored target does not match finding")
    original = read_target(Path(root), target)
    if sha256(original) != record["original_sha256"]:
        raise ValueError("target changed since proposal; scan and propose again")
    rendered, diff = validate_proposal(record["proposal"], finding, original, record["diff"])
    if rendered != record["rendered"] or sha256(diff) != record["diff_sha256"]:
        raise ValueError("stored proposal evidence was modified")
