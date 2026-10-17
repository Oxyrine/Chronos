"""Scanner: certificates and key material (PEM, DER, PKCS#12, JKS). Reads file contents only; never opens network connections."""
import hashlib
import logging
import os
import re

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, rsa, x448, x25519
from cryptography.hazmat.primitives.serialization import pkcs12

from chronos.discovery.common import asset, iter_files, rel

log = logging.getLogger(__name__)
SOURCE = "certs_keys"
SUFFIXES = (".pem", ".crt", ".cer", ".key", ".der", ".p12", ".pfx", ".jks")
PEM_BLOCK = re.compile(rb"-----BEGIN ([A-Z0-9 ]+)-----.*?-----END \1-----", re.S)
# Passwords tried on keystores that live in the scanned tree; override for your own stores.
PASSWORDS = [p.encode() for p in os.environ.get("CHRONOS_KEYSTORE_PASSWORDS", "changeit").split(",")]


def key_info(key) -> tuple[str, dict]:
    if isinstance(key, rsa.RSAPublicKey | rsa.RSAPrivateKey):
        return "RSA", {"key_bits": key.key_size}
    if isinstance(key, ec.EllipticCurvePublicKey | ec.EllipticCurvePrivateKey):
        return "ECDSA", {"curve": key.curve.name, "key_bits": key.curve.key_size}
    if isinstance(key, ed25519.Ed25519PublicKey | ed25519.Ed25519PrivateKey):
        return "Ed25519", {}
    if isinstance(key, ed448.Ed448PublicKey | ed448.Ed448PrivateKey):
        return "Ed448", {}
    if isinstance(key, x25519.X25519PublicKey | x25519.X25519PrivateKey):
        return "X25519", {}
    if isinstance(key, x448.X448PublicKey | x448.X448PrivateKey):
        return "X448", {}
    if isinstance(key, dsa.DSAPublicKey | dsa.DSAPrivateKey):
        return "DSA", {"key_bits": key.key_size}
    return type(key).__name__, {}


def cert_asset(cert: x509.Certificate, path: str, line: int | None = None) -> dict:
    alg, params = key_info(cert.public_key())
    try:
        ca = cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        ca = False
    params |= {
        "signature_algorithm": cert.signature_algorithm_oid._name,
        "subject": cert.subject.rfc4514_string(), "issuer": cert.issuer.rfc4514_string(),
        "not_before": cert.not_valid_before_utc.isoformat(), "not_after": cert.not_valid_after_utc.isoformat(),
        "is_ca": ca, "certificate_format": "X.509",
    }
    fp = cert.fingerprint(hashes.SHA256()).hex()
    return asset(path=path, line=line, asset_type="certificate", algorithm=alg, usage="signature", source=SOURCE,
                 params=params, fingerprint=fp)


def key_asset(key, path: str, line: int | None = None) -> dict:
    alg, params = key_info(key)
    params["material"] = "private-key"
    fp = hashlib.sha256(key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()
    return asset(path=path, line=line, asset_type="related-crypto-material", algorithm=alg, usage="signature",
                 source=SOURCE, params=params, fingerprint=f"key:{fp}")


def _pem(data: bytes, path: str):
    for m in PEM_BLOCK.finditer(data):
        label, block = m.group(1).decode(), m.group(0)
        line = data[: m.start()].count(b"\n") + 1
        try:
            if label in ("CERTIFICATE", "TRUSTED CERTIFICATE"):
                yield cert_asset(x509.load_pem_x509_certificate(block), path, line)
            elif label.endswith("PRIVATE KEY") and "ENCRYPTED" not in label:
                yield key_asset(serialization.load_pem_private_key(block, None), path, line)
            elif label == "PUBLIC KEY":
                alg, params = key_info(serialization.load_pem_public_key(block))
                yield asset(path=path, line=line, asset_type="related-crypto-material", algorithm=alg, usage="signature",
                            source=SOURCE, params={**params, "material": "public-key"})
        except Exception as e:  # unreadable block: report, keep scanning
            log.warning("%s:%s %s block unreadable: %s", path, line, label, e)


def _p12(data: bytes, path: str):
    for pw in [None, *PASSWORDS]:
        try:
            key, cert, extra = pkcs12.load_key_and_certificates(data, pw)
        except Exception:
            continue
        if key is not None:
            yield key_asset(key, path)
        for c in [cert, *(extra or [])]:
            if c is not None:
                yield cert_asset(c, path)
        return
    log.warning("%s: PKCS#12 store not readable with the configured passwords", path)


def _jks(path_obj, path: str):
    try:
        import jks
    except ImportError:
        log.warning("%s: pyjks not installed, keystore skipped (source scanners still cover its Java usage)", path)
        return
    for pw in PASSWORDS:
        try:
            ks = jks.KeyStore.load(str(path_obj), pw.decode())
        except Exception:
            continue
        for entry in ks.entries.values():
            if isinstance(entry, jks.PrivateKeyEntry):
                yield key_asset(serialization.load_der_private_key(entry.pkey_pkcs8, None), path)
                for _, der in entry.cert_chain:
                    yield cert_asset(x509.load_der_x509_certificate(der), path)
            elif isinstance(entry, jks.TrustedCertEntry):
                yield cert_asset(x509.load_der_x509_certificate(entry.cert), path)
        return
    log.warning("%s: JKS not readable with the configured passwords", path)


def scan(root, base=None) -> list[dict]:
    base = base or root
    out = []
    for p in iter_files(root, SUFFIXES):
        path, data = rel(p, base), p.read_bytes()
        if p.suffix.lower() in (".p12", ".pfx"):
            out += _p12(data, path)
        elif p.suffix.lower() == ".jks":
            out += _jks(p, path)
        elif b"-----BEGIN" in data[:4096]:
            out += _pem(data, path)
        elif p.suffix.lower() in (".der", ".cer", ".crt"):
            try:
                out.append(cert_asset(x509.load_der_x509_certificate(data), path))
            except Exception as e:
                log.warning("%s: not a DER certificate: %s", path, e)
    return out
