"""One-service sandbox, with no production configuration or log mounts."""
import contextlib
import copy
import json
import os
from pathlib import Path
import shutil
import time
from chronos.verify.checks import command, wait_ready


def root_path():
    return Path(os.environ.get('CHRONOS_ROOT', Path(__file__).resolve().parents[2])).resolve()


def service_for(record):
    path = Path(record['target'])
    if len(path.parts) < 3 or path.parts[0] != 'demo' or path.parts[1] not in ('portal', 'reminders', 'ops-ssh', 'lab-api'):
        raise ValueError('target is outside patchable demo services')
    return path.parts[1]


def configuration(root, record, work, run=command):
    svc = service_for(record)
    rc, output = run(['docker', 'compose', '-f', str(root / 'demo/compose.yml'), 'config', '--format', 'json'])
    if rc:
        raise RuntimeError(output)
    spec = copy.deepcopy(json.loads(output)['services'][svc])
    allowed = {'image', 'command', 'entrypoint', 'environment', 'working_dir', 'user', 'healthcheck', 'init'}
    spec = {key: value for key, value in spec.items() if key in allowed}
    if not spec.get('image'):
        raise ValueError('demo service needs an explicit built image')
    original = (root / 'demo' / svc).resolve()
    volumes = []
    full = json.loads(output)['services'][svc]
    for volume in full.get('volumes', []):
        if volume.get('type') != 'bind':
            raise ValueError('sandbox refuses named or anonymous volumes')
        source = Path(volume['source']).resolve()
        if source == original or original in source.parents:
            source = work / svc / source.relative_to(original)
        elif source == root / 'demo/ca/ca.pem':
            pass
        elif 'out/logs' in source.as_posix():
            source = work / 'logs'
            source.mkdir(exist_ok=True)
        else:
            raise ValueError(f'unexpected sandbox bind: {source}')
        volumes.append({'type': 'bind', 'source': str(source), 'target': volume['target'],
                        'read_only': volume['target'] != '/var/log/nginx'})
    spec.update(container_name='sandbox-' + svc, mem_limit='128m', volumes=volumes,
                networks={'staster': {'aliases': ['sandbox-' + svc]}})
    # Compose always adds the service key as a DNS alias. A distinct key keeps
    # sandbox traffic from stealing the production service's DNS name.
    return {'services': {'sandbox-' + svc: spec}, 'networks': {'staster': {'external': True, 'name': 'staster'}}}


@contextlib.contextmanager
def sandbox(record, run=command):
    root = root_path()
    svc = service_for(record)
    work = Path(os.environ.get('CHRONOS_OUT', root / 'out')) / 'sandbox' / record['proposal']['proposal_id']
    work.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root / 'demo' / svc, work / svc, dirs_exist_ok=True)
    relative = Path(record['target']).relative_to(Path('demo') / svc)
    (work / svc / relative).write_bytes(record['rendered'].encode())
    cfg = work / 'compose.json'
    cfg.write_text(json.dumps(configuration(root, record, work, run)))
    command_line = ['docker', 'compose', '-p', 'chronos-sandbox', '-f', str(cfg)]
    try:
        rc, output = run(command_line + ['up', '-d', '--no-build', '--pull', 'never'], timeout=90)
        if rc:
            raise RuntimeError(output)
        wait_ready('sandbox-' + svc, run)
        yield 'sandbox-' + svc, 2222 if svc == 'ops-ssh' else 8001 if svc == 'lab-api' else 8444 if svc == 'reminders' else 8443
    except Exception as exc:
        _, logs = run(['docker', 'logs', '--tail', '80', 'sandbox-' + svc])
        raise RuntimeError(str(exc) + '\nSandbox logs:\n' + logs) from exc
    finally:
        rc, output = run(command_line + ['down', '--remove-orphans'], timeout=45)
        if rc:
            raise RuntimeError('sandbox cleanup failed: ' + output)
