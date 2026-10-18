import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import pytest
from chronos.common import store
from chronos.verify import attest, checks, sandbox, worker


def record():
    return {'proposal': {'proposal_id': 'P-0001', 'template_id': 'T1_nginx_hybrid_groups',
                         'params': {'mode': 'compatibility'}, 'model': 'rules-only', 'rationale': 'reviewed rationale'},
            'finding': {'finding_id': 'F-0001'}, 'target': 'demo/portal/nginx.conf',
            'original_sha256': '1' * 64, 'rendered': 'safe', 'diff': 'diff',
            'diff_sha256': attest.digest(b'diff')}


@pytest.mark.parametrize('text,expected', [
    ('Negotiated TLS1.3 group: X25519MLKEM768', 'X25519MLKEM768'),
    ('Server Temp Key: X25519, 253 bits', 'X25519'), ('no group', None)])
def test_actual_negotiation_parser(text, expected):
    assert checks.negotiated(text) == expected


def test_strict_rejection_cannot_be_certificate_error(monkeypatch):
    patch = record()
    patch['proposal']['params'] = {'protocols': ['TLSv1.3'], 'groups': ['X25519MLKEM768']}
    monkeypatch.setattr(checks, 'tls', lambda host, port, groups, **kw:
                        (1, 'certificate verify failed') if groups == 'X25519' else
                        (0, 'HTTP/1.1 200 OK' if kw.get('health') else 'Negotiated TLS1.3 group: X25519MLKEM768'))
    result = checks.run_checks(patch, 'sandbox-portal', 8443, 'sandbox-portal', lambda argv: (0, 'syntax ok'))
    assert not next(row for row in result if row['name'] == 'classical_rejected')['passed']


def test_compat_requires_observed_classical_group(monkeypatch):
    monkeypatch.setattr(checks, 'tls', lambda host, port, groups, **kw:
                        (0, 'HTTP/1.1 200 OK' if kw.get('health') else 'connection succeeded without group'))
    result = checks.run_checks(record(), 'sandbox-portal', 8443, 'sandbox-portal', lambda argv: (0, 'syntax ok'))
    assert not next(row for row in result if row['name'] == 'pq_handshake')['passed']
    assert not next(row for row in result if row['name'] == 'classical_compat')['passed']


def test_allowlist_excludes_client_pinned_and_untrusted_hosts(tmp_path, monkeypatch):
    (tmp_path / 'demo').mkdir()
    (tmp_path / 'demo/topology.yaml').write_text('channels:\n- {protocol: tls, dst: portal, port: 8443}\n- {protocol: tls, dst: partner-lab, port: 8443, probe: false}\n')
    monkeypatch.setenv('CHRONOS_ROOT', str(tmp_path))
    assert worker.allowed('tls', 'portal', 8443)
    assert not worker.allowed('tls', 'portal;id', 8443)
    assert not worker.allowed('tls', 'partner-lab', 8443)
    assert not worker.allowed('tls', '169.254.169.254', 80)


def test_sandbox_drops_published_ports_and_maps_copy(tmp_path):
    root = tmp_path
    work = tmp_path / 'out/sandbox/P-0001'
    work.mkdir(parents=True)
    spec = {'services': {'portal': {'image': 'chronos-portal:local', 'ports': ['8443:8443'],
            'privileged': True, 'container_name': 'portal', 'volumes': [
                {'type': 'bind', 'source': str(root / 'demo/portal/nginx.conf'), 'target': '/etc/nginx/nginx.conf', 'read_only': True}]}}}
    data = sandbox.configuration(root, record(), work, lambda argv: (0, json.dumps(spec)))
    service = data['services']['sandbox-portal']
    assert 'ports' not in service and 'privileged' not in service
    assert service['container_name'] == 'sandbox-portal'
    assert service['volumes'][0]['source'] == str(work / 'portal/nginx.conf')
    assert service['networks'] == {'staster': {'aliases': ['sandbox-portal']}}


def test_sandbox_rejects_socket_mount(tmp_path):
    spec = {'services': {'portal': {'image': 'image', 'volumes': [
        {'type': 'bind', 'source': '/var/run/docker.sock', 'target': '/var/run/docker.sock'}]}}}
    with pytest.raises(ValueError, match='unexpected sandbox bind'):
        sandbox.configuration(tmp_path, record(), tmp_path, lambda argv: (0, json.dumps(spec)))


def test_approval_enforces_role_before_side_effects():
    with pytest.raises(PermissionError):
        attest.approve('P-0001', {'sub': 'viewer', 'role': 'viewer'})


def test_approval_rejects_changed_verified_diff(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setenv('CHRONOS_ROOT', str(tmp_path))
    patch = record()
    monkeypatch.setattr(attest, 'bound_record', lambda pid: patch)
    result = {'proposal_id': 'P-0001', 'status': 'passed', 'checks': [], 'diff_sha256': 'changed',
              'log_path': 'out/log', 'duration_s': 1}
    store.put('verification_P-0001', result)
    with pytest.raises(ValueError, match='content changed'):
        attest.approve('P-0001', {'sub': 'secops', 'role': 'security_engineer'})


def test_failed_verification_does_not_touch_demo(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'out')
    monkeypatch.setenv('CHRONOS_ROOT', str(tmp_path))
    target = tmp_path / 'demo/portal/nginx.conf'
    target.parent.mkdir(parents=True)
    target.write_text('original')
    monkeypatch.setattr(worker, 'bound_record', lambda pid: (_ for _ in ()).throw(ValueError('bad group')))
    result = worker.verify('P-0001')
    assert result['status'] == 'failed'
    assert target.read_text() == 'original'


def test_postdeploy_failure_restores_original_and_recreates(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'out')
    monkeypatch.setenv('CHRONOS_ROOT', str(tmp_path))
    target = tmp_path / 'demo/portal/nginx.conf'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'original')
    patch = record()
    monkeypatch.setattr(attest, 'bound_record', lambda pid: patch)
    verification = {'proposal_id': 'P-0001', 'status': 'passed', 'checks': [{'name': 'sandbox', 'passed': True, 'evidence': 'ok'}], 'diff_sha256': patch['diff_sha256'],
                    'log_path': 'log', 'duration_s': 1, 'original_sha256': patch['original_sha256'],
                    'rendered_sha256': attest.digest(patch['rendered'].encode()),
                    'proposal_binding_sha256': attest.digest(attest.proposal_binding(patch))}
    store.put('verification_P-0001', verification)
    calls = []
    def runner(argv, **kwargs):
        calls.append((argv, target.read_bytes()))
        return 0, 'recreated'
    monkeypatch.setattr(attest, 'run_checks', lambda *args: [{'name': 'health', 'passed': False}])
    monkeypatch.setattr(attest, 'wait_ready', lambda *args: None)
    with pytest.raises(RuntimeError, match='post-deploy checks failed'):
        attest.approve('P-0001', {'sub': 'secops', 'role': 'security_engineer'}, run=runner)
    assert target.read_bytes() == b'original'
    assert [body for _, body in calls] == [b'safe', b'original']
    assert all('--force-recreate' in argv for argv, _ in calls)
    assert store.get('proposal_P-0001')['state'] == 'apply_failed'


def test_api_denies_non_security_engineer_even_in_sample_mode(monkeypatch):
    from fastapi import HTTPException
    from chronos.api.routers.verify import approval
    monkeypatch.setenv('CHRONOS_USE_SAMPLES', '1')
    with pytest.raises(HTTPException) as exc:
        approval('P-0001', {'sub': 'viewer', 'role': 'viewer'})
    assert exc.value.status_code == 403


def test_evidence_archive_preserves_exact_bytes_and_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    patch = record()
    verification = {'status': 'passed', 'checks': [{'passed': True, 'evidence': 'original'}]}
    cbom_bytes = b'{"serialNumber":"scan-one"}'
    archive = attest.archive_evidence('P-0001', patch, verification, cbom_bytes)
    verification_path = Path(archive['verification']['path'])
    assert verification_path.read_bytes() == attest.json_bytes(verification)
    assert Path(archive['cbom']['path']).read_bytes() == cbom_bytes
    assert archive['verification']['sha256'] == attest.digest(verification)
    assert attest.archive_evidence('P-0001', patch, verification, cbom_bytes) == archive
    # A later scan gets a distinct path; the earlier signed CBOM remains retrievable.
    next_archive = attest.archive_evidence('P-0001', patch, verification, b'{"serialNumber":"scan-two"}')
    assert next_archive['cbom']['path'] != archive['cbom']['path']
    assert Path(archive['cbom']['path']).read_bytes() == cbom_bytes
    verification_path.chmod(0o666)
    verification_path.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='immutable evidence'):
        attest.archive_evidence('P-0001', patch, verification, cbom_bytes)


@pytest.mark.parametrize('field', ['model', 'rationale'])
def test_reviewed_proposal_metadata_is_bound_to_verification(tmp_path, monkeypatch, field):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setenv('CHRONOS_ROOT', str(tmp_path))
    patch = record()
    verification = {'proposal_id': 'P-0001', 'status': 'passed', 'checks': [], 'diff_sha256': patch['diff_sha256'],
                    'log_path': 'log', 'duration_s': 1, 'original_sha256': patch['original_sha256'],
                    'rendered_sha256': attest.digest(patch['rendered'].encode()),
                    'proposal_binding_sha256': attest.digest(attest.proposal_binding(patch))}
    store.put('verification_P-0001', verification)
    patch['proposal'][field] = 'changed after verification'
    monkeypatch.setattr(attest, 'bound_record', lambda pid: patch)
    with pytest.raises(ValueError, match='content changed'):
        attest.approve('P-0001', {'sub': 'secops', 'role': 'security_engineer'})


@pytest.mark.parametrize('state_write_fails', [False, True])
def test_approval_archives_local_rescan_result_despite_concurrent_global_write(tmp_path, monkeypatch, state_write_fails):
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'out')
    monkeypatch.setenv('CHRONOS_ROOT', str(tmp_path))
    target = tmp_path / 'demo/portal/nginx.conf'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'original')
    patch = record()
    verification = {'proposal_id': 'P-0001', 'status': 'passed',
                    'checks': [{'name': 'sandbox', 'passed': True, 'evidence': 'ok'}],
                    'diff_sha256': patch['diff_sha256'], 'log_path': 'log', 'duration_s': 1,
                    'original_sha256': patch['original_sha256'],
                    'rendered_sha256': attest.digest(patch['rendered'].encode()),
                    'proposal_binding_sha256': attest.digest(attest.proposal_binding(patch))}
    store.put('verification_P-0001', verification)
    store.put('cbom', {'serialNumber': 'concurrent-stale-scan'})
    monkeypatch.setattr(attest, 'bound_record', lambda pid: patch)
    monkeypatch.setattr(attest, 'wait_ready', lambda *args: None)
    monkeypatch.setattr(attest, 'run_checks', lambda *args: [{'name': 'health', 'passed': True, 'evidence': 'ok'}])
    if state_write_fails:
        actual_put = store.put
        def failing_put(kind, value):
            if kind == 'proposal_P-0001':
                raise OSError('injected state write failure')
            return actual_put(kind, value)
        monkeypatch.setattr(store, 'put', failing_put)
    class EvidenceLedger:
        def append(self, entry):
            return entry
    entry = attest.approve('P-0001', {'sub': 'secops', 'role': 'security_engineer'},
                            run=lambda *args, **kwargs: (0, 'ok'),
                            rescan=lambda: {'cbom': {'serialNumber': 'the-actual-postdeploy-scan'}},
                            evidence_ledger=EvidenceLedger())
    archived_cbom = Path(entry['evidence_files']['cbom']['path']).read_bytes()
    assert json.loads(archived_cbom)['serialNumber'] == 'the-actual-postdeploy-scan'
    assert attest.digest(archived_cbom) == entry['cbom_sha256']
    assert attest.digest(Path(entry['evidence_files']['verification']['path']).read_bytes()) == entry['verification_sha256']
    assert target.read_bytes() == b'safe'
    if state_write_fails:
        recovery = json.loads((store.ROOT / 'state_recovery/P-0001.json').read_text())
        assert recovery['state'] == 'approved'
        assert recovery['record']['attestation'] == entry
    else:
        assert store.get('proposal_P-0001')['state'] == 'approved'


@pytest.fixture
def evidence_download(tmp_path, monkeypatch):
    from chronos.api.routers import verify as api
    monkeypatch.setenv('CHRONOS_USE_SAMPLES', '0')
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'out')
    path = store.ROOT / 'evidence/P-0001/archive/cbom.json'
    path.parent.mkdir(parents=True)
    payload = b'{"exact":"archived bytes"}'
    path.write_bytes(payload)
    entry = {'seq': 1, 'evidence_files': {'cbom': {'path': str(path), 'sha256': attest.digest(payload)}}}
    def fake_worker(route):
        return {'chain_ok': True} if route == '/ledger/verify' else [entry]
    monkeypatch.setattr(api, 'worker', fake_worker)
    return api, entry, path, payload


def test_evidence_download_exact_signed_bytes_and_authentication(evidence_download, monkeypatch):
    from chronos.api.app import app
    from fastapi.testclient import TestClient
    api, entry, path, payload = evidence_download
    monkeypatch.setenv('CHRONOS_API_TOKEN', 'unit-owner-token')
    client = TestClient(app)
    assert client.get('/api/ledger/1/evidence/cbom').status_code == 401
    response = client.get('/api/ledger/1/evidence/cbom', headers={'Authorization': 'Bearer unit-owner-token'})
    assert response.status_code == 200
    assert response.content == payload
    assert response.headers['x-content-sha256'] == entry['evidence_files']['cbom']['sha256']
    assert response.headers['content-type'] == 'application/json'


@pytest.mark.parametrize('failure', ['hash', 'outside', 'symlink', 'chain'])
def test_evidence_download_rejects_invalid_evidence(evidence_download, monkeypatch, tmp_path, failure):
    from fastapi import HTTPException
    api, entry, path, payload = evidence_download
    if failure == 'hash':
        path.write_bytes(b'changed archive')
    elif failure == 'outside':
        entry['evidence_files']['cbom']['path'] = str(tmp_path / 'secret.json')
    elif failure == 'symlink':
        actual = Path.is_symlink
        monkeypatch.setattr(Path, 'is_symlink', lambda candidate: candidate == path.parent or actual(candidate))
    else:
        monkeypatch.setattr(api, 'worker', lambda route: {'chain_ok': False})
    with pytest.raises(HTTPException) as exc:
        api.download_evidence(1, 'cbom', {'sub': 'secops'})
    assert exc.value.status_code == 409


def test_evidence_download_missing_or_sample_is_404(evidence_download, monkeypatch):
    from fastapi import HTTPException
    api, entry, path, payload = evidence_download
    for seq, kind in [(2, 'cbom'), (1, 'secret'), (1, 'verification')]:
        with pytest.raises(HTTPException) as exc:
            api.download_evidence(seq, kind, {'sub': 'secops'})
        assert exc.value.status_code == 404
    monkeypatch.setenv('CHRONOS_USE_SAMPLES', '1')
    with pytest.raises(HTTPException) as exc:
        api.download_evidence(1, 'cbom', {'sub': 'secops'})
    assert exc.value.status_code == 404


@pytest.fixture
def worker_http(tmp_path, monkeypatch):
    token = 'unit-test-worker-token-at-least-24'
    monkeypatch.setenv('CHRONOS_WORKER_TOKEN', token)
    monkeypatch.setenv('CHRONOS_ROOT', str(tmp_path))
    (tmp_path / 'demo').mkdir()
    (tmp_path / 'demo/topology.yaml').write_text('channels:\n- {protocol: tls, dst: portal, port: 8443}\n')
    monkeypatch.setattr(worker, 'tls', lambda *args: (0, 'Negotiated TLS1.3 group: X25519'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), worker.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', token
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def test_worker_http_rejects_unauthenticated_probes(worker_http):
    url, _ = worker_http
    with pytest.raises(HTTPError) as exc:
        urlopen(url + '/probe/tls?host=portal&port=8443', timeout=3)
    assert exc.value.code == 401


def test_worker_http_allowlist_and_raw_discovery_output(worker_http):
    url, token = worker_http
    request = Request(url + '/probe/tls?host=portal&port=8443', headers={'Authorization': 'Bearer ' + token})
    with urlopen(request, timeout=3) as response:
        assert json.loads(response.read())['output'] == 'Negotiated TLS1.3 group: X25519'
    forbidden = Request(url + '/probe/tls?host=169.254.169.254&port=80', headers={'Authorization': 'Bearer ' + token})
    with pytest.raises(HTTPError) as exc:
        urlopen(forbidden, timeout=3)
    assert exc.value.code == 403
