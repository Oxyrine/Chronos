"""Real protocol checks. Success requires observed negotiation and certificate trust."""
import json
import os
import re
import subprocess
import time
from urllib.request import Request, urlopen
from chronos.risk.catalog import kex_class


def command(argv, input=None, timeout=25):
    cp = subprocess.run(argv, input=input, text=True, capture_output=True, timeout=timeout)
    return cp.returncode, cp.stdout + cp.stderr


def negotiated(output, protocol='tls'):
    pattern = (r'kex: algorithm:\s*([^\s]+)' if protocol == 'ssh' else
               r'(?:Negotiated TLS1\.3 group|Server Temp Key|Peer Temp Key):\s*([^\s,]+)')
    match = re.search(pattern, output, re.I)
    return match.group(1) if match else None


def tls(host, port, groups, server=None, health=False):
    server = server or host.replace('sandbox-', '') + '.staster.test'
    cmd = ['openssl', 's_client', '-connect', f'{host}:{port}', '-servername', server,
           '-groups', groups, '-verify_return_error', '-verify_hostname', server,
           '-CAfile', os.environ.get('CHRONOS_CA_FILE', '/keys/ca.pem')]
    if health:
        cmd += ['-quiet', '-ign_eof']
        payload = f'GET /health HTTP/1.1\r\nHost: {server}\r\nConnection: close\r\n\r\n'
    else:
        cmd += ['-brief']
        payload = ''
    return command(cmd, payload)


def ssh(host, port, kex=None):
    argv = ['ssh', '-vv', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=7',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=ops-ssh',
            '-o', 'UserKnownHostsFile=' + os.environ.get('CHRONOS_SSH_KNOWN_HOSTS', '/keys/known_hosts'),
            '-i', os.environ.get('CHRONOS_SSH_PROBE_KEY', '/keys/probe_key'), '-p', str(port)]
    if kex:
        argv += ['-o', 'KexAlgorithms=' + kex]
    return command(argv + [f'probe@{host}', 'true'])


def check(name, passed, evidence):
    return {'name': name, 'passed': bool(passed), 'evidence': evidence}


def wait_ready(container, run=command, timeout=40):
    deadline = time.monotonic() + timeout
    state = ''
    while time.monotonic() < deadline:
        rc, state = run(['docker', 'inspect', '--format',
                         '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}', container])
        if rc == 0 and state.strip() in ('healthy', 'running'):
            return
        if rc == 0 and state.strip() in ('unhealthy', 'exited', 'dead'):
            raise RuntimeError('container not ready: ' + state)
        time.sleep(1)
    raise RuntimeError('container readiness timed out: ' + state)


def run_checks(record, host, port, container, run=command):
    template = record['proposal']['template_id']
    checks = []
    if template == 'T1_nginx_hybrid_groups':
        rc, output = run(['docker', 'exec', container, 'nginx', '-t'])
        checks.append(check('config_syntax', rc == 0, output))
        rc, output = tls(host, port, 'X25519MLKEM768')
        group = negotiated(output)
        checks.append(check('pq_handshake', rc == 0 and group and kex_class(group) == 'hybrid', output))
        rc, output = tls(host, port, 'X25519')
        params = record['proposal'].get('params', {})
        strict = params.get('protocols') == ['TLSv1.3'] and params.get('groups') == ['X25519MLKEM768']
        rejection = rc != 0 and bool(re.search(r'no suitable key share|handshake failure|no shared cipher|alert.*(40|70|80)', output, re.I))
        checks.append(check('classical_rejected' if strict else 'classical_compat',
                            rejection if strict else rc == 0 and negotiated(output) == 'X25519', output))
        rc, output = tls(host, port, 'X25519MLKEM768', health=True)
        checks.append(check('health', rc == 0 and bool(re.search(r'HTTP/1\.[01] 200', output)), output))
    elif template == 'T2_sshd_hybrid_kex':
        rc, output = run(['docker', 'exec', container, '/usr/sbin/sshd', '-t'])
        checks.append(check('config_syntax', rc == 0, output))
        rc, output = ssh(host, port, 'mlkem768x25519-sha256')
        checks.append(check('pq_handshake', rc == 0 and negotiated(output, 'ssh') == 'mlkem768x25519-sha256', output))
        rc, output = ssh(host, port, 'curve25519-sha256')
        checks.append(check('classical_compat', rc == 0 and negotiated(output, 'ssh') == 'curve25519-sha256', output))
    elif template == 'T3_client_tls_groups':
        from pathlib import Path
        trace = record['proposal']['proposal_id']
        request = Request(f'http://{host}:{port}/forward/1?trace={trace}', data=b'', method='POST')
        try:
            with urlopen(request, timeout=20) as response:
                evidence = response.read().decode()
                passed = response.status == 200
        except Exception as exc:
            evidence, passed = str(exc), False
        checks.append(check('outbound_request', passed, evidence))
        root = Path(os.environ.get('CHRONOS_OUT', 'out')) / 'logs' / 'partner-lab'
        matches = []
        for log in root.glob('*.log'):
            for line in log.read_text(errors='replace').splitlines():
                try:
                    row = json.loads(line)
                    if f'trace={trace}' in row.get('request_uri', ''):
                        matches.append(row)
                except ValueError:
                    pass
        checks.append(check('outbound_pq_negotiation', bool(matches) and
                            all(kex_class(row.get('ssl_curve', '')) == 'hybrid' for row in matches), json.dumps(matches)))
    else:
        raise ValueError('unsupported template')
    return checks
