# Chronos: 10-Slide Deck Outline & 3-Minute Video Script

**IBM Z Datathon 2026 — Theme 2: AI Secured: Innovation Without Exposure**  
*Chronos: Proactive Post-Quantum Cryptographic Agility for IBM Z LinuxONE*

---

## Part 1: 10-Slide Deck Outline

### Slide 1: Title & Theme 2 Hook
- **Title:** Chronos: Proactive Post-Quantum Cryptographic Agility
- **Subtitle:** Automated Cryptographic Discovery, In-DB Shelf-Life Profiling, and Verified Post-Quantum Remediation on IBM LinuxONE
- **Team:** Chronos Team (IBM Z Datathon 2026)
- **Visuals:** Chronos dark console shield logo, s390x badge, NIST FIPS 203/204 badges.
- **Theme 2 Opening Line:**  
  > *"Chronos understands sensitive data without exporting it, then protects how it travels from here on."*

---

### Slide 2: The Threat: Harvest Now, Decrypt Later (HNDL)
- **The Problem:** Classical asymmetric cryptography (RSA-2048, ECDHE P-256) will be broken by Shor's algorithm on a Cryptanalytically Relevant Quantum Computer (CRQC).
- **The Vulnerability:** Adversaries are recording encrypted enterprise traffic across public internet and partner networks today.
- **The High-Stakes Mismatch:**
  - Genomic and clinical healthcare data has a statutory retention shelf-life of **50 years**.
  - Banking and government identity records require **20 to 25 years** of confidentiality.
  - A CRQC is conservatively projected within **7 to 10 years** (2033 horizon).
  - *Data recorded today will be readable while still legally protected.*

---

### Slide 3: The Narrative Spine: Discover → Prioritize → Fix → Sign
- **Architecture Overview:** Chronos operates as an end-to-end cryptographic control plane:
  1. **Discover:** AST and network scanner generates CycloneDX 1.6 Cryptographic Bill of Materials (CBOM).
  2. **Prioritize:** Zero-data-egress in-DB classifier scores data shelf-life ($X$), applying Mosca's Inequality ($M = X + Y - Z$).
  3. **Fix:** IBM Granite 3.2 synthesizes verified hybrid PQ configuration patches (`X25519MLKEM768`), pre-validated in container sandboxes.
  4. **Sign:** NIST FIPS 204 **ML-DSA-65** post-quantum signatures recorded on an immutable Merkle ledger.

---

### Slide 4: Step 1: Discover (CycloneDX 1.6 CBOM)
- **Multi-Layer Detection:** Python AST, Java syntax trees, Nginx/OpenSSH parsers, and live network TLS probes.
- **Key Metrics (from `out/metrics.json`):**
  - **100% Recall** on tuned parser (0.933 baseline) across 45 seeded cryptographic assets.
  - Scan completes in **1.18 seconds**.
  - Compare to regex/grep baseline: **100% vs 26.7% recall** (grep misses indirect protocol calls and cipher suite strings).
- **Standard Output:** Standards-compliant CycloneDX 1.6 CBOM exported via JSON API.

---

### Slide 5: Step 2: Prioritize (In-DB Profiling & Zero Data Egress)
- **Zero Data Egress Guarantee:**
  - SQL aggregate functions execute inside PostgreSQL to compute cardinality, distinctness ratio, entropy, and token frequencies.
  - **No raw cell data, PII, or patient records ever leave the database boundary.**
- **Snap ML on LinuxONE (s390x):**
  - **0.094 ms / column** classification latency.
  - **Macro F1: 0.8207 (82.1%)**, 93.5% overall accuracy on 675 held-out synthetic columns.
  - Robust against obfuscation: **71.4% F1** on misleading column names (vs 4.9% for keyword matching).

---

### Slide 6: Step 2b: Mosca's Theorem ($M = X + Y - Z$) & Risk Matrix
- **Mosca's Inequality:**
  $$\mathbf{M = X + Y - Z}$$
  - $X$: Shelf-life retention requirement (years).
  - $Y$: Migration deployment time (1 year).
  - $Z$: Years until CRQC threat emerges (7 years in Base 2033 scenario).
  - **Condition $M > 0$:** Data will be decrypted during its confidential lifetime.
- **Deep-Dive Case Study:**
  - **Patient Portal (`patients.blood_group`):** $X = 50\text{y} \implies M = 50 + 1 - 7 = \mathbf{+44\text{ years}}$ (CRITICAL EXPOSURE, Priority 98/100).
  - **Appointment Reminders (`appointment_reminders.patient_id`):** $X = 10\text{y} \implies M = 10 + 1 - 7 = \mathbf{+4\text{ years}}$ (Low risk / deprioritized).

---

### Slide 7: Step 3: Fix (Granite 3.2 8B + Sandbox Verification)
- **Granite 3.2 Seam:** Synthesizes verified hybrid post-quantum configuration diffs (`T1_nginx_hybrid_groups`, `T2_sshd_hybrid_kex`).
- **Hybrid Security:** Deploys `X25519MLKEM768` (FIPS 203) — combines classical X25519 with ML-KEM lattice key encapsulation.
- **Sandbox Container Verification (~38.0s):**
  - Ephemeral container spins up with proposed diff.
  - Tests live TLS 1.3 handshake negotiation.
  - Verifies legacy client fallback (compatibility mode).
  - Validates zero configuration regressions before production apply.

---

### Slide 8: Step 4: Sign (ML-DSA-65 Attestation Ledger)
- **Cryptographic Attestation:**
  - Approved exclusively by authorized `security_engineer` (secops) role.
  - Signed with NIST FIPS 204 **ML-DSA-65** post-quantum digital signature.
  - Linked to previous attestation via SHA-256 Merkle hashes.
- **Immutable Evidence Bundle:** Each entry anchors the CBOM SHA-256, verification log SHA-256, and proposal diff SHA-256.
- **Public Key:** Downloadable PEM key allows independent third-party verification.

---

### Slide 9: Measured Impact & LinuxONE Proof (With Qualifiers)
- **Reproducible Metrics Table (from `out/metrics.json` & `out/bench.json`):**
  - **Exposure Index ($E$):** $668,000 \to 78,000$ (**↓ 88.3% risk reduction**).  
    *Qualifier: Evaluated under disclosed 70% hybrid / 30% legacy client traffic mix; 4 classical routes remain open.*
  - **Discovery Recall:** $0.933$ baseline measurement; $1.0$ achieved after closing regex/parser gaps.
  - **Classifier Accuracy:** $0.8207$ held-out Macro F1.  
    *Qualifier: Evaluated on synthetic schemas (hospital, bank, school); School F1 is optimistic.*
  - **Target Environment:** LinuxONE s390x CPU-only.  
    *Qualifier: CPU-only execution; no on-chip NNPA neural accelerator claimed or configured.*
  - **Runtime TLS Performance:** <0.5 ms handshake delta on s390x.

---

### Slide 10: Conclusion & Enterprise Readiness
- **Regulatory Alignment:** Exceeds compliance for NIST FIPS 203/204 (Aug 2024), NSA CNSA 2.0 (2025–2030), and BSI TR-02102.
- **Production Seam:** Human-in-the-loop governance with RBAC, scrypt password hashing, and rate limiting.
- **Summary:** Chronos empowers enterprise LinuxONE mainframes to achieve post-quantum crypto-agility today.

---

## Part 2: ~3-Minute Video Script (Timed Run)

| Timestamp | Screen / Visual | Speaker Audio & Action |
|---|---|---|
| **0:00 – 0:25** | **Title Slide → Browser showing Overview Screen**<br/>(URL: `https://localhost:9443`) | *"Nation-states are harvesting encrypted enterprise traffic today to decrypt with future quantum computers. On IBM LinuxONE mainframes, patient genomic records and financial transactions have a 50-year legal shelf-life. Classical encryption will fail long before statutory confidentiality expires. **Chronos understands sensitive data without exporting it, then protects how it travels from here on.** Our framework follows four rigorous steps: Discover, Prioritize, Fix, and Sign."* |
| **0:25 – 0:55** | **Switch to Inventory (CBOM) Screen**<br/>Click "Run Discovery Scan". | *"Step 1 is Discover. Rather than relying on fragile grep scripts that miss 73% of cryptographic calls, Chronos runs AST parsers and network probes across our seven microservices in just 1.18 seconds. Here we see 26 discovered assets compiled into a standardized CycloneDX 1.6 Cryptographic Bill of Materials—flagging vulnerable RSA-2048 and ECDHE ciphers in Nginx and OpenSSH."* |
| **0:55 – 1:30** | **Switch to Shelf-life Screen → Overview Heat Map**<br/>Drag CRQC slider from 2033 to 2030. | *"Step 2 is Prioritize. Chronos delivers a zero-data-egress guarantee: SQL aggregates profile columns inside PostgreSQL without raw data ever leaving the database boundary. Snap ML classifies data shelf-life in under 0.1 ms per column. On our Overview screen, we evaluate Michele Mosca's Theorem: Margin equals Shelf-life plus Migration minus Years to Quantum Computer ($M = X + Y - Z$). The patient portal transmits 50-year genetic data, yielding a critical margin of +44 years (red), while appointment reminders are safe (green)."* |
| **1:30 – 2:15** | **Switch to Remediation Queue**<br/>Select `ch_portal_api`. Click "Run Sandbox Verification". | *"Step 3 is Fix. In the Remediation Queue, findings are ranked by exposure score. We select the patient portal. Granite 3.2 8B synthesizes a verified hybrid patch injecting NIST FIPS 203 `X25519MLKEM768`. Before touching production, we run an automated container sandbox. Over 38 seconds, the sandbox verifies TLS 1.3 handshakes, hybrid negotiation, and legacy client fallback. All four checks pass."* |
| **2:15 – 2:45** | **Log in as `secops` → Approve Modal → Switch to Ledger** | *"Step 4 is Sign. Mutation and approvals require the `secops` role. Reviewing the diff SHA-256 and CBOM hashes, the security engineer approves the deployment. The target container is rebuilt, post-deploy checks pass, and an attestation is signed with NIST FIPS 204 **ML-DSA-65** post-quantum signatures and anchored to our SHA-256 Merkle ledger."* |
| **2:45 – 3:00** | **Overview Metrics Card & Footer**<br/>Highlight Exposure drop and `X-TLS-Group` footer. | *"Returning to the Overview, our Total Exposure Index has dropped from 668,000 to 78,000—an 88.3% risk reduction. In the footer, our active connection is verified running hybrid `X25519MLKEM768` directly on IBM LinuxONE s390x. Chronos delivers proactive, verified post-quantum cryptographic agility today."* |

---

## Part 3: Submission Checklist

Before submitting to Devpost / IBM Datathon portal:

1. [x] **Discord Confirmations:**
   - Confirmed submission deadline: 1 hour safety margin buffer maintained.
   - Video length confirmed under 3 minutes (script timed at 2m 55s).
   - Video uploaded as unlisted YouTube / Vimeo link.
2. [x] **Hands-on Lab Verification:**
   - Lab 1 and Lab 2 completion certificates confirmed for all team members.
3. [x] **Artifacts & Metrics Integrity:**
   - Un-ignored and committed `out/bench.json`.
   - Validated and committed `out/cbom.json` (CycloneDX 1.6 format).
   - `out/metrics.json` verified with zero hardcoded discrepancies.
4. [x] **Security & Secrets Scrubbing:**
   - Ran automated scan for secrets: no `.env`, private keys (`keys/*.key`), or raw passwords in git history.
   - Scrypt password generation implemented in `run_all.sh`.
   - Role protection on all mutation endpoints verified via pytest.
5. [x] **Team Alignment:**
   - Entire team reviewed `docs/primer.md` for live judge Q&A prep.
   - Demo reset script (`scripts/reset_demo.sh`) tested and operational.
6. [x] **Early Submission Target:**
   - Final PR merged and submitted at least 60 minutes prior to portal close.
