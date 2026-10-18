import hashlib

import pytest

from chronos.discovery import certs_keys, python_ast


@pytest.mark.parametrize('source,bits', [
    ('from cryptography.hazmat.primitives.ciphers.aead import AESGCM\nk = AESGCM.generate_key(bit_length=256)',256),
    ('from cryptography.hazmat.primitives.ciphers.aead import AESGCM as GCM\nk = GCM.generate_key(128)',128),
    ('from cryptography.hazmat.primitives.ciphers import aead\nk = aead.AESGCM.generate_key(bit_length=192)',192),
    ('import cryptography.hazmat.primitives.ciphers.aead as a\nk = a.AESGCM.generate_key(256)',256),
])
def test_aes_gcm_key_generation(source,bits):
    result=python_ast.scan_source(source,'demo/lab-api/crypto_utils.py')
    assert len(result)==1
    assert result[0]['algorithm']==f'AES-{bits}-GCM'
    assert result[0]['params']['key_bits']==bits
    assert result[0]['usage']=='symmetric' and result[0]['line']==2


def test_unknown_aes_key_length_is_not_invented():
    source='from cryptography.hazmat.primitives.ciphers.aead import AESGCM\nk = AESGCM.generate_key(bit_length=chosen_bits)'
    result=python_ast.scan_source(source,'example.py')[0]
    assert result['algorithm']=='AES-GCM' and result['params']=={} and result['status']=='vulnerable'
    assert python_ast.scan_source('class AESGCM: pass\nk = AESGCM.generate_key(256)','unrelated.py')==[]


@pytest.fixture
def java_style_jks(tmp_path):
    jks=pytest.importorskip('jks')
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from conftest import _cert
    from pyasn1.codec.der import decoder,encoder
    from pyasn1_modules import rfc5208
    key=rsa.generate_private_key(65537,2048)
    certificate=_cert(key).public_bytes(serialization.Encoding.DER)
    private=key.private_bytes(serialization.Encoding.DER,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    entry=jks.PrivateKeyEntry.new('billing',[certificate],private,'pkcs8')
    entry.encrypt('changeit')
    # Reproduce Java's valid AlgorithmIdentifier with omitted optional params.
    info=decoder.decode(entry._encrypted,asn1Spec=rfc5208.EncryptedPrivateKeyInfo())[0]
    algorithm=info['encryptionAlgorithm']['algorithm']
    info['encryptionAlgorithm'].clear()
    info['encryptionAlgorithm']['algorithm']=algorithm
    entry._encrypted=encoder.encode(info)
    path=tmp_path/'billing.jks'
    path.write_bytes(jks.KeyStore.new('jks',[entry]).saves('changeit'))
    return path


def test_jks_inventory_does_not_need_private_key_decryption(java_style_jks,monkeypatch):
    path=java_style_jks
    monkeypatch.setattr(certs_keys,'PASSWORDS',[b'changeit'])
    before=hashlib.sha256(path.read_bytes()).digest()
    result=certs_keys.scan(path.parent,path.parent)
    assert {item['asset_type'] for item in result}=={'certificate','related-crypto-material'}
    assert len(result)==2 and all(item['algorithm']=='RSA' and item['params']['key_bits']==2048 for item in result)
    private=next(item for item in result if item['asset_type']=='related-crypto-material')
    assert private['params']['encrypted'] and private['params']['key_identity_source']=='certificate-chain'
    assert hashlib.sha256(path.read_bytes()).digest()==before


def test_jks_still_checks_password_and_integrity(java_style_jks,monkeypatch):
    path=java_style_jks
    monkeypatch.setattr(certs_keys,'PASSWORDS',[b'wrong-password'])
    assert certs_keys.scan(path.parent,path.parent)==[]
    monkeypatch.setattr(certs_keys,'PASSWORDS',[b'changeit'])
    content=bytearray(path.read_bytes()); content[-1]^=1; path.write_bytes(content)
    assert certs_keys.scan(path.parent,path.parent)==[]
