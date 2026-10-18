"""Verification API. Docker and signing operations stay in the internal worker."""
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from fastapi import APIRouter, Depends, HTTPException, Response
from chronos.api.deps import current_user
from chronos.common import samples, store
from chronos.verify.ledger import digest

router = APIRouter(tags=['verification'])


def worker(path, body=None):
    token = os.environ.get('CHRONOS_WORKER_TOKEN', '')
    if not token:
        raise HTTPException(503, 'verifier worker is not configured')
    request = Request(os.environ.get('CHRONOS_VERIFIER_URL', 'http://verifier:8090').rstrip('/') + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=240 if path.startswith('/approve/') else 20) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get('detail', 'worker request failed')
        except ValueError:
            detail = 'worker request failed'
        raise HTTPException(exc.code, detail) from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(503, 'verifier unavailable') from exc


def valid_id(proposal_id):
    if not re.fullmatch(r'P-\d{4}', proposal_id):
        raise HTTPException(422, 'invalid proposal id')


@router.post('/proposals/{proposal_id}/verify', status_code=202)
def start(proposal_id: str, user: dict = Depends(current_user)):
    valid_id(proposal_id)
    if samples.use_samples():
        return {'proposal_id': proposal_id, 'status': 'sample', 'applied': False}
    return worker('/verify/' + proposal_id, {})


@router.get('/verifications/{proposal_id}')
def verification(proposal_id: str, user: dict = Depends(current_user)):
    valid_id(proposal_id)
    if samples.use_samples():
        return samples.load('verification_result', lambda: [])
    return worker('/verifications/' + proposal_id)


@router.post('/proposals/{proposal_id}/approve')
def approval(proposal_id: str, user: dict = Depends(current_user)):
    valid_id(proposal_id)
    if user.get('role') != 'security_engineer':
        raise HTTPException(403, 'security_engineer approval required')
    if samples.use_samples():
        return {'proposal_id': proposal_id, 'status': 'sample', 'applied': False,
                'attestation': samples.load('attestation', lambda: [])}
    return worker('/approve/' + proposal_id, {'user': {'sub': user['sub'], 'role': user['role']}})


@router.get('/ledger')
def entries(user: dict = Depends(current_user)):
    return samples.load('attestation', lambda: worker('/ledger'))


@router.get('/ledger/verify')
def chain(user: dict = Depends(current_user)):
    if samples.use_samples():
        return {'chain_ok': None, 'bad_seq': None, 'mode': 'sample', 'detail': 'sample signatures are illustrative'}
    return worker('/ledger/verify')


@router.get('/ledger/public-key')
def public_key(user: dict = Depends(current_user)):
    if samples.use_samples():
        raise HTTPException(404, 'sample mode has no signing key')
    return worker('/public-key')


@router.get('/ledger/{seq}/evidence/{kind}')
def download_evidence(seq: int, kind: str, user: dict = Depends(current_user)):
    if samples.use_samples():
        raise HTTPException(404, 'sample mode has no archived evidence')
    if kind not in ('cbom', 'verification', 'proposal') or seq < 1:
        raise HTTPException(404, 'evidence not found')
    chain_status = worker('/ledger/verify')
    if chain_status.get('chain_ok') is not True:
        raise HTTPException(409, 'ledger signature or hash chain verification failed')
    entry = next((item for item in worker('/ledger') if item.get('seq') == seq), None)
    metadata = entry.get('evidence_files', {}).get(kind) if entry else None
    if not metadata:
        raise HTTPException(404, 'archived evidence is unavailable for this entry')
    try:
        archive_root = Path(store.ROOT).resolve() / 'evidence'
        candidate = Path(metadata['path'])
        if not candidate.is_absolute() or '..' in candidate.parts or not candidate.is_relative_to(archive_root):
            raise ValueError('path outside archive')
        cursor = archive_root
        if cursor.is_symlink():
            raise ValueError('symlink archive')
        for part in candidate.relative_to(archive_root).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError('symlink evidence')
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(archive_root) or not resolved.is_file():
            raise ValueError('path outside archive')
        # O_NOFOLLOW also closes a last-component symlink swap on Linux.
        fd = os.open(candidate, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as handle:
            payload = handle.read()
        actual = digest(payload)
        if actual != metadata['sha256']:
            raise ValueError('archive hash mismatch')
    except FileNotFoundError as exc:
        raise HTTPException(404, 'archived evidence file is unavailable') from exc
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise HTTPException(409, 'archived evidence failed integrity or path validation') from exc
    return Response(payload, media_type='application/json', headers={
        'X-Content-SHA256': actual, 'Content-Disposition': f'attachment; filename="ledger-{seq}-{kind}.json"',
        'Cache-Control': 'no-store'})
