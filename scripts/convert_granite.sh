#!/usr/bin/env bash
# Run on the x86 laptop in bash/WSL; requires local HF Granite 3.3 2B Instruct files.
# Usage: scripts/convert_granite.sh /path/to/hf-model [/path/to/output.gguf]
set -euo pipefail
cd "$(dirname "$0")/.."
hf_dir=${1:?Usage: convert_granite.sh HF_MODEL_DIR [OUTPUT_GGUF]}
output=${2:-"$PWD/out/models/granite-3.3-2b-instruct-q8_0-be.gguf"}
source_dir=${LLAMA_CPP_DIR:-"$PWD/out/llama.cpp"}
python_bin=${PYTHON:-python3}
if [[ $(uname -m) != x86_64 && $(uname -m) != amd64 ]]; then
  echo 'Convert on the x86 laptop, then copy the big-endian GGUF to LinuxONE.' >&2
  exit 1
fi
[[ -f "$source_dir/convert_hf_to_gguf.py" ]] || { echo 'Set LLAMA_CPP_DIR to the same llama.cpp revision used for the server.' >&2; exit 1; }
[[ -d "$hf_dir" ]] || { echo 'HF model directory does not exist.' >&2; exit 1; }
mkdir -p "$(dirname "$output")"
# Confirm converter capability instead of pretending every revision has the same CLI.
converter_help=$("$python_bin" "$source_dir/convert_hf_to_gguf.py" --help)
[[ $converter_help == *--bigendian* && $converter_help == *q8_0* ]] || { echo 'Converter lacks --bigendian or q8_0; use a compatible llama.cpp revision.' >&2; exit 1; }
"$python_bin" "$source_dir/convert_hf_to_gguf.py" "$hf_dir" --outtype q8_0 --bigendian --outfile "$output"
"$python_bin" - "$output" <<'PY'
import pathlib, struct, sys
p = pathlib.Path(sys.argv[1])
with p.open('rb') as f:
    magic, version = f.read(4), f.read(4)
if magic != b'GGUF' or struct.unpack('>I', version)[0] not in (2, 3):
    raise SystemExit('Expected a big-endian GGUF v2/v3 header')
print(f'Big-endian GGUF header verified: {p} ({p.stat().st_size:,} bytes)')
PY
sha256sum "$output" > "$output.sha256"
git -C "$source_dir" rev-parse HEAD > "$output.llama-revision"
echo 'Before using proposals, run a short prompt on LinuxONE and inspect readable text; header validation alone does not validate inference.'
