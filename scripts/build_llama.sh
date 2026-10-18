#!/usr/bin/env bash
# Native build; source checkout and binaries are local generated artifacts.
# Set CHRONOS_LLM_PREBUILT=1 for the verified official s390x binary runtime fallback.
set -euo pipefail
cd "$(dirname "$0")/.."
repo_root=$PWD
source_dir=${LLAMA_CPP_DIR:-"$repo_root/out/llama.cpp"}
build_jobs=${CHRONOS_BUILD_JOBS:-2}
exec 9>/tmp/chronos-build.lock
flock 9
if [[ ${CHRONOS_LLM_PREBUILT:-0} == 1 ]]; then
  [[ $(uname -m) == s390x ]] || { echo 'The pinned prebuilt image is s390x only.' >&2; exit 1; }
  docker build -f docker/llama/Dockerfile.prebuilt -t chronos-llm:local docker/llama
  docker run --rm chronos-llm:local --version
  exit 0
fi
command -v cmake >/dev/null || { echo 'Install cmake, g++, git, pkg-config and libopenblas-dev first.' >&2; exit 1; }
if [[ ! -d "$source_dir/.git" ]]; then
  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$source_dir"
fi
if [[ -n ${LLAMA_CPP_REF:-} ]]; then
  git -C "$source_dir" fetch --depth 1 origin "$LLAMA_CPP_REF"
  git -C "$source_dir" checkout --detach FETCH_HEAD
fi
git -C "$source_dir" rev-parse HEAD > "$repo_root/out/llama-cpp-revision.txt"
arch_flags=()
if [[ $(uname -m) == s390x ]]; then
  # Ubuntu 24.04 GCC13 cannot compile llama.cpp's auto-detected z17/arch15.
  # A z15 CPU target runs on z15 and later; vector CPU code is not NNPA offload.
  cpu_arch=${CHRONOS_CPU_ARCH:-z15}
  case "$cpu_arch" in z15|z16|native) ;; *) echo 'CHRONOS_CPU_ARCH must be z15, z16 or native.' >&2; exit 1 ;; esac
  arch_flags=(-DGGML_NATIVE=OFF "-DCMAKE_C_FLAGS=-march=$cpu_arch" "-DCMAKE_CXX_FLAGS=-march=$cpu_arch")
fi
cmake -S "$source_dir" -B "$source_dir/build" -DCMAKE_BUILD_TYPE=Release \
  -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF "${arch_flags[@]}"
cmake --build "$source_dir/build" --config Release --target llama-server -j "$build_jobs"
"$source_dir/build/bin/llama-server" --version
echo "Built native server for $(uname -m); source revision recorded in out/llama-cpp-revision.txt"
echo 'Set LLAMA_CPP_REF to that revision when reproducing this build.'
if [[ ${CHRONOS_BUILD_LLM_IMAGE:-1} == 1 ]]; then
  if [[ "$source_dir" != "$repo_root/out/llama.cpp" ]]; then
    echo 'Image build requires the default out/llama.cpp location; set CHRONOS_BUILD_LLM_IMAGE=0 for a custom source path.' >&2
    exit 1
  fi
  docker build -f docker/llama/Dockerfile -t chronos-llm:local "$repo_root"
fi
