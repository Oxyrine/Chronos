#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export CHRONOS_ROOT="$(pwd)"
mkdir -p out keys ledger out/logs/portal out/logs/reminders out/logs/partner-lab dashboard/dist
docker network inspect staster >/dev/null 2>&1 || docker network create staster
flock /tmp/chronos-build.lock docker build -t chronos-base:local docker/base
for image in postgres:16 eclipse-temurin:21-jdk; do
    docker image inspect "$image" >/dev/null 2>&1 || docker pull "$image"
done
python3 demo/records-db/gen_data.py --update-topology
bash scripts/seed_crypto.sh
python3 - <<'PY'
from pathlib import Path
import secrets
p=Path('.env')
values=dict(line.split('=',1) for line in p.read_text().splitlines() if '=' in line and not line.startswith('#'))
values['CHRONOS_ROOT']=str(Path.cwd())
for name in ('CHRONOS_WORKER_TOKEN','CHRONOS_API_TOKEN'):
    values.setdefault(name,secrets.token_hex(32))
values['PGPASSWORD']=values['POSTGRES_PASSWORD']
p.write_text(''.join(f'{k}={v}\n' for k,v in values.items()))
p.chmod(0o600)
PY
if [ ! -f keys/chronos-mldsa65.key ]; then
    docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/keys:/keys" chronos-base:local openssl genpkey -algorithm ML-DSA-65 -out /keys/chronos-mldsa65.key
fi
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/keys:/keys" chronos-base:local openssl pkey -in /keys/chronos-mldsa65.key -pubout -out /keys/chronos-mldsa65.pub.pem
chmod 600 keys/chronos-mldsa65.key
cp demo/ca/ca.pem keys/ca.pem
cp demo/ops-ssh/certs/probe_key keys/probe_key
cp demo/ops-ssh/certs/known_hosts keys/known_hosts
chmod 600 keys/probe_key
flock /tmp/chronos-build.lock docker build -t chronos-pybase:local docker/pybase
flock /tmp/chronos-build.lock docker compose build verifier
flock /tmp/chronos-build.lock docker compose --env-file .env -f demo/compose.yml build
docker compose --env-file .env -f demo/compose.yml up -d --wait --wait-timeout 300
for attempt in $(seq 1 90); do
    if docker exec records-db pg_isready -U chronos -d staster >/dev/null; then break; fi
    sleep 2
done
image_id=$(docker image inspect chronos-pybase:local --format '{{.Id}}')
if [ ! -f out/api-model-image-id ] || [ "$(cat out/api-model-image-id)" != "$image_id" ]; then
    docker compose run --rm chronos-api make train
    printf '%s' "$image_id" > out/api-model-image-id
fi
docker compose up -d --wait --wait-timeout 120 verifier chronos-api chronos-nginx
if [ -s ledger/attestations.jsonl ]; then
    echo 'Existing attestations retained; baseline-only checks are skipped on this resumed stack.'
else
    bash scripts/acceptance_demo.sh
fi
echo 'Chronos available through SSH tunnel on https://localhost:9443. Owner token is in .env.'
