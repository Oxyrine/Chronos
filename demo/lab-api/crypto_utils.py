"""Deliberately classical synthetic PDF path, retained as residual risk after TLS migration."""
import hashlib
import os
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def protect_fake_pdf(payload):
    wrapping_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    aes_key = AESGCM.generate_key(bit_length=256)
    wrapped = wrapping_key.public_key().encrypt(aes_key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    signer = ec.generate_private_key(ec.SECP256R1())
    signature = signer.sign(payload, ec.ECDSA(hashes.SHA256()))
    nonce = os.urandom(12)
    return {"wrapped_key": wrapped.hex(), "ciphertext": AESGCM(aes_key).encrypt(nonce, payload, None).hex(),
            "nonce": nonce.hex(), "signature": signature.hex(), "etag": hashlib.sha1(payload).hexdigest()}
