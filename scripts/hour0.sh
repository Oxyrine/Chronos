#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p out
exec > >(tee out/hour0.log) 2>&1
date -u; uname -m; nproc; free -m; df -h /
if grep -qw nnpa /proc/cpuinfo; then echo 'NNPA flag present; benchmark acceleration separately'; else echo 'No NNPA flag; CPU only'; fi
docker manifest inspect ubuntu:26.04 | grep s390x
for image in ubuntu:26.04 ubuntu:24.04 postgres:16 redis:7 eclipse-temurin:21-jdk; do docker pull "$image"; done
docker network inspect staster >/dev/null 2>&1 || docker network create staster
if ! docker compose version >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y docker-compose-v2
fi
if ! swapon --show | grep -q /swapfile; then
    if [ ! -e /swapfile ]; then
        sudo fallocate -l 4G /swapfile
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
    fi
    sudo swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi
flock /tmp/chronos-build.lock docker build -t chronos-base:local docker/base
docker run --rm chronos-base:local sh -c 'openssl version; openssl list -tls-groups | grep -i mlkem; ssh -V; python3 -c "import ssl; print(ssl.OPENSSL_VERSION)"'
