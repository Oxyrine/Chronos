#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
name="${1:?usage: snapshot_run.sh before|after}"
case "$name" in before|after) ;; *) echo 'invalid run name' >&2; exit 2;; esac
docker compose exec -T chronos-api python - "$name" <<'PY'
import json, os, pathlib, shutil, sys, urllib.request, time
root=pathlib.Path(os.environ['CHRONOS_ROOT']); out=root/'out'; dst=out/'runs'/sys.argv[1]
dst.mkdir(parents=True,exist_ok=True)
def request(path, data=None):
    req=urllib.request.Request('http://localhost:8000/api'+path, data=data,headers={'Authorization':'Bearer '+os.environ['CHRONOS_API_TOKEN'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=600) as r: return json.load(r)
sid=request('/scan', b'{}')['scan_id']
for _ in range(120):
    status=request('/scan/'+sid)
    if status['status']!='running': break
    time.sleep(1)
if status['status']!='done': raise RuntimeError(status)
request('/shelflife/run',b'{}')
for name in ('findings','shelflife','client_mix'):
    shutil.copy2(out/'store'/f'{name}.json',dst/f'{name}.json')
with (dst/'nginx.log').open('w') as f:
    offsets=json.loads((dst/'log_offsets.json').read_text()) if (dst/'log_offsets.json').exists() else {}
    for svc in ('portal','reminders','partner-lab'):
        p=out/'logs'/svc/'chronos.log'
        if p.exists():
            with p.open('rb') as source:
                source.seek(offsets.get(svc,0))
                f.write(source.read().decode())
print(dst)
PY
