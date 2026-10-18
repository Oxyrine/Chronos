"""Measured 70/30 demonstration. Failed handshakes are reported separately, never counted classical."""
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen
import yaml
from chronos.common import store
from chronos.risk.catalog import kex_class
from chronos.verify.checks import negotiated, ssh, tls
from chronos.verify.sandbox import root_path


def measure(name):
    if name not in ('before', 'after'):
        raise ValueError('run name must be before or after')
    topology = yaml.safe_load((root_path() / 'demo/topology.yaml').read_text())
    result = {'mix': {'hybrid_capable': 70, 'legacy': 30}, 'q': {}, 'channels': {},
              'scenario': 'controlled 100-attempt client mix; q uses successful negotiations only'}
    for channel in topology['channels']:
        if channel.get('probe', True) is False:
            # Exercise the actual pinned outbound application, never substitute s_client for it.
            rows = []
            prefix = f'mix-{name}-{time.time_ns()}'
            for number in range(100):
                trace = f'{prefix}-{number}'
                try:
                    req = Request(f'http://{channel["src"]}:8001/forward/1?trace={trace}', data=b'', method='POST')
                    with urlopen(req, timeout=20) as response:
                        response.read()
                        rows.append({'trace': trace, 'http_ok': response.status == 200})
                except Exception as exc:
                    rows.append({'trace': trace, 'http_ok': False, 'error': str(exc)})
            observed = {}
            for log in (Path(store.ROOT) / 'logs' / channel['dst']).glob('*.log'):
                for line in log.read_text(errors='replace').splitlines():
                    try:
                        event = json.loads(line)
                        uri = event.get('request_uri', '')
                        if prefix in uri:
                            trace = uri.split('trace=', 1)[1].split('&', 1)[0]
                            observed[trace] = event.get('ssl_curve')
                    except (ValueError, IndexError):
                        pass
            for row in rows:
                group = observed.get(row['trace'])
                row.update(group=group, accepted=row['http_ok'] and bool(group),
                           **{'class': kex_class(group) if group else None})
            success = [row for row in rows if row['accepted']]
            classical = sum(row['class'] == 'classical' for row in success)
            if success:
                result['q'][channel['id']] = classical / len(success)
            result['channels'][channel['id']] = {'attempted': 100, 'accepted': len(success), 'rejected': 100-len(success),
                                                 'classical': classical, 'handshakes': rows,
                                                 'client': 'actual lab-api outbound TLS; 70/30 mix does not change this fixed client'}
            continue
        rows = []
        for number in range(100):
            capable = number < 70
            if channel['protocol'] == 'tls':
                rc, output = tls(channel['dst'], channel['port'], 'X25519MLKEM768:X25519' if capable else 'X25519:prime256v1')
            else:
                rc, output = ssh(channel['dst'], channel['port'], None if capable else 'curve25519-sha256')
            group = negotiated(output, channel['protocol'])
            accepted = rc == 0 and bool(group)
            rows.append({'client': 'hybrid_capable' if capable else 'legacy', 'accepted': accepted,
                         'group': group, 'class': kex_class(group) if accepted else None,
                         'error': output[-1000:] if not accepted else ''})
        success = [row for row in rows if row['accepted']]
        classical = sum(row['class'] == 'classical' for row in success)
        if success:
            result['q'][channel['id']] = classical / len(success)
        result['channels'][channel['id']] = {'attempted': 100, 'accepted': len(success),
                                             'rejected': 100 - len(success), 'classical': classical, 'handshakes': rows}
    path = Path(store.ROOT) / 'runs' / name / 'client_mix.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2))
    store.put('client_mix', result)
    return result


if __name__ == '__main__':
    result = measure(sys.argv[1])
    print(json.dumps({'q': result['q'], 'path': str(Path(store.ROOT) / 'runs' / sys.argv[1] / 'client_mix.json')}))
