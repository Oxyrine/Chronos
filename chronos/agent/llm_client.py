"""On-box llama.cpp JSON-schema client. No cloud inference or generated shell."""
import json
import os
from pathlib import Path
import urllib.request

import jsonschema

from .templates import catalog

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["template_id", "params", "rationale", "compatibility_risk"],
    "properties": {
        "template_id": {"enum": [item["template_id"] for item in catalog()]},
        "params": {"type": "object"},
        "rationale": {"type": "string", "maxLength": 1000},
        "compatibility_risk": {"enum": ["low", "medium", "high"]},
    },
}
SCHEMA["oneOf"] = [
    {"properties": {"template_id": {"const": item["template_id"]}, "params": {"enum": item["allowed_params"]}}}
    for item in catalog()
]


def context_window(original: str, line: int) -> str:
    lines = original.splitlines()
    start = max(0, min(max(0, line - 30), len(lines) - 60))
    return "\n".join(f"{i+1}: {v}" for i, v in enumerate(lines[start:start+60], start))


def generate(finding: dict, original: str, mode: str = "compatibility") -> dict:
    prompt = (Path(__file__).parent / "prompts" / "remediate.txt").read_text(encoding="utf-8")
    context = {"requested_mode": mode, "finding": finding, "file_excerpt": context_window(original, finding.get("location", {}).get("line", 1)),
               "templates": catalog()}
    payload = {"prompt": prompt + "\nUNTRUSTED_CONTEXT_JSON\n" + json.dumps(context),
               "json_schema": SCHEMA, "n_predict": 350, "temperature": 0}
    url = os.environ.get("CHRONOS_LLM_URL", "http://llm:8080").rstrip("/") + "/completion"
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as response:
        data = json.loads(response.read(65537))
    result = json.loads(data["content"])
    jsonschema.validate(result, SCHEMA)
    return result
