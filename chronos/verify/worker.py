"""Internal authenticated worker. The only service permitted a Docker socket and signing key."""
import base64
import hmac
import json
import os
import platform
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import yaml
from chronos.common import samples, store
from chronos.verify.attest import approve, bound_record, ledger, proposal_binding
from chronos.verify.checks import check, command, run_checks, ssh, tls
from chronos.verify.ledger import OpenSSLSigner, canonical, digest, locked
from chronos.verify.sandbox import root_path, sandbox


def allowed(protocol, host, port):
    data = yaml.safe_load((root_path() / 'demo/topology.yaml').read_text())
    return any(c['protocol'] == protocol and c['dst'] == host and c.get('port') == port
               and c.get('probe', True) for c in data['channels'])


def verify(proposal_id):
    start = time.monotonic()
    checks, record = [], None
    with locked(Path(store.ROOT) / 'verify-operation.lock'):
        try:
            record = bound_record(proposal_id)
            if record.get('state') == 'approved':
                raise ValueError('proposal already approved')
            rc, running = command(['docker', 'ps', '--filter', 'label=com.docker.compose.service=llm', '--format', '{{.ID}}'])
            if rc or running.strip():
                raise RuntimeError('stop the llm service before sandbox verification')
            with sandbox(record) as (host, port):
                checks = run_checks(record, host, port, host)
        except Exception as exc:
            checks.append(check('sandbox_error', False, str(exc)))
        log = Path(store.ROOT) / 'verify' / (proposal_id + '.log')
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps(checks, indent=2))
        result = {'proposal_id': proposal_id, 'status': 'passed' if checks and all(c['passed'] for c in checks) else 'failed',
                  'checks': checks, 'diff_sha256': record['diff_sha256'] if record else '',
                  'log_path': str(log), 'duration_s': round(time.monotonic() - start, 3),
                  'original_sha256': record['original_sha256'] if record else '',
                  'rendered_sha256': digest(record['rendered'].encode()) if record else '',
                  'proposal_binding_sha256': digest(proposal_binding(record)) if record else ''}
        samples.validate('verification_result', result)
        store.put('verification_' + proposal_id, result)
        if record:
            record['state'] = 'verified_awaiting_approval' if result['status'] == 'passed' else 'verification_failed'
            store.put('proposal_' + proposal_id, record)
        return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Request bodies and authorization headers are never logged.

    def reply(self, code, body):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def authenticated(self):
        token = os.environ.get('CHRONOS_WORKER_TOKEN', '')
        return bool(token) and hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token)

    def do_GET(self):
        path = urlparse(self.path)
        if path.path == '/health':
            return self.reply(200, {'status': 'ok', 'arch': platform.machine()})
        if not self.authenticated():
            return self.reply(401, {'detail': 'worker authentication required'})
        try:
            if path.path in ('/probe/tls', '/probe/ssh'):
                protocol = path.path.rsplit('/', 1)[1]
                query = parse_qs(path.query)
                host, port = query['host'][0], int(query['port'][0])
                if not allowed(protocol, host, port):
                    return self.reply(403, {'detail': 'endpoint not allow-listed'})
                rc, output = tls(host, port, 'X25519MLKEM768:X25519') if protocol == 'tls' else ssh(host, port)
                return self.reply(200, {'output': output, 'returncode': rc})
            if path.path == '/ledger':
                return self.reply(200, ledger().entries())
            if path.path == '/ledger/verify':
                return self.reply(200, ledger().verify())
            if path.path == '/public-key':
                return self.reply(200, {'algorithm': 'ML-DSA-65', 'pem': OpenSSLSigner().public.read_text()})
            match = re.fullmatch(r'/verifications/(P-\d{4})', path.path)
            if match:
                result = store.get('verification_' + match[1])
                return self.reply(200 if result else 404, result or {'detail': 'not found'})
            self.reply(404, {'detail': 'not found'})
        except Exception as exc:
            self.reply(400, {'detail': str(exc)})

    def do_POST(self):
        if not self.authenticated():
            return self.reply(401, {'detail': 'worker authentication required'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > 65536:
                return self.reply(413, {'detail': 'request too large'})
            body = json.loads(self.rfile.read(length) or b'{}')
            path = urlparse(self.path).path
            match = re.fullmatch(r'/(verify|approve)/(P-\d{4})', path)
            if match:
                action, proposal_id = match.groups()
                if action == 'verify':
                    bound_record(proposal_id)
                    store.put('verification_' + proposal_id, {'proposal_id': proposal_id, 'status': 'pending'})
                    threading.Thread(target=verify, args=(proposal_id,), daemon=True).start()
                    return self.reply(202, {'proposal_id': proposal_id, 'status': 'pending'})
                return self.reply(200, approve(proposal_id, body.get('user', {})))
            if path == '/sign':
                # Restricted to attestation evidence, never arbitrary shell, keys or file paths.
                entry = body['entry']
                samples.validate('attestation', dict(entry, sig_b64='pending'))
                signature = OpenSSLSigner().sign(canonical(entry))
                return self.reply(200, {'sig_b64': base64.b64encode(signature).decode()})
            if path == '/verify-sig':
                valid = OpenSSLSigner().verify(canonical(body['entry']), base64.b64decode(body['sig_b64'], validate=True))
                return self.reply(200, {'valid': valid})
            self.reply(404, {'detail': 'not found'})
        except PermissionError as exc:
            self.reply(403, {'detail': str(exc)})
        except Exception as exc:
            self.reply(400, {'detail': str(exc)})


if __name__ == '__main__':
    if len(os.environ.get('CHRONOS_WORKER_TOKEN', '')) < 24:
        raise SystemExit('CHRONOS_WORKER_TOKEN must contain at least 24 characters')
    ThreadingHTTPServer(('0.0.0.0', 8090), Handler).serve_forever()
