#!/usr/bin/env bash
# Reset the demo stack to its baseline unpatched state before recording takes.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[reset_demo] Restoring baseline planted vulnerable configs..."
git checkout HEAD -- demo/portal/nginx.conf demo/reminders/nginx.conf demo/ops-ssh/sshd_config demo/lab-api/openssl.cnf

if [ -s ledger/attestations.jsonl ]; then
    mkdir -p ledger/archive
    TS="$(date +%Y%m%d_%H%M%S)"
    echo "[reset_demo] Archiving existing ledger to ledger/archive/attestations_${TS}.jsonl..."
    cp ledger/attestations.jsonl "ledger/archive/attestations_${TS}.jsonl"
    : > ledger/attestations.jsonl
fi

echo "[reset_demo] Rebuilding and restarting demo services..."
docker compose --env-file .env -f demo/compose.yml up -d --build --wait --wait-timeout 300 portal reminders ops-ssh lab-api

# Run the scan and classification in-process inside chronos-api: no HTTP auth, no curl
# (the API image has none), and any failure stops the script instead of being swallowed.
echo "[reset_demo] Rescanning and reclassifying the baseline stack..."
docker compose exec -T chronos-api python - <<'PYEOF'
from chronos.common import store
from chronos.discovery.service import rescan
from chronos.shelflife import model, serve

stats = rescan()["stats"]
predictions = serve.classify_database(model.CategoryModel.load(), overrides=store.get("overrides", {}))
store.put("shelflife", predictions)
store.put("proposals", [])  # proposals bound to the patched files are stale after a reset
print(f"[reset_demo] scan: {stats['findings']} findings in {stats['scan_seconds']} s; classified {len(predictions)} columns")
PYEOF

echo "[reset_demo] Demo stack reset complete. Baseline vulnerable state active."
