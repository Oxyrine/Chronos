#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
name="${1:?usage: loadgen.sh before|after [seconds]}"
seconds="${2:-60}"
case "$name" in before|after) ;; *) exit 2;; esac
mkdir -p "out/runs/$name"
python3 - "$name" <<'PY'
import json, pathlib, sys
out=pathlib.Path('out')
offsets={}
for svc in ('portal','reminders','partner-lab'):
    p=out/'logs'/svc/'chronos.log'
    offsets[svc]=p.stat().st_size if p.exists() else 0
(out/'runs'/sys.argv[1]/'log_offsets.json').write_text(json.dumps(offsets))
PY
docker run --rm --network staster -v "$PWD:$PWD:ro" -v "$PWD/demo/ca/ca.pem:/keys/ca.pem:ro" -w "$PWD" chronos-base:local python3 -m chronos.stream.loadgen --seconds "$seconds" > "out/runs/$name/loadgen.json"
bash scripts/client_mix.sh "$name"
bash scripts/snapshot_run.sh "$name"
