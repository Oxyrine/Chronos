"""Unit signing uses HMAC explicitly; real ML-DSA acceptance belongs to the worker VM."""
import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from chronos.verify.ledger import Ledger, canonical


class TestSigner:
    __test__ = False
    def sign(self, payload):
        return hmac.digest(b'unit-test-only', payload, hashlib.sha256)

    def verify(self, payload, signature):
        return hmac.compare_digest(self.sign(payload), signature)


def evidence(pid='P-0001'):
    return {'ts': '2026-10-18T00:00:00Z', 'proposal_id': pid, 'approved_by': 'secops',
            'verification_sha256': '1' * 64, 'cbom_sha256': '2' * 64}


def test_chain_and_signature_cover_evidence(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.jsonl', TestSigner())
    first = ledger.append(evidence())
    second = ledger.append(evidence('P-0002'))
    assert second['prev_hash'] == first['entry_hash']
    assert ledger.verify()['chain_ok'] is True
    lines = ledger.entries()
    lines[1]['approved_by'] = 'attacker'
    ledger.path.write_text('\n'.join(json.dumps(line) for line in lines) + '\n')
    assert ledger.verify() == {'chain_ok': False, 'bad_seq': 2}
    with pytest.raises(ValueError, match='corrupted'):
        ledger.append(evidence())


@pytest.mark.parametrize('mutation', ['sig_b64', 'prev_hash', 'entry_hash', 'seq', 'alg'])
def test_tamper_detected(tmp_path, mutation):
    ledger = Ledger(tmp_path / 'ledger.jsonl', TestSigner())
    entry = ledger.append(evidence())
    entry[mutation] = 9 if mutation == 'seq' else 'tampered'
    ledger.path.write_text(json.dumps(entry) + '\n')
    assert ledger.verify() == {'chain_ok': False, 'bad_seq': 1}


def test_malformed_line_reports_position(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.jsonl', TestSigner())
    ledger.append(evidence())
    with ledger.path.open('a') as handle:
        handle.write('{broken\n')
    assert ledger.verify() == {'chain_ok': False, 'bad_seq': 2}


def test_concurrent_append_serialized(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.jsonl', TestSigner())
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda number: ledger.append(evidence(f'P-{number:04d}')), range(1, 9)))
    assert [entry['seq'] for entry in ledger.entries()] == list(range(1, 9))
    assert ledger.verify()['chain_ok'] is True


def test_canonical_order_ignores_derived_fields():
    assert canonical({'b': 2, 'a': 1, 'sig_b64': 'x', 'entry_hash': 'y'}) == b'{"a":1,"b":2}'
