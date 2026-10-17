"""Mini St. Aster tree for discovery tests. Real St. Aster comes from Person A; this mirrors its planted crypto."""
import datetime as dt
import textwrap

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

NGINX = """\
server {
    listen 8443 ssl;
    server_name portal.staster.test;
    ssl_certificate /etc/nginx/portal.pem;
    ssl_protocols TLSv1.3 TLSv1.2;
    ssl_ecdh_curve X25519:prime256v1;
}
"""
SSHD = "Port 22\nKexAlgorithms curve25519-sha256,ecdh-sha2-nistp256\nHostKey /etc/ssh/ssh_host_rsa_key\n"
OPENSSL_CNF = "[system_default_sect]\nMinProtocol = TLSv1.2\nGroups = X25519:P-256\n"
CRYPTO_PY = textwrap.dedent('''\
    import hashlib
    from cryptography.hazmat.primitives.asymmetric import rsa, padding, ec
    from cryptography.hazmat.primitives import hashes

    KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    SIGN = ec.generate_private_key(ec.SECP256R1())

    def wrap(dek, pub):
        return pub.encrypt(dek, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))

    def etag(b):
        return hashlib.sha1(b).hexdigest()
    ''')
BILLING_JAVA = textwrap.dedent('''\
    class Billing {
        void keys() throws Exception {
            KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
            g.initialize(2048);
            Signature s = Signature.getInstance("SHA256withRSA");
            Cipher c = Cipher.getInstance("AES/ECB/PKCS5Padding");
            MessageDigest d = MessageDigest.getInstance("SHA-1");
        }
    }
    ''')
TF = 'resource "tls_private_key" "ca" {\n  algorithm = "RSA"\n  rsa_bits  = 2048\n}\n'


def _cert(key, cn="portal.staster.test"):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = dt.datetime.now(dt.timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True).sign(key, hashes.SHA256()))


@pytest.fixture
def demo_tree(tmp_path):
    d = tmp_path / "demo"
    for sub, name, text in [("portal", "nginx.conf", NGINX), ("reminders", "nginx.conf", NGINX), ("ops-ssh", "sshd_config", SSHD),
                            ("lab-api", "openssl.cnf", OPENSSL_CNF), ("lab-api", "crypto_utils.py", CRYPTO_PY),
                            ("billing", "Billing.java", BILLING_JAVA)]:
        (d / sub).mkdir(parents=True, exist_ok=True)
        (d / sub / name).write_text(text)
    (tmp_path / "infra" / "terraform").mkdir(parents=True)
    (tmp_path / "infra" / "terraform" / "main.tf").write_text(TF)
    key = rsa.generate_private_key(65537, 2048)
    cert = _cert(key)
    (d / "portal" / "portal.pem").write_bytes(
        cert.public_bytes(serialization.Encoding.PEM)
        + key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    eckey = ec.generate_private_key(ec.SECP256R1())
    (d / "ops-ssh" / "ca.der").write_bytes(_cert(eckey, "ca").public_bytes(serialization.Encoding.DER))
    (d / "portal" / "ground_truth.yaml").write_text("assets: [{algorithm: 'RSA', path: 'x'}]")  # must never be read
    return tmp_path, cert.fingerprint(hashes.SHA256()).hex()
