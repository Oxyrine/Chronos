#!/usr/bin/env bash
# Run on the LinuxONE VM after startup, before any approvals. Fail on missing evidence.
set -euo pipefail
cd "$(dirname "$0")/.."
dc=(docker compose --env-file .env -f demo/compose.yml)
mkdir -p out/acceptance
for svc in portal reminders partner-lab portal-app lab-api; do
  if [[ $svc == portal-app ]]; then url=http://localhost:8000/health
  elif [[ $svc == lab-api ]]; then url=http://localhost:8001/health
  elif [[ $svc == reminders ]]; then url=https://localhost:8444/health
  else url=https://localhost:8443/health; fi
  "${dc[@]}" exec -T "$svc" curl --fail --silent --cacert /keys/ca.pem "$url" > "out/acceptance/$svc-health.json"
  python3 -c 'import json,sys; x=json.load(open(sys.argv[1])); assert x["status"]=="ok"; assert x["arch"]=="s390x", x' "out/acceptance/$svc-health.json"
done
"${dc[@]}" exec -T ops-ssh /usr/sbin/sshd -t
for svc in portal reminders; do
  port=8443; [[ $svc == reminders ]] && port=8444
  "${dc[@]}" exec -T "$svc" sh -c "openssl s_client -connect localhost:$port -servername $svc.staster.test -groups X25519MLKEM768:X25519 -brief -verify_return_error -verify_hostname $svc.staster.test -CAfile /keys/ca.pem </dev/null" > "out/acceptance/$svc-tls.log" 2>&1
  grep -Eq '(Negotiated TLS1.3 group|Server Temp Key|Peer Temp Key): X25519([,[:space:]]|$)' "out/acceptance/$svc-tls.log"
done
"${dc[@]}" exec -T lab-api curl --fail --silent -X POST 'http://localhost:8001/forward/1?trace=baseline-acceptance' > out/acceptance/lab-forward.json
# Access logging can flush at request completion; the request above has completed.
python3 - <<'PY'
import json
from pathlib import Path
rows=[json.loads(x) for x in Path('out/logs/partner-lab/chronos.log').read_text().splitlines()]
hits=[x for x in rows if 'trace=baseline-acceptance' in x.get('request_uri','')]
assert hits and hits[-1]['ssl_curve'].lower() in ('x25519','0x001d','0x1d'), hits[-1:]
PY
"${dc[@]}" exec -T ops-ssh ssh -vv -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/keys/known_hosts -i /keys/probe_key -p 2222 probe@ops-ssh true \
  > out/acceptance/ssh.log 2>&1
grep -F 'kex: algorithm: curve25519-sha256' out/acceptance/ssh.log
sql=$(python3 - <<'PY'
import json
top=json.load(open('demo/topology.yaml'))
print(' UNION ALL '.join(f"SELECT '{t}',count(*) FROM public.{t}" for t in top['tables']))
PY
)
"${dc[@]}" exec -T records-db psql -U chronos -d staster -Atc "$sql" > out/acceptance/table-counts.txt
python3 - <<'PY'
import json
expected={k:v['records'] for k,v in json.load(open('demo/topology.yaml'))['tables'].items()}
actual={parts[0]:int(parts[1]) for line in open('out/acceptance/table-counts.txt') if len(parts:=line.strip().split('|'))==2}
assert actual==expected, {'actual':actual,'expected':expected}
PY
echo 'Baseline acceptance passed: health, verified classical TLS/outbound/SSH, and database rows recorded.'
