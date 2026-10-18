#!/usr/bin/env bash
# Re-runnable: retain CA, credentials and host identity unless --regenerate is explicit.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
regenerate=0
if [[ ${1:-} == --regenerate ]]; then regenerate=1; shift; fi
if [[ $# -gt 0 ]]; then echo 'Usage: seed_crypto.sh [--regenerate]' >&2; exit 2; fi
mkdir -p demo/ca demo/billing out/logs/{portal,reminders,partner-lab}
if [[ $regenerate == 1 || ! -s demo/ca/ca.key ]]; then
  openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 3650 \
    -subj '/CN=St Aster Synthetic Demo CA/O=Chronos Demo' \
    -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign' \
    -keyout demo/ca/ca.key -out demo/ca/ca.pem
fi
for svc in portal reminders partner-lab records-db chronos-nginx; do
  dir="demo/$svc/certs"
  mkdir -p "$dir"
  if [[ $regenerate == 1 || ! -s "$dir/server.key" || ! -s "$dir/server.crt" ]]; then
    openssl req -new -newkey rsa:2048 -nodes -sha256 -subj "/CN=$svc.staster.test/O=Chronos Demo" \
      -keyout "$dir/server.key" -out "$dir/server.csr"
    printf 'subjectAltName=DNS:%s,DNS:%s.staster.test,DNS:sandbox-%s,DNS:localhost,IP:127.0.0.1\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n' "$svc" "$svc" "$svc" > "$dir/extensions.cnf"
    openssl x509 -req -in "$dir/server.csr" -CA demo/ca/ca.pem -CAkey demo/ca/ca.key \
      -set_serial "0x$(openssl rand -hex 16)" -days 365 -sha256 -extfile "$dir/extensions.cnf" -out "$dir/server.crt"
    rm -f "$dir/server.csr" "$dir/extensions.cnf"
  fi
  cp demo/ca/ca.pem "$dir/ca.pem"
  chmod 600 "$dir/server.key"
  chmod 644 "$dir/server.crt" "$dir/ca.pem"
done
mkdir -p demo/ops-ssh/certs
dir=demo/ops-ssh/certs
for key in ssh_host_rsa_key probe_key; do
  if [[ $regenerate == 1 || ! -s "$dir/$key" ]]; then
    rm -f "$dir/$key" "$dir/$key.pub"
    ssh-keygen -q -t rsa -b 2048 -m PEM -N '' -C "chronos-demo-$key" -f "$dir/$key"
  fi
done
cp "$dir/probe_key.pub" "$dir/authorized_keys"
pub=$(cut -d' ' -f1-2 "$dir/ssh_host_rsa_key.pub")
printf 'ops-ssh,[ops-ssh]:2222,[sandbox-ops-ssh]:2222,[localhost]:2222 %s\n' "$pub" > "$dir/known_hosts"
chmod 600 "$dir/ssh_host_rsa_key" "$dir/probe_key"
# sshd reads the probe user's authorized keys as that user.
chmod 755 "$dir"
chmod 644 "$dir/authorized_keys" "$dir/known_hosts"
if [[ ! -s .env ]]; then touch .env; fi
if ! grep -q '^POSTGRES_PASSWORD=' .env; then printf 'POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)" >> .env; fi
chmod 600 .env demo/ca/ca.key
# A caller may cut the optional JKS if the JDK image is unavailable, explicitly labelled.
if [[ ${CHRONOS_SKIP_JKS:-0} != 1 && ( $regenerate == 1 || ! -s demo/billing/billing.jks ) ]]; then
  rm -f demo/billing/billing.jks
  docker run --rm --pull never --user "$(id -u):$(id -g)" -v "$PWD/demo/billing:/work" eclipse-temurin:21-jdk \
    keytool -genkeypair -alias billing -keyalg RSA -keysize 2048 -sigalg SHA256withRSA \
    -dname 'CN=Synthetic Billing,O=Chronos Demo' -validity 365 -storetype JKS \
    -keystore /work/billing.jks -storepass changeit -keypass changeit
fi
if [[ ! -s ledger/attestations.jsonl || ! -s demo/ground_truth.yaml || $regenerate == 1 ]]; then
  python3 demo/build_ground_truth.py
else
  echo 'Preserving the measured baseline ground truth alongside the existing ledger.'
fi
echo 'Demo crypto ready. Generated keys and .env must remain untracked.'
