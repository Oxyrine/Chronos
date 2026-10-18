"""Canonical, hash-chained evidence. A signature attests evidence, not universal safety."""
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading

_LOCK = threading.RLock()


def canonical(entry):
    return json.dumps({k: v for k, v in entry.items() if k not in ('sig_b64', 'entry_hash')},
                      sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


@contextlib.contextmanager
def locked(path):
    """Thread and process lock; lock file survives replacement of data files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, path.open('a+b') as handle:
        if os.name == 'posix':
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'posix':
                fcntl.flock(handle, fcntl.LOCK_UN)


class OpenSSLSigner:
    """Private key stays in the worker. Never accepts a shell command."""
    def __init__(self, private=None, public=None):
        self.private = Path(private or os.environ.get('CHRONOS_SIGNING_KEY', '/keys/chronos-mldsa65.key'))
        self.public = Path(public or os.environ.get('CHRONOS_PUBLIC_KEY', '/keys/chronos-mldsa65.pub'))
        self._checked = False

    def _check_algorithm(self):
        if not self._checked:
            cp = subprocess.run(['openssl', 'pkey', '-pubin', '-in', str(self.public), '-text', '-noout'],
                                capture_output=True, text=True, check=True, timeout=20)
            if 'ML-DSA-65' not in cp.stdout:
                raise RuntimeError('ledger requires an ML-DSA-65 public key')
            self._checked = True

    def sign(self, data):
        self._check_algorithm()
        if not self.private.exists():
            raise RuntimeError('ML-DSA signing key is unavailable')
        if os.name == 'posix' and self.private.stat().st_mode & 0o077:
            raise RuntimeError('ML-DSA private key must have mode 600')
        # ML-DSA uses one-shot signing: OpenSSL must know the complete input length.
        # A pipe/stdin cannot provide that size; use a private temporary regular file.
        with tempfile.TemporaryDirectory() as tmp:
            message = Path(tmp) / 'message'
            message.write_bytes(data)
            return subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(self.private),
                                   '-in', str(message)], capture_output=True, check=True, timeout=20).stdout

    def verify(self, data, signature):
        self._check_algorithm()
        with tempfile.TemporaryDirectory() as tmp:
            message, sig = Path(tmp) / 'message', Path(tmp) / 'signature'
            message.write_bytes(data)
            sig.write_bytes(signature)
            cp = subprocess.run(['openssl', 'pkeyutl', '-verify', '-rawin', '-pubin', '-inkey',
                                 str(self.public), '-in', str(message), '-sigfile', str(sig)],
                                capture_output=True, timeout=20)
            return cp.returncode == 0


class Ledger:
    def __init__(self, path, signer):
        self.path, self.signer = Path(path), signer

    def entries(self):
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def verify(self):
        previous = '0' * 64
        try:
            lines = self.path.read_text().splitlines() if self.path.exists() else []
            for number, line in enumerate(lines, 1):
                entry = json.loads(line)
                from chronos.common.samples import validate
                validate('attestation', entry)
                if (entry['seq'] != number or entry['prev_hash'] != previous or
                    entry.get('entry_hash') != digest(entry) or
                    not self.signer.verify(canonical(entry), base64.b64decode(entry['sig_b64'], validate=True))):
                    return {'chain_ok': False, 'bad_seq': number}
                previous = entry['entry_hash']
        except Exception:
            return {'chain_ok': False, 'bad_seq': locals().get('number', 1)}
        return {'chain_ok': True, 'bad_seq': None, 'entries': len(lines), 'head': previous}

    def append(self, evidence):
        with locked(self.path.with_suffix('.lock')):
            status = self.verify()
            if not status['chain_ok']:
                raise ValueError('refusing to append to a corrupted ledger')
            entry = dict(evidence, seq=status['entries'] + 1, prev_hash=status['head'], alg='ML-DSA-65')
            entry.pop('sig_b64', None)
            entry.pop('entry_hash', None)
            entry['entry_hash'] = digest(entry)
            entry['sig_b64'] = base64.b64encode(self.signer.sign(canonical(entry))).decode()
            if not self.signer.verify(canonical(entry), base64.b64decode(entry['sig_b64'])):
                raise RuntimeError('new attestation signature failed verification')
            from chronos.common.samples import validate
            validate('attestation', entry)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(entry, sort_keys=True) + '\n')
                handle.flush()
                os.fsync(handle.fileno())
            return entry
