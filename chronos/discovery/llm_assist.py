"""Scanner: Granite reads files no deterministic scanner parsed. Output is schema-constrained and floored at confidence 0.7.

Every asset it adds is tagged method="ai". It never sees cell values, only file text from the scanned tree.
"""
import json
import os
import urllib.request

from chronos.discovery.common import asset, iter_files, rel

SOURCE = "llm_assist"
MIN_CONFIDENCE = 0.7
MAX_CHARS = 6000
SCHEMA = {
    "type": "object", "required": ["assets"],
    "properties": {"assets": {"type": "array", "items": {
        "type": "object", "required": ["algorithm", "usage", "line", "confidence"],
        "properties": {"algorithm": {"type": "string"}, "line": {"type": "integer"}, "confidence": {"type": "number"},
                       "usage": {"enum": ["key_exchange", "encryption", "signature", "hash", "symmetric", "protocol"]},
                       "params": {"type": "object"}}}}},
}
PROMPT = ("List every cryptographic algorithm, key size or protocol group used in this file. Reply as JSON "
          '{"assets":[{"algorithm":..,"usage":..,"line":..,"confidence":0-1,"params":{}}]}. Only report what is in the text.\n\nFILE %s\n%s')


def granite(prompt: str) -> dict:
    """POST to the on-box llama-server (JSON-schema constrained). No external calls."""
    url = os.environ.get("CHRONOS_LLM_URL", "http://llm:8080") + "/completion"
    body = json.dumps({"prompt": prompt, "json_schema": SCHEMA, "n_predict": 400, "temperature": 0}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(json.loads(r.read())["content"])


def scan_files(files: dict[str, str], llm=granite) -> list[dict]:
    """files: {path: text}. llm: callable(prompt) -> {"assets": [...]}; injectable for tests."""
    out = []
    for path, text in files.items():
        try:
            reply = llm(PROMPT % (path, text[:MAX_CHARS]))
        except Exception:  # LLM down or malformed: skip the file, deterministic scanners already ran
            continue
        for a in reply.get("assets", []):
            if a.get("confidence", 0) < MIN_CONFIDENCE:
                continue
            out.append(asset(path=path, line=a["line"], asset_type="algorithm", algorithm=a["algorithm"], usage=a["usage"],
                             source=SOURCE, params=a.get("params") or {}, confidence=a["confidence"], method="ai"))
    return out


def unparsed_files(root, base, covered: set[str]) -> dict[str, str]:
    """Crypto-looking files that no deterministic scanner produced an asset for (other languages, odd configs)."""
    hints = ("rsa", "ecdsa", "ecdh", "cipher", "tls", "kex", "aes", "sha1", "md5", "private key")
    out = {}
    for p in iter_files(root, (".go", ".js", ".ts", ".rb", ".php", ".sh", ".yaml", ".yml", ".ini", ".toml", ".properties", ".xml", ".cfg", ".rs", ".c", ".cpp")):
        path = rel(p, base)
        text = p.read_text(errors="replace")
        if path not in covered and any(h in text.lower() for h in hints):
            out[path] = text
    return out
