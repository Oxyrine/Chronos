"""Scanner: crypto-relevant settings in nginx, sshd, openssl.cnf, java.security, postgresql.conf and Terraform."""
import re

from chronos.discovery.common import asset, iter_files, rel
from chronos.risk.catalog import kex_class

SOURCE = "configs"
SUFFIXES = (".conf", ".cnf", ".security", ".tf")
NAMES = ("sshd_config", "nginx.conf", "openssl.cnf", "java.security", "postgresql.conf")

NGINX_CURVE = re.compile(r"^\s*ssl_ecdh_curve\s+([^;#]+);", re.I)
NGINX_PROTO = re.compile(r"^\s*ssl_protocols\s+([^;#]+);", re.I)
SSHD_KEX = re.compile(r"^\s*KexAlgorithms\s+(\S+)", re.I)
OPENSSL_GROUPS = re.compile(r"^\s*(?:Groups|Curves)\s*=\s*(\S+)", re.I)
JAVA_GROUPS = re.compile(r"^\s*jdk\.tls\.namedGroups\s*=\s*(.+)$")
PG_CURVE = re.compile(r"^\s*ssl_(?:ecdh_curve|groups)\s*=\s*'?([^'#\n]+)'?", re.I)
TF_KEY = re.compile(r'resource\s+"tls_private_key"\s+"(\w+)"\s*\{(.*?)\n\}', re.S)


def _groups(raw: str, sep: str) -> list[str]:
    return [g.strip().lstrip("+-^") for g in raw.strip().split(sep) if g.strip()]


def kex_asset(path, line, raw, sep, protocol) -> dict:
    """A key-exchange list. Resistant when any hybrid/PQ group is offered; the classical fallback is recorded, not hidden."""
    groups = _groups(raw, sep)
    classes = [kex_class(g) for g in groups]
    resistant = any(c != "classical" for c in classes)
    return asset(path=path, line=line, asset_type="protocol", algorithm=sep.join(groups), usage="key_exchange",
                 source=SOURCE, status="resistant" if resistant else "vulnerable",
                 params={"groups": groups, "protocol": protocol, "classical_accepted": "classical" in classes})


def scan_text(text: str, path: str, filename: str) -> list[dict]:
    out = []
    name = filename.lower()
    for no, raw in enumerate(text.splitlines(), 1):
        if name.endswith(".tf"):
            break
        if name == "sshd_config" and (m := SSHD_KEX.match(raw)):
            out.append(kex_asset(path, no, m.group(1), ",", "ssh"))
        elif name == "openssl.cnf" and (m := OPENSSL_GROUPS.match(raw)):
            out.append(kex_asset(path, no, m.group(1), ":", "tls"))
        elif name == "java.security" and (m := JAVA_GROUPS.match(raw)):
            out.append(kex_asset(path, no, m.group(1), ",", "tls"))
        elif name == "postgresql.conf" and (m := PG_CURVE.match(raw)):
            out.append(kex_asset(path, no, m.group(1), ":", "tls"))
        elif name.endswith(".conf") and name not in ("postgresql.conf",):
            if m := NGINX_CURVE.match(raw):
                out.append(kex_asset(path, no, m.group(1), ":", "tls"))
            elif m := NGINX_PROTO.match(raw):
                protos = m.group(1).split()
                out.append(asset(path=path, line=no, asset_type="protocol", algorithm=" ".join(protos), usage="protocol",
                                 source=SOURCE, status="resistant", params={"protocol": "tls", "versions": protos}))
    if name.endswith(".tf"):
        for m in TF_KEY.finditer(text):
            body, line = m.group(2), text[: m.start()].count("\n") + 1
            alg = re.search(r'algorithm\s*=\s*"(\w+)"', body)
            bits = re.search(r"rsa_bits\s*=\s*(\d+)", body)
            curve = re.search(r'ecdsa_curve\s*=\s*"(\w+)"', body)
            if alg:
                a = alg.group(1).upper()
                params = {"resource": m.group(1)}
                if bits:
                    params["key_bits"] = int(bits.group(1))
                if curve:
                    params["curve"] = curve.group(1)
                out.append(asset(path=path, line=line, asset_type="related-crypto-material", algorithm=a, usage="signature",
                                 source=SOURCE, params=params))
    return out


def scan(root, base=None) -> list[dict]:
    base = base or root
    out = []
    for p in iter_files(root, SUFFIXES, NAMES):
        # nginx files are *.conf; sshd_config/openssl.cnf/etc are matched by name
        out += scan_text(p.read_text(errors="replace"), rel(p, base), p.name)
    return out
