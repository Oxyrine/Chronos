#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
$PY -m chronos.shelflife.train
$PY -m chronos.eval_all "$@"
