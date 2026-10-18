#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
name="${1:?usage: client_mix.sh before|after}"
[[ "$name" == before || "$name" == after ]] || { echo 'run name must be before or after' >&2; exit 2; }
# Run in the worker's OpenSSL/OpenSSH 3.5/10 environment, never host OpenSSL 3.0.
docker compose exec -T verifier python3 -m chronos.verify.client_mix "$name"
