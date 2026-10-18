#!/usr/bin/env bash
# Pinned community BE conversion; the upstream IBM model is Granite 3.3 2B.
# A matching checksum verifies this artifact's bytes, not its inference quality.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p out/models
model=out/models/granite-3.3-2b-instruct-q8_0-be.gguf
expected=67f49e578649678a2f6c2d5343bb0ea03d77daf31ec85a398a20b8a44e91b6a2
revision=e55e965a507b2bfbaf44d2f7297f852ddc0250bb
if [[ -f $model ]] && echo "$expected  $model" | sha256sum --check --status; then
  echo 'Pinned BE Q8_0 model already present.'
  exit 0
fi
curl --fail --location --retry 3 \
  "https://huggingface.co/taronaeo/Granite-3.3-2B-Instruct-BE-GGUF/resolve/$revision/granite-3.3-2b-instruct-be.Q8_0.gguf" \
  --output "$model.part"
echo "$expected  $model.part" | sha256sum --check
python3 - "$model.part" <<'PY'
import pathlib, struct, sys
with pathlib.Path(sys.argv[1]).open('rb') as f:
    assert f.read(4)==b'GGUF' and struct.unpack('>I',f.read(4))[0]==3,'expected BE GGUF v3'
PY
mv -- "$model.part" "$model"
echo 'Verified community artifact. Check readable inference on LinuxONE before enabling Granite proposals.'
