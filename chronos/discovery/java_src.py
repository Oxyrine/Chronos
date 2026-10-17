"""Scanner: Java source. Regex over getInstance(...) strings.

# ponytail: regex, not tree-sitter. It misses algorithm names built at runtime; llm_assist covers odd files, upgrade to tree-sitter if recall is short.
"""
import re

from chronos.discovery.common import asset, iter_files, rel

SOURCE = "java_src"
GET = re.compile(r'\b(KeyPairGenerator|Signature|Cipher|KeyAgreement|MessageDigest|KeyGenerator|Mac)\s*\.\s*getInstance\(\s*"([^"]+)"')
INIT = re.compile(r"\.\s*initialize\(\s*(\d+)")
KEYSIZE = re.compile(r"\.\s*init\(\s*(\d+)")


def scan_source(src: str, path: str) -> list[dict]:
    out = []
    lines = src.splitlines()
    for no, line in enumerate(lines, 1):
        for m in GET.finditer(line):
            kind, name = m.groups()
            upper = name.upper()
            params, alg, usage = {}, name, "encryption"
            if kind == "KeyPairGenerator":
                alg, usage = upper, "encryption"
                for nxt in lines[no - 1: no + 6]:  # the matching .initialize(n) is within a few lines
                    if i := INIT.search(nxt):
                        params["key_bits"] = int(i.group(1))
                        break
            elif kind == "Signature":
                usage = "signature"
            elif kind == "Cipher":
                if upper.startswith("RSA"):
                    alg, usage = "RSA-OAEP" if "OAEP" in upper else "RSA", "key_exchange"
                elif upper.startswith("AES") and "ECB" in upper:
                    alg, usage = "AES-ECB", "symmetric"
                else:
                    usage = "symmetric"
            elif kind == "KeyAgreement":
                usage = "key_exchange"
            elif kind == "MessageDigest":
                usage = "hash"
            elif kind in ("KeyGenerator", "Mac"):
                usage = "symmetric"
                for nxt in lines[no - 1: no + 4]:
                    if i := KEYSIZE.search(nxt):
                        params["key_bits"] = int(i.group(1))
                        break
            out.append(asset(path=path, line=no, asset_type="algorithm", algorithm=alg, usage=usage, source=SOURCE,
                             params={**params, "java_class": kind, "java_name": name}))
    return out


def scan(root, base=None) -> list[dict]:
    base = base or root
    out = []
    for p in iter_files(root, (".java",)):
        out += scan_source(p.read_text(errors="replace"), rel(p, base))
    return out
