"""On-box llama.cpp JSON-schema client. No cloud inference or generated shell.

Latency on the L1CC VM (Granite 3.3 2B Q8_0, 3 vCPUs) was measured at about 14.5 prompt
tokens/s and 5.9 generated tokens/s, so a 60-line excerpt plus 350 output tokens cannot
finish inside 20 s. The prompt is therefore split into a static prefix (instructions and
template catalog, identical on every call so llama-server's prompt cache reuses it) and a
short per-finding suffix, and generation is capped. Every knob is an environment variable
so the VM run can be tuned without code changes.
"""
import json
import os
from pathlib import Path
import urllib.request

import jsonschema

from .templates import catalog

RATIONALE_MAX = 300

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["template_id", "params", "rationale", "compatibility_risk"],
    "properties": {
        "template_id": {"enum": [item["template_id"] for item in catalog()]},
        "params": {"type": "object"},
        "rationale": {"type": "string", "maxLength": RATIONALE_MAX},
        "compatibility_risk": {"enum": ["low", "medium", "high"]},
    },
}
SCHEMA["oneOf"] = [
    {"properties": {"template_id": {"const": item["template_id"]}, "params": {"enum": item["allowed_params"]}}}
    for item in catalog()
]


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def context_window(original: str, line: int, size: int = 60) -> str:
    """Up to `size` numbered lines around `line` (spec 7.7 allows at most 60)."""
    size = max(1, min(size, 60))
    lines = original.splitlines()
    start = max(0, min(max(0, line - size // 2), len(lines) - size))
    return "\n".join(f"{i+1}: {v}" for i, v in enumerate(lines[start:start+size], start))


def static_prefix() -> str:
    """Instructions plus the compact template catalog; byte-identical across calls for the prompt cache."""
    prompt = (Path(__file__).parent / "prompts" / "remediate.txt").read_text(encoding="utf-8")
    return prompt + "\nTEMPLATES_JSON\n" + json.dumps(catalog(), separators=(",", ":")) + "\n"


def build_prompt(finding: dict, original: str, mode: str = "compatibility") -> str:
    lines = _int_env("CHRONOS_LLM_CONTEXT_LINES", 12)
    location = finding.get("location", {})
    context = {"requested_mode": mode,
               "finding": {k: finding.get(k) for k in ("finding_id", "service", "usage", "algorithm", "quantum_status")}
               | {"path": location.get("path"), "line": location.get("line")},
               "file_excerpt": context_window(original, location.get("line", 1), lines)}
    return static_prefix() + "UNTRUSTED_CONTEXT_JSON\n" + json.dumps(context, separators=(",", ":")) + "\nJSON:\n"


def generate(finding: dict, original: str, mode: str = "compatibility") -> dict:
    payload = {"prompt": build_prompt(finding, original, mode), "json_schema": SCHEMA,
               "n_predict": _int_env("CHRONOS_LLM_MAX_TOKENS", 160), "temperature": 0, "cache_prompt": True}
    url = os.environ.get("CHRONOS_LLM_URL", "http://llm:8080").rstrip("/") + "/completion"
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=_int_env("CHRONOS_LLM_TIMEOUT", 90)) as response:
        data = json.loads(response.read(65537))
    result = json.loads(data["content"])
    jsonschema.validate(result, SCHEMA)
    return result


def warm() -> float:
    """Evaluate the static prefix once so the first real proposal only pays for its suffix."""
    import time
    started = time.perf_counter()
    payload = {"prompt": static_prefix(), "n_predict": 0, "cache_prompt": True}
    url = os.environ.get("CHRONOS_LLM_URL", "http://llm:8080").rstrip("/") + "/completion"
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=_int_env("CHRONOS_LLM_TIMEOUT", 90) * 2) as response:
        response.read(65537)
    return time.perf_counter() - started
