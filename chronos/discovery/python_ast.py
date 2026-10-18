"""Scanner: Python source via the ast module. Reads files, never imports or executes them."""
import ast

from chronos.discovery.common import asset, iter_files, rel

SOURCE = "python_ast"
HASHES = {"sha1": "SHA-1", "md5": "MD5"}


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def const_arg(call: ast.Call, name: str | None = None, pos: int | None = None):
    for kw in call.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant):
            return kw.value.value
    if pos is not None and len(call.args) > pos and isinstance(call.args[pos], ast.Constant):
        return call.args[pos].value
    return None


def scan_source(src: str, path: str) -> list[dict]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    rsa_bits = None
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    calls.sort(key=lambda n: (n.lineno, n.col_offset))
    imports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for item in node.names:
                imports[item.asname or item.name] = node.module + "." + item.name
        elif isinstance(node, ast.Import):
            for item in node.names:
                imports[item.asname or item.name.split(".")[0]] = item.name if item.asname else item.name.split(".")[0]
    out = []

    def add(node, **kw):
        out.append(asset(path=path, line=node.lineno, source=SOURCE, **kw))

    for c in calls:
        fn = dotted(c.func)
        last = fn.rsplit(".", 1)[-1]
        head, _, tail = fn.partition(".")
        canonical = imports.get(head, head) + ("." + tail if tail else "")
        if canonical == "cryptography.hazmat.primitives.ciphers.aead.AESGCM.generate_key":
            bits = const_arg(c, "bit_length", 0)
            known = type(bits) is int and bits in (128, 192, 256)
            add(c, asset_type="algorithm", algorithm=f"AES-{bits}-GCM" if known else "AES-GCM",
                usage="symmetric", params={"key_bits": bits} if known else {},
                status=None if known else "vulnerable")
        elif fn.endswith("rsa.generate_private_key") or (fn == "generate_private_key" and const_arg(c, "key_size", 1)):
            rsa_bits = const_arg(c, "key_size", 1)
            add(c, asset_type="algorithm", algorithm="RSA", usage="encryption", params={"key_bits": rsa_bits})
        elif fn.endswith("ec.generate_private_key"):
            curve = dotted(c.args[0].func) if c.args and isinstance(c.args[0], ast.Call) else (dotted(c.args[0]) if c.args else "")
            add(c, asset_type="algorithm", algorithm="ECDSA", usage="signature", params={"curve": curve.rsplit(".", 1)[-1].lower() or "unknown"})
        elif fn in ("RSA.generate", "Crypto.PublicKey.RSA.generate", "Cryptodome.PublicKey.RSA.generate"):
            rsa_bits = const_arg(c, "bits", 0)
            add(c, asset_type="algorithm", algorithm="RSA", usage="encryption", params={"key_bits": rsa_bits})
        elif last == "OAEP" and ("padding" in fn or fn == "OAEP"):
            add(c, asset_type="algorithm", algorithm="RSA-OAEP", usage="key_exchange", params={"key_bits": rsa_bits} if rsa_bits else {})
        elif last == "generate" and "ed25519privatekey" in fn.lower():
            add(c, asset_type="algorithm", algorithm="Ed25519", usage="signature")
        elif "X25519PrivateKey" in fn and last == "generate":
            add(c, asset_type="algorithm", algorithm="X25519", usage="key_exchange")
        elif fn.startswith("hashlib.") and last in HASHES:
            add(c, asset_type="algorithm", algorithm=HASHES[last], usage="hash")
        elif fn == "hashlib.new" and (n := const_arg(c, None, 0)) and str(n).lower() in HASHES:
            add(c, asset_type="algorithm", algorithm=HASHES[str(n).lower()], usage="hash")
        elif last == "new" and fn.endswith("AES.new") and any("MODE_ECB" in dotted(a) for a in [*c.args, *(k.value for k in c.keywords)]):
            add(c, asset_type="algorithm", algorithm="AES-ECB", usage="symmetric")
    return out


def scan(root, base=None) -> list[dict]:
    base = base or root
    out = []
    for p in iter_files(root, (".py",)):
        out += scan_source(p.read_text(errors="replace"), rel(p, base))
    return out
