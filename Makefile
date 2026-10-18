PY ?= python3
.PHONY: test test-contracts test-discovery test-shelflife test-risk test-api corpus train eval

test-contracts: ; CHRONOS_ROUNDS=40 $(PY) -m pytest -q tests/test_contracts.py
test-discovery: ; CHRONOS_ROUNDS=40 $(PY) -m pytest -q tests/test_discovery.py
test-shelflife: ; CHRONOS_ROUNDS=40 $(PY) -m pytest -q tests/test_shelflife.py
test-risk:      ; CHRONOS_ROUNDS=40 $(PY) -m pytest -q tests/test_risk.py
test-api:       ; CHRONOS_ROUNDS=40 $(PY) -m pytest -q tests/test_api_and_eval.py
test:           ; CHRONOS_ROUNDS=40 $(PY) -m pytest -q

corpus: ; $(PY) -m data.gen_schemas          # seed 7, ~20 s; writes data/generated/columns.jsonl and data/labels.yaml
train:  corpus ; $(PY) -m chronos.shelflife.train   # run on the VM: the model is only ever loaded on the machine that trained it
eval:   ; ./scripts/eval_all.sh              # writes out/metrics.json; add --full for leave-one-domain-out

test-agent: ; $(PY) -m pytest -q tests/test_agent.py
test-verify: ; $(PY) -m pytest -q tests/test_verify.py tests/test_ledger.py
pregenerate: ; $(PY) -m chronos.agent.pregenerate   # after POST /scan; set CHRONOS_AGENT_MODE=granite with the llm profile up
