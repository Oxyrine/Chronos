# Chronos: Person A Implementation Plan (Crypto & Infrastructure)

## Context
Chronos (IBM Z Datathon 2026) finds data that can be recorded now and decrypted later, scores it with Mosca's rule, and fixes the worst channels with verified, ML-DSA-signed post-quantum config changes. Three-person split: **A = crypto & infra**, B = data/AI/scoring, C = API/dashboard/story.

**Person B is done and verified on the VM** (repo `github.com/Oxyrine/Chronos`, `/opt/chronos`): contracts, six scanners + CBOM, shelf-life classifier (Snap ML, held-out F1 0.821, under-protection 4.2%), Mosca/priority/E/R, routers, `eval_all`. 73 tests pass on s390x. Everything B still needs to finish (real discovery recall, in-DB profiling on Postgres, E and R from real runs) is blocked on **Person A's stack**.

Person A owns **Lane 1 (St. Aster demo stack), Lane 6 (Granite remediation agent), Lane 7 (PQC base images, sandbox verifier, ML-DSA ledger)**, plus Hour-0, base images, swap and build lock, `loadgen`, and the 70/30 client-mix run. A hands B the running stack, `topology.yaml` and `ground_truth.yaml`, and hands C the proposal, verification and ledger endpoints.

On approval: save as `docs/PLAN_PERSON_A.md` in the repo (commit and push) and as `chronos-person-A-plan.md` beside B's plan.

---

## 0. Facts already established on the VM (don't redo)
| Item | State |
|---|---|
| Host | `linux1@cloud-instance`, s390x, **Ubuntu 24.04** (host OpenSSL 3.0, Python 3.12) |
| Docker | `docker.io` 29.x from apt, working; `linux1` in `docker` group |
| Repo | `/opt/chronos`, owned by `linux1`; B's venv `.venv` (apt numpy/scipy/sklearn + pip snapml, jsonschema) |
| NNPA | Snap ML reports "Falling back to CPU-only mode": treat as **no NNPA** until `grep -w nnpa /proc/cpuinfo` says otherwise. Never claim accelerator numbers |
| Python wheels | numpy/scipy/sklearn have **no s390x wheels for py3.12 slim**; `python:3.12-slim` can't install them without compiling. Use apt packages on Ubuntu 24.04 (B's proven recipe) |
| Not yet done | swapfile, `ubuntu:26.04` s390x manifest + container OpenSSL/OpenSSH check, RAM/disk numbers, nginx/ssh/llama builds |

## 1. What A owns (files)
```
scripts/  hour0.sh seed_crypto.sh build_llama.sh convert_granite.sh(laptop) client_mix.sh snapshot_run.sh run_all.sh acceptance_demo.sh
docker/base/Dockerfile      chronos-base:   ubuntu:26.04 + openssl 3.5 + openssh 10 + nginx + python3 (+psycopg2, cryptography)
docker/pybase/Dockerfile    chronos-pybase: ubuntu:24.04 + apt numpy/scipy/sklearn/fastapi + venv(system-site) + pip snapml jsonschema   (for chronos-api)
demo/compose.yml            portal, portal-app, reminders, lab-api, partner-lab, records-db, ops-ssh   (billing + infra = files only)
demo/<service>/...          configs, Dockerfiles, app code, planted crypto
demo/topology.yaml          channels + table sizes        (contract: contracts/topology.schema.json)
demo/ground_truth.yaml      every crypto asset in demo/   (contract: contracts/ground_truth.schema.json)
compose.yml                 chronos project: chronos-nginx(9443), chronos-api, verifier, llm(profile), redis(P1 profile)
chronos/agent/   templates.py validator.py llm_client.py propose.py eval.py prompts/
chronos/verify/  worker.py(verifier HTTP service) sandbox.py checks.py ledger.py attest.py
chronos/stream/loadgen.py
chronos/api/routers/  agent.py verify.py          (mounted by C like B's routers)
tests/  test_agent.py test_verify.py test_ledger.py
```
**Reuse B's code, don't re-implement:** `chronos/common/samples.py` (`validate`, `load`, `CHRONOS_USE_SAMPLES`), `chronos/common/store.py` (`put/get`), `chronos/api/deps.py:current_user`, `chronos/risk/catalog.py:kex_class` (classify negotiated groups), `contracts/patch_proposal|verification_result|attestation.schema.json`, `chronos/discovery/scan.py:run` + the scan router's `_run` for the post-approve rescan.

---

## 2. Interfaces A must match exactly (B's code already depends on these)
| What | Exact shape |
|---|---|
| `demo/topology.yaml` | `channels: [{id: "src->dst", src, dst, protocol: tls|ssh, port, reach: internet|partner|internal, tables: [...], probe: true|false}]`, `tables: {name: {records, store: records-db, mean_record_bytes}}`. `dst` = **docker DNS name** reachable from the verifier; `port` = **in-network** port. Channels: `internet->portal`(8443: patients, encounters, appointment_reminders, otp_codes), `internet->reminders`(8444: appointment_reminders), `lab-api->partner-lab`(8443: lab_results, genomics_results, **probe: false**: client-pinned), `clinician->ops-ssh`(2222: encounters). **Do not** model `portal-app->records-db` as a channel (postgres:16 = OpenSSL 3.0, no template; it would pin E). List it as a remaining risk on the card instead |
| `demo/ground_truth.yaml` | `assets: [{id, path, line, asset_type, algorithm, params, quantum_status}]`. `path` relative to repo root (`demo/portal/nginx.conf`); live endpoints as `live://portal:8443`. List **every** crypto asset in `demo/`, vulnerable or not (otherwise B's precision is wrong). Match rule: same path, algorithm family overlaps, line ±2 (`chronos/discovery/evaluate.py`) |
| File naming the scanners read | nginx `*.conf` with `ssl_ecdh_curve A:B;` on one line; `sshd_config` (exact name) with `KexAlgorithms`; `openssl.cnf` (exact) with `Groups = ...`; `java.security` (exact) with `jdk.tls.namedGroups=`; `postgresql.conf` with `ssl_ecdh_curve`; `*.tf` with `tls_private_key`; certs `.pem/.crt/.der/.p12/.jks` (JKS password `changeit`) |
| SSH host key | generate with **`ssh-keygen -m PEM`** (B's cert scanner reads PEM, not the OpenSSH key format) |
| records-db | `container_name: records-db`, `POSTGRES_USER=chronos`, `POSTGRES_DB=staster` (B's default `CHRONOS_PSQL_CMD`), tables in `public`, `ANALYZE` after load |
| nginx log | `log_format chronos escape=json '{"time":"$time_iso8601","remote_addr":"$remote_addr","request_uri":"$request_uri","status":$status,"bytes_sent":$bytes_sent,"request_time":$request_time,"ssl_protocol":"$ssl_protocol","ssl_cipher":"$ssl_cipher","ssl_curve":"$ssl_curve","ssl_curves":"$ssl_curves"}';` on portal, reminders, partner-lab; log dir mounted to `/opt/chronos/out/logs/<svc>/` → `CHRONOS_NGINX_LOG` |
| portal-app routes | `/api/patients/{id}`, `/api/patients/export?limit=`, `/api/records/{patient_id}` (encounters), `/api/labs/...`, `/api/genomics/...`, `/api/reminders/...`: B's route map in `chronos/risk/harvestable.py:DEFAULT_ROUTES` |
| Run snapshots for B's eval | `out/runs/{before,after}/{findings.json, shelflife.json, client_mix.json, nginx.log}`; `client_mix.json` = `{"mix":{"hybrid_capable":70,"legacy":30},"q":{channel_id: classical_share}}`; also `store.put("client_mix", ...)` for the live API |
| Every service | `GET /health` → `{"status":"ok","arch":"s390x"}` |

**Small B-side follow-ups this plan creates** (B does them, about 1 hour total): (1) `live_probe` honours `probe: false` and gains an HTTP runner (`CHRONOS_PROBE_URL`) that calls the verifier's allow-listed probe endpoints, so chronos-api needs no Docker socket; (2) lift the scan router's `_run` into `chronos/discovery/service.py:rescan()` for the approve flow; (3) `eval_all` reads `out/agent_eval.json` and `out/bench.json`.

---

## 3. Timeline (relative; shift to the real deadline)
Spec clock: start 19:00 IST 17 Oct, submit 08:00 18 Oct. B is complete, so A is the critical path. **If time is short, follow the minimum path in section 9.**

| Phase | Duration | A does | Exit check (spec gate) |
|---|---|---|---|
| 0. Hour-0 | 45 min | Both mandatory labs (if not done). `hour0.sh`, swapfile, manifests, kick off `chronos-base` build in background | Results posted to team channel |
| 1. Walking skeleton | ~2 h | `seed_crypto.sh`, portal (nginx + planted RSA cert) + portal-app `/health`, records-db with 1 table, draft `topology.yaml` | B's `certs_keys` finds the portal cert; B profiles 1 table in-DB |
| 2. Gate 1 | ~4 h | All demo services, full data, `ground_truth.yaml`, baseline-classical proof, llama.cpp + Granite answering, T1–T3 renderers + validator (rules first), verifier worker with sign/ledger | **Gate 1:** all services up, every channel classical, Granite answers |
| 3. Gate 2 | ~4 h | Sandbox verify T1/T2 (T3 attempt), approve → apply → rescan → attest, client mix q before/after, loadgen before/after + snapshots, agent eval (20) | **Gate 2:** T1+T2 verified & attested; q measured; B's E and R computed |
| 4. Polish | ~3 h | Benchmark table, rehearse the fix step, security notes, help the video | Rough take at Gate 2, final at video time |

---

## 4. Phase 0 — Hour-0 (VM)
1. `scripts/hour0.sh` (spec §6 verbatim), plus `docker manifest inspect ubuntu:26.04 | grep s390x`. Record: `nproc`, `free -g`, `df -h /` (needs ≥ 15 GB free: images + 2.7 GB GGUF + llama build), NNPA grep, container `openssl version` + `openssl list -tls-groups | grep -i mlkem`, `ssh -V`.
2. Swap: `sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile` (+ `/etc/fstab` line).
3. Build lock convention: every build is `flock /tmp/chronos-build.lock docker compose build <svc>`.
4. `docker network create staster` (shared by demo, chronos, sandbox projects).
5. Decision table outcomes (spec §6): no `ubuntu:26.04` s390x → `25.10` → OpenSSL 3.5 from source into `/opt/openssl35` on 24.04 (Fallback A) → oqs-provider (B). OpenSSH < 10 → T2 uses `sntrup761x25519-sha512@openssh.com`.
6. Team access: if teammates use separate accounts, `sudo usermod -aG docker <user>` and a `chronos` group with setgid on `/opt/chronos`. Agree: **one branch per person**, merge to `main`.

## 5. Lane 7a — Base images
- **`chronos-base`** (`docker/base/Dockerfile`, `ubuntu:26.04`): `openssl openssh-server openssh-client nginx python3 python3-psycopg2 python3-cryptography curl ca-certificates`. Build-time asserts: `openssl version` ≥ 3.5; `openssl list -tls-groups` has `X25519MLKEM768`; `ssh -Q kex` has `mlkem768x25519-sha256`; `python3 -c "import ssl;print(ssl.OPENSSL_VERSION)"` reports 3.5. Used by portal, reminders, partner-lab, ops-ssh, lab-api, portal-app, verifier, chronos-nginx.
- **`chronos-pybase`** (`docker/pybase/Dockerfile`, `ubuntu:24.04`): replicate B's working VM recipe: apt `python3-numpy python3-scipy python3-sklearn python3-joblib python3-yaml python3-faker python3-cryptography python3-fastapi python3-httpx python3-venv libgomp1 make`, venv `--system-site-packages`, pip `jsonschema>=4.18 referencing pyjks "httpx>=0.27,<0.28"` + `pip install --no-deps snapml`. Used by chronos-api. **B retrains inside this image** (`docker compose run chronos-api make corpus train`) so the pickled model matches its sklearn/numpy.
- Pull once at Hour-0 (`ubuntu:26.04 ubuntu:24.04 postgres:16 redis:7 eclipse-temurin:21-jdk`); compose never pulls after.

## 6. Lane 1 — St. Aster General demo stack (`demo/`)
**`scripts/seed_crypto.sh`** (idempotent, regenerates everything, never committed): internal CA RSA-2048 (`demo/ca/ca.pem`, `ca.key`); per-service RSA-2048 server certs with SANs `<svc>`, `<svc>.staster.test`, `sandbox-<svc>` into `demo/<svc>/certs/`; ops-ssh RSA-2048 host key `ssh-keygen -t rsa -b 2048 -m PEM`; `billing.jks` via `docker run --rm eclipse-temurin:21-jdk keytool -genkeypair -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -storetype JKS -storepass changeit`; records-db server cert; chmod 600 on keys; `.env` with a random Postgres password. Add to `.gitignore`: `demo/**/certs/`, `demo/ca/`, `*.key`, `*.jks`, `.env`.

| Service | Build | Planted "before" state (pinned explicitly, never left to defaults) |
|---|---|---|
| portal | chronos-base nginx, 8443 → `portal-app:8000` | RSA-2048 cert; `ssl_protocols TLSv1.3 TLSv1.2;` `ssl_ecdh_curve X25519:prime256v1;` chronos log |
| portal-app | chronos-base, Python stdlib `http.server` + psycopg2 (parameterised queries, int-validated ids) | JSON routes from section 2; `/health` |
| reminders | same nginx config and cert profile as portal, 8444; `location` allows only `/api/reminders` | identical crypto: the twin |
| lab-api | chronos-base Python, `OPENSSL_CONF=/app/openssl.cnf` | `crypto_utils.py`: `rsa.generate_private_key(key_size=2048)`, `padding.OAEP` wrap of an AES-256-GCM key, `ec.generate_private_key(ec.SECP256R1())` signing a fake PDF, `hashlib.sha1` etag; `openssl.cnf` `[system_default_sect] Groups = X25519:P-256`. `POST /forward/{lab_id}?trace=` sends a lab result to partner-lab over TLS with cert + hostname verification against the internal CA, and logs `ssl.OPENSSL_VERSION` + peer |
| partner-lab | chronos-base nginx, hybrid **enabled**: `ssl_ecdh_curve X25519MLKEM768:X25519:prime256v1;` chronos log; `POST /ingest` → 200 | (resistant server; the classical pin is lab-api's client) |
| records-db | `postgres:16`, `mem_limit 256m`, `shared_buffers=64MB`, TLS on with RSA cert | `postgresql.conf` `ssl = on`, `ssl_ecdh_curve = 'prime256v1'` |
| ops-ssh | chronos-base sshd, **`Port 2222` inside the container** (so topology port = probe port) | ssh-rsa 2048 host key (PEM); `KexAlgorithms curve25519-sha256,ecdh-sha2-nistp256` |
| billing | files only | `Billing.java`: `KeyPairGenerator.getInstance("RSA")` + `.initialize(2048)`, `Signature.getInstance("SHA256withRSA")`, `Cipher.getInstance("AES/ECB/PKCS5Padding")`, `MessageDigest.getInstance("SHA-1")`; `billing.jks` |
| infra | files only (`demo/infra/`) | `terraform/main.tf` `tls_private_key` RSA 2048; `openssl.cnf` classical `Groups`; `java.security` `jdk.tls.namedGroups=x25519,secp256r1` |

**Synthetic data** (`demo/records-db/gen_data.py`, seed 42, own generators: **do not import B's `data/semantics.py`**, so B's real-DB test stays honest): the 9 tables, exact names and row counts from spec §7.1 (~913k rows). Add `patient_id` PK on `patients` and FK constraints where natural. Speed: pre-generate pools (5k names, addresses) and sample; write CSV, load with `COPY` from `docker-entrypoint-initdb.d`; end with `ANALYZE`. Target < 3 min on 3 vCPUs. Realistic formats: ICD-10, LOINC, HGVS, phones, national-ID-like, 6-digit OTPs, 64-hex token hashes, ISO dates.

**Topology + table facts:** measure `mean_record_bytes` per table from real portal-app JSON responses and write them into `topology.yaml`.

**`ground_truth.yaml` (~40 assets):** per nginx (portal, reminders, partner-lab): conf `ssl_ecdh_curve` line, cert, key, live endpoint; CA cert + key; lab-api: 4 Python lines + `openssl.cnf` Groups; billing: 4 Java lines + JKS key + cert; records-db: conf line + cert + key; ops-ssh: KexAlgorithms line + host key + live endpoint; infra: tf + openssl.cnf + java.security. Write line numbers by grepping the committed files after the last edit; certs and keys by path only.

**Acceptance (`scripts/acceptance_demo.sh`, spec 7.1):** `seed_crypto.sh` regenerates all keys; every service `/health` (and `sshd -t`) green; baseline run shows **every channel classical**: verifier `s_client` to portal/reminders → `X25519`; real lab-api `/forward` → partner-lab log `ssl_curve = X25519`; `ssh -vv` → `kex: algorithm: curve25519-sha256`. Then B runs `python -m chronos.eval_all` for recall/precision and profiles `records-db`.

## 7. Lane 7b — Verifier service, sandbox, ML-DSA ledger (`chronos/verify/`)
**Design:** `verifier` container (chronos-base) runs `worker.py`, a stdlib HTTP service on the internal `staster` network only (no published port). It is the **only** container with `/var/run/docker.sock` and `keys/chronos-mldsa65.key` mounted (documented risk: socket = root on the VM; mitigated by no exposed port, allow-listed hosts, and accepting only stored proposal ids, never commands).

| Endpoint | Does |
|---|---|
| `GET /probe/tls?host&port` / `GET /probe/ssh?host&port` | Allow-listed against `topology.yaml`; runs `openssl s_client -brief` / `ssh -vv`; returns raw output (B's `live_probe` parses it) |
| `POST /verify/{proposal_id}` | Async job → VerificationResult |
| `POST /sign`, `POST /verify-sig` | `openssl pkeyutl -sign/-verify -rawin` with ML-DSA-65 |

**Sandbox flow (`sandbox.py`, spec 7.8):** copy `demo/<svc>/` → `out/sandbox/<P-id>/<svc>/`, write the rendered file, `docker compose -p sandbox -f demo/compose.yml -f <override>` up **one** container `sandbox-<svc>` (mem_limit 128 MB) on `staster`; always torn down after checks; never runs while `llm` is up.

**Checks (`checks.py`):**
- **TLS (T1):** `openssl s_client -connect sandbox-portal:8443 -servername portal.staster.test -groups X25519MLKEM768 -brief -verify_return_error -verify_hostname portal.staster.test -CAfile /keys/ca.pem` must report an MLKEM group. Compat mode: `-groups X25519` must still connect (residual recorded). Strict mode (`TLSv1.3` only, MLKEM-only groups): the classical client must fail, reported as rejected. `/health` 200.
- **SSH (T2):** `ssh -vv -o KexAlgorithms=mlkem768x25519-sha256 -p 2222 probe@sandbox-ops-ssh true` logs `kex: algorithm: mlkem768x25519-sha256`; `sshd -t` ok.
- **Outbound (T3):** a real `sandbox-lab-api` `POST /forward/{id}?trace=P-xxxx` reaches partner-lab with verification on; partner log line with that trace shows `X25519MLKEM768`; the same request before the fix showed `X25519`. **If MLKEM isn't negotiated, T3 is cut, not faked.**
- **Client mix:** 100 scripted handshakes (70 `-groups X25519MLKEM768:X25519`, 30 `-groups X25519:prime256v1`; SSH: 70 default OpenSSH 10, 30 `-o KexAlgorithms=curve25519-sha256`), negotiated group recorded per handshake via `kex_class` → q.
- Result stored as B's `verification_result` contract + full log at `out/verify/P-xxxx.log`; status → `verified_awaiting_approval`. A broken patch (bad group name) must fail at `nginx -t` or the handshake and never reach the demo stack.

**Approve → apply → attest (`attest.py`, `ledger.py`):** role `security_engineer` required (server-side check on `current_user()["role"]`). Write the rendered file into `demo/<svc>/`, `docker compose -f demo/compose.yml up -d --build <svc>`, rescan (B's `rescan()`), regenerate `out/cbom.json`. Attestation (B's contract): `entry = {seq, ts, proposal_id, approved_by, verification_sha256, cbom_sha256, prev_hash, alg: "ML-DSA-65"}`; canonical = `json.dumps(entry, sort_keys=True, separators=(",",":"))`; `entry_hash = sha256(canonical)`; `sig_b64` = ML-DSA over canonical; next `prev_hash` = this `entry_hash`; append to `ledger/attestations.jsonl`. `GET /ledger/verify` → `{chain_ok, bad_seq}` recomputing hashes and signatures. Key made once: `openssl genpkey -algorithm ML-DSA-65 -out keys/chronos-mldsa65.key`; public key downloadable.

**Acceptance (spec 7.8):** broken patch fails and the demo file is untouched; hand-edited ledger line → `chain_ok: false, bad_seq: n`; after deploy a real patient page loads over the new config; the card lists remaining risks (legacy share, signatures, the DB link, the RSA-OAEP code path); ledger UI text: "a signature proves who attested to which evidence, not that the patch is secure in every respect".

## 8. Lane 6 — Granite remediation agent (`chronos/agent/`)
**Model:** Granite 3.3 2B Instruct, Q8_0, **big-endian GGUF**. Order (spec risk table): (1) a published s390x-ready GGUF if one exists; (2) on the **x86 laptop**, `llama.cpp/convert_hf_to_gguf.py <hf_dir> --outtype q8_0 --bigendian --outfile granite-3.3-2b-instruct-q8_0-be.gguf` (`scripts/convert_granite.sh`), then `scp` to the VM (a BE GGUF is target-format data, not an x86 pickle). Do not rely on `gguf_convert_endian.py`.
**Runtime:** `scripts/build_llama.sh` builds llama.cpp on the VM (`cmake -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS`, under the build lock). Compose service `llm` under `profiles: [llm]`, `llama-server -m ... -t 3 -c 4096 --port 8080`, started on demand and stopped after; never alongside sandbox runs or benchmarks. Sanity: a short prompt must return readable text (garbage = endianness).

**Flow (`propose.py`):** rule gate first: only `usage == key_exchange`, `quantum_status == vulnerable` findings on a templatable file become proposals (nginx conf → T1, `sshd_config` → T2, lab-api `openssl.cnf` → T3); others are flagged without a proposal (RSA-OAEP code, Java, certificates; T4 is P1). The LLM gets the finding JSON, up to 60 lines of the file, the template catalog (ids + param enums), and the allowed groups/KEX names. Its JSON schema covers only `template_id`, `params`, `rationale`, `compatibility_risk`. Code adds `proposal_id`, `finding_id`, `requires_human: true`, `model`, then validates against B's `patch_proposal` contract.

**Templates (`templates.py`, deterministic renderers → new file content + unified diff via `difflib`):** T1 `ssl_protocols TLSv1.3 TLSv1.2;` + `ssl_ecdh_curve X25519MLKEM768:X25519:prime256v1;` (strict variant: `TLSv1.3` + MLKEM-only, card shows the legacy-client trade-off); T2 `KexAlgorithms mlkem768x25519-sha256,sntrup761x25519-sha512@openssh.com,curve25519-sha256`; T3 `Groups = X25519MLKEM768:X25519` in lab-api's `openssl.cnf`.
**Validator (`validator.py`, spec order):** schema valid → template allowed for the finding's asset type/file → params inside enums → diff touches only the target file → no key material (`BEGIN .* KEY`, long base64 runs). Any failure rejects with a reason shown in the UI.
**Fallback (decide at Gate 1):** if Granite is > 20 s per proposal or misbehaves: pre-generate proposals right after the scan; worst case the rules pick the template and Granite writes only the rationale (deck says so).
**Eval (`eval.py` → `out/agent_eval.json`):** 20 seeded templatable findings (the 4 real ones + 16 variants across files, group lists and services, with expected template labels) → 20 parseable, ≥ 18 correct template, 0 validator bypasses (include adversarial cases where the model proposes an off-enum group). Record latency p50/p95 for the benchmark table.

**Routers (`chronos/api/routers/agent.py`, `verify.py`, B's pattern):** `POST /proposals {finding_id}`, `GET /proposals/{id}` (proposal + diff), `POST /proposals/{id}/verify`, `GET /verifications/{proposal_id}`, `POST /proposals/{id}/approve` (security_engineer), `GET /ledger`, `GET /ledger/verify`. All honour `CHRONOS_USE_SAMPLES` via `samples.load`.

## 9. Minimum demo path (if time is short) and cut order
**Never cut:** baseline-classical pinning, the verifier, human approval, the ML-DSA ledger, honest metrics.
**Minimum:** portal + reminders + portal-app + records-db + ops-ssh, T1 + T2, verifier + ledger, client mix q, one loadgen before/after.
**Cut in this order:** T3 (and partner-lab) → strict mode → billing keystore → Granite (rules + canned rationale, said on the slide) → loadgen profiles reduced to two → P1 anything.

## 10. Client mix, loadgen, and run snapshots (feeds B's E and R)
- `scripts/client_mix.sh <before|after>`: runs the 100-handshake mix against the **real** stack per channel, writes `out/runs/<name>/client_mix.json` and `store.put("client_mix", ...)`. Before: expect q = 1.0 everywhere; after compat T1/T2: about 0.30 on portal/reminders/ops-ssh; T3: 0.0.
- `chronos/stream/loadgen.py`: runs **inside chronos-base** (host Python has OpenSSL 3.0, so it can't do hybrid). Four seeded profiles via per-process `OPENSSL_CONF`: patient browsers (classical), clinicians (hybrid-capable), partner lab (classical), harvester (bulk `/api/patients/export` bursts). Fixed duration (e.g. 5 min).
- `scripts/snapshot_run.sh <name>`: `POST /scan`, `POST /shelflife/run`, then copy `out/store/{findings,shelflife,client_mix}.json` + the nginx log segment into `out/runs/<name>/`. Order: baseline loadgen → `snapshot before` → approve fixes → loadgen again → `snapshot after` → B runs `eval_all`.

## 11. chronos-nginx (dashboard over hybrid TLS, port 9443)
chronos-base nginx: `ssl_protocols TLSv1.3;` `ssl_ecdh_curve X25519MLKEM768:X25519;` RSA (or ECDSA) cert from the internal CA (browsers don't trust ML-DSA certs yet: out of scope); serves C's built dashboard and proxies `/api` to chronos-api; security headers (HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors 'none'`, CSP agreed with C); HTTP listener absent or redirect-only.

## 12. Security baseline for A's pieces
- Bind every demo and chronos host port to `127.0.0.1`; reach the dashboard with `ssh -L 9443:localhost:9443 linux1@<vm>`. A deliberately vulnerable hospital must not face the internet.
- No secrets in git: keys/certs/JKS/`.env` generated by `seed_crypto.sh`, git-ignored; run `git ls-files | grep -Ei 'key|pem|jks|env'` before every push.
- ML-DSA key mode 600, mounted only into the verifier. Docker socket only in the verifier (documented).
- portal-app: parameterised queries, integer-validated ids, JSON only. Verifier: allow-listed hosts/ports only.
- Approve is enforced server-side by role, never by the UI alone.

## 13. Agent lanes A directs (file-disjoint, one session each)
| Agent | Files | Done when |
|---|---|---|
| Demo stack | `demo/`, `scripts/seed_crypto.sh`, `gen_data.py`, `acceptance_demo.sh`, `docker/base/` | 7.1 acceptance green; topology + ground truth delivered to B |
| Verifier + ledger | `chronos/verify/`, `chronos/api/routers/verify.py`, `scripts/client_mix.sh`, `tests/test_verify.py test_ledger.py` | 7.8 acceptance green |
| Agent | `chronos/agent/`, `chronos/api/routers/agent.py`, `scripts/build_llama.sh`, `convert_granite.sh`, `tests/test_agent.py` | 7.7 acceptance green; `out/agent_eval.json` |
| Loadgen + runs (after Gate 1) | `chronos/stream/loadgen.py`, `scripts/snapshot_run.sh` | before/after snapshots in `out/runs/` |
A personally does Hour-0, base images, the compose files, the shared network and the gate checks. Unit-testable pieces (renderers, validator, ledger canonicalisation and chain with a mocked signer) are written and tested on the laptop first; every acceptance run happens on the VM.

## 14. Risks → fallback
| Risk | Fallback | Decide by |
|---|---|---|
| No `ubuntu:26.04` s390x | 25.10 → OpenSSL 3.5 from source on 24.04 → oqs-provider | Hour-0 |
| Ubuntu nginx prints `$ssl_curve` as hex | B's `kex_class` already maps `0x11ec` | n/a |
| OpenSSH < 10 | T2 uses `sntrup761x25519-sha512@openssh.com` | Hour-0 |
| GGUF endianness garbage | laptop `--bigendian` convert; else rules-only template choice | Gate 1 |
| Granite > 20 s | pre-generate; shorter context; rules + rationale only | Gate 1 |
| Python `ssl` ignores `OPENSSL_CONF` Groups | set `ssl_conf`/`system_default` sections explicitly; else cut T3 | Gate 2 |
| RAM pressure (7.8 GB) | llm on demand only; one sandbox container; Postgres 256 MB; P1 off during demo | Gate 2 |
| Disk fills | `docker builder prune`, keep one GGUF | ongoing |
| Live demo breaks | recorded rough take at Gate 2; screenshots in deck | always |

## Verification (A is done when)
On the VM: `scripts/acceptance_demo.sh` green (all `/health`, every channel classical at baseline) → B's `python -m chronos.eval_all` reports discovery recall ≥ 0.90 / precision ≥ 0.85 and profiles `records-db` → `make test-agent` (20 proposals, ≥ 18 correct, 0 bypasses) → `make test-verify` (broken patch rejected, tampered ledger detected) → T1 + T2 verified, approved, attested, `GET /ledger/verify` → `chain_ok: true` → `out/runs/before|after` present and `eval_all` shows E before/after (target ≥ 70% drop under the disclosed 70/30 mix) and R → C's dashboard runs the full demo path over `https://localhost:9443` through the SSH tunnel.