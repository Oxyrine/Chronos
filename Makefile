PY ?= python3
.PHONY: test test-contracts test-discovery test-shelflife test-risk test-api corpus train eval

test-contracts: ; $(PY) -m pytest -q tests/test_contracts.py
test-discovery: ; $(PY) -m pytest -q tests/test_discovery.py
test-shelflife: ; $(PY) -m pytest -q tests/test_shelflife.py
test-risk:      ; $(PY) -m pytest -q tests/test_risk.py
test-api:       ; $(PY) -m pytest -q tests/test_api_and_eval.py
test:           ; $(PY) -m pytest -q

corpus: ; $(PY) -m data.gen_schemas          # seed 7, ~20 s; writes data/generated/columns.jsonl and data/labels.yaml
train:  corpus ; $(PY) -m chronos.shelflife.train   # run on the VM: the model is only ever loaded on the machine that trained it
eval:   ; ./scripts/eval_all.sh              # writes out/metrics.json; add --full for leave-one-domain-out
