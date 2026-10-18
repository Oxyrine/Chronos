FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv libpython3.12t64 python3-numpy python3-scipy python3-sklearn python3-joblib python3-yaml python3-pyjks python3-fake-factory python3-cryptography python3-fastapi python3-httpx python3-psycopg2 python3-jwt postgresql-client libgomp1 make ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --system-site-packages /venv && /venv/bin/pip install --no-cache-dir 'jsonschema>=4.18' referencing 'httpx>=0.27,<0.28' uvicorn pytest pyjwt && /venv/bin/pip install --no-cache-dir --no-deps snapml
ENV PATH=/venv/bin:$PATH
RUN python -c 'from snapml import BoostingMachineClassifier; print("Snap ML import verified (CPU fallback allowed)")'
WORKDIR /opt/chronos
