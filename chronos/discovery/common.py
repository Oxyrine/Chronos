"""Shared helpers for the six Discovery scanners. Scanners emit raw assets (plain dicts); merge.py turns them into Findings."""
import pathlib

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "out", "ledger", "dist", ".mypy_cache", ".pytest_cache"}
# The scanners must never read the evaluation answer key or the topology file.
NEVER_READ = {"ground_truth.yaml", "ground_truth.yml", "topology.yaml", "topology.yml"}

DEFAULT_FIX = {"certs_keys": "config", "configs": "config", "live_probe": "config",
               "python_ast": "code_change", "java_src": "code_change", "llm_assist": "code_change"}


def iter_files(root, suffixes=(), names=()):
    root = pathlib.Path(root)
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name in NEVER_READ:
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        if p.suffix.lower() in suffixes or p.name in names:
            yield p


def rel(path, base) -> str:
    return pathlib.Path(path).resolve().relative_to(pathlib.Path(base).resolve()).as_posix()


def asset(*, path, line, asset_type, algorithm, usage, source, params=None, status=None, confidence=1.0,
          method="deterministic", fix_class=None, fingerprint=None) -> dict:
    return {"path": path, "line": line, "asset_type": asset_type, "algorithm": algorithm, "usage": usage,
            "params": params or {}, "status": status, "confidence": confidence, "method": method,
            "fix_class": fix_class or DEFAULT_FIX[source], "fingerprint": fingerprint, "sources": [source]}


def service_of(path: str) -> str:
    parts = path.split("/")
    if parts[0] == "demo" and len(parts) > 2:
        return parts[1]
    if path.startswith("live://"):
        return path[len("live://"):].split(":")[0]
    return parts[0] if len(parts) > 1 else "unknown"
