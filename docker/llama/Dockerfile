# Native s390x artifacts are built by scripts/build_llama.sh on LinuxONE.
# Use repository root as build context, with out/llama.cpp/build/bin available.
FROM ubuntu:26.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libopenblas0 libgomp1 libstdc++6 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY out/llama.cpp/build/bin/ /opt/llama/bin/
ENV LD_LIBRARY_PATH=/opt/llama/bin
RUN test -x /opt/llama/bin/llama-server && \
    ln -s /opt/llama/bin/llama-server /llama-server && \
    /llama-server --version
ENTRYPOINT ["/llama-server"]
