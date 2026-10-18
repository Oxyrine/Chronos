ARG UBUNTU_VERSION=26.04
FROM ubuntu:${UBUNTU_VERSION}
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl openssh-server openssh-client nginx python3 python3-psycopg2 \
    python3-cryptography curl ca-certificates && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd \
    && python3 -c 'import ssl; assert ssl.OPENSSL_VERSION_INFO >= (3,5), ssl.OPENSSL_VERSION' \
    && openssl list -tls-groups | grep -qi X25519MLKEM768 \
    && ssh -Q kex | grep -qx mlkem768x25519-sha256
WORKDIR /app
