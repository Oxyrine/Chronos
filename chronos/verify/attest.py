"""Apply only an unchanged, passed verification; roll back on deployment failure."""
import datetime as dt
import json
import os
import logging
from pathlib import Path
from chronos.common import samples, store
from chronos.verify.checks import command, run_checks, wait_ready
from chronos.verify.ledger import Ledger, OpenSSLSigner, digest, locked
from chronos.verify.sandbox import root_path, service_for


def proposal_binding(record):
    """Bind everything the human reviewed, including rationale/model, to verification."""
    return {'proposal': record['proposal'], 'finding': record['finding'], 'target': record['target'],
            'original_sha256': record['original_sha256'],
            'rendered_sha256': digest(record['rendered'].encode()), 'diff_sha256': record['diff_sha256']}


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def archive_evidence(proposal_id, record, verification, cbom_bytes):
    """Publish exact signed inputs once. Retries reuse identical bytes or a distinct hash path."""
    verification_bytes = json_bytes(verification)
    # Scans contain time/UUID fields, so each distinct CBOM must keep its own archive.
    archive_id = digest(verification_bytes) + '-' + digest(cbom_bytes)
    directory = Path(store.ROOT) / 'evidence' / proposal_id / archive_id
    directory.mkdir(parents=True, exist_ok=True)
    payloads = {'verification.json': verification_bytes, 'cbom.json': cbom_bytes,
                'proposal.json': json_bytes({**proposal_binding(record), 'diff': record['diff'],
                                             'rendered': record['rendered']})}
    files = {}
    for name, payload in payloads.items():
        path = directory / name
        try:
            with path.open('xb') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            path.chmod(0o444)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise ValueError('immutable evidence archive already contains different content')
        files[name.removesuffix('.json')] = {'path': str(path), 'sha256': digest(payload)}
    return files


def bound_record(proposal_id):
    from chronos.agent.propose import get_proposal
    from chronos.agent.validator import validate_stored
    record = get_proposal(proposal_id)
    if not record:
        raise KeyError(proposal_id)
    validate_stored(record, root_path())
    if digest(record['diff'].encode()) != record['diff_sha256']:
        raise ValueError('proposal diff hash mismatch')
    target = root_path() / record['target']
    if digest(target.read_bytes()) != record['original_sha256']:
        raise ValueError('target changed since proposal; rescan and propose again')
    return record


def ledger():
    return Ledger(Path(os.environ.get('CHRONOS_LEDGER', root_path() / 'ledger/attestations.jsonl')), OpenSSLSigner())


def approve(proposal_id, user, run=command, rescan=None, evidence_ledger=None):
    if user.get('role') != 'security_engineer' or not user.get('sub'):
        raise PermissionError('security_engineer approval required')
    root = root_path()
    with locked(Path(store.ROOT) / 'verify-operation.lock'):
        record = bound_record(proposal_id)
        verification = store.get('verification_' + proposal_id)
        if not verification or verification['status'] != 'passed':
            raise ValueError('a passed sandbox verification is required')
        samples.validate('verification_result', verification)
        if (verification['diff_sha256'] != record['diff_sha256'] or
            verification.get('rendered_sha256') != digest(record['rendered'].encode()) or
            verification.get('original_sha256') != record['original_sha256'] or
            verification.get('proposal_binding_sha256') != digest(proposal_binding(record))):
            raise ValueError('verified proposal content changed')
        if not verification['checks'] or not all(check.get('passed') is True for check in verification['checks']):
            raise ValueError('verification must contain successful checks')
        target = root / record['target']
        original = target.read_bytes()
        svc = service_for(record)
        compose = ['flock', '/run/chronos-build.lock', 'docker', 'compose', '-f', str(root / 'demo/compose.yml')]
        committed = False
        scan_attempted = False
        try:
            target.write_bytes(record['rendered'].encode())
            rc, output = run(compose + ['up', '-d', '--build', '--force-recreate', '--no-deps', svc], timeout=180)
            if rc:
                raise RuntimeError(output)
            wait_ready(svc, run)
            checks = run_checks(record, svc, 2222 if svc == 'ops-ssh' else 8001 if svc == 'lab-api' else 8444 if svc == 'reminders' else 8443,
                                svc, run)
            if not checks or not all(check['passed'] for check in checks):
                raise RuntimeError('post-deploy checks failed: ' + json.dumps(checks))
            if rescan is None:
                from chronos.discovery.service import rescan
            scan_attempted = True
            result = rescan()
            cbom = result.get('cbom')
            if not cbom:
                raise RuntimeError('rescan did not produce a CBOM')
            cbom_bytes = json_bytes(cbom)
            (Path(store.ROOT) / 'cbom.json').write_bytes(cbom_bytes)
            archive = archive_evidence(proposal_id, record, verification, cbom_bytes)
            evidence = {'ts': dt.datetime.now(dt.timezone.utc).isoformat(), 'proposal_id': proposal_id,
                        'approved_by': user['sub'], 'verification_sha256': digest(verification),
                        'cbom_sha256': digest(cbom_bytes), 'diff_sha256': record['diff_sha256'],
                        'post_deploy_checks': checks, 'evidence_files': archive,
                        'proposal_binding_sha256': verification['proposal_binding_sha256']}
            entry = (evidence_ledger or ledger()).append(evidence)
            committed = True
            record.update(state='approved', attestation=entry)
            try:
                store.put('proposal_' + proposal_id, record)
            except Exception as exc:
                # The ledger is the durable commit point. A metadata write failure
                # must not turn a completed deployment into a reported rollback.
                logging.getLogger(__name__).error('approved %s; proposal state needs recovery (%s)',
                                                  proposal_id, type(exc).__name__)
                try:
                    recovery = Path(store.ROOT) / 'state_recovery'
                    recovery.mkdir(parents=True, exist_ok=True)
                    path = recovery / (proposal_id + '.json')
                    temporary = path.with_suffix('.tmp')
                    with temporary.open('wb') as handle:
                        handle.write(json_bytes({'proposal_id': proposal_id, 'state': 'approved',
                                                 'record': record, 'error': type(exc).__name__}))
                        handle.flush()
                        os.fsync(handle.fileno())
                    temporary.replace(path)
                except Exception:
                    logging.getLogger(__name__).exception('state recovery journal unavailable; recover from signed ledger')
            return entry
        finally:
            if not committed:
                target.write_bytes(original)
                rc, output = run(compose + ['up', '-d', '--build', '--force-recreate', '--no-deps', svc], timeout=180)
                record['state'] = 'apply_failed' if rc == 0 else 'rollback_failed'
                record['rollback_output'] = output
                if rc == 0 and scan_attempted:
                    try:
                        wait_ready(svc, run)
                        rescan()
                    except Exception as exc:
                        record['rollback_rescan_error'] = str(exc)
                store.put('proposal_' + proposal_id, record)
                if rc:
                    raise RuntimeError('deployment failed and rollback failed: ' + output)
