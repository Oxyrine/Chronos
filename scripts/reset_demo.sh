#!/usr/bin/env bash
# Reset the demo stack to its baseline unpatched state before recording takes.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[reset_demo] Restoring baseline planted vulnerable configs..."
git checkout HEAD -- demo/portal/nginx.conf demo/reminders/nginx.conf demo/ops-ssh/sshd_config demo/lab-api/openssl.cnf 2>/dev/null || true

if [ -s ledger/attestations.jsonl ]; then
    mkdir -p ledger/archive
    TS="$(date +%Y%m%d_%H%M%S)"
    echo "[reset_demo] Archiving existing ledger to ledger/archive/attestations_${TS}.jsonl..."
    cp ledger/attestations.jsonl "ledger/archive/attestations_${TS}.jsonl"
    : > ledger/attestations.jsonl
fi

if docker compose version >/dev/null 2>&1; then
    echo "[reset_demo] Rebuilding and restarting demo services..."
    docker compose --env-file .env -f demo/compose.yml up -d --build portal reminders ops-ssh lab-api
    echo "[reset_demo] Triggering fresh scan and classification..."
    docker compose exec chronos-api curl -s -X POST http://localhost:8000/api/scan >/dev/null || true
    docker compose exec chronos-api curl -s -X POST http://localhost:8000/api/shelflife/run >/dev/null || true
fi

echo "[reset_demo] Demo stack reset complete. Baseline vulnerable state active."
