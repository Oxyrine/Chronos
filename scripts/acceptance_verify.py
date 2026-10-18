"""Real VM negative acceptance. Run in the verifier after normal approvals.

The deliberately broken config runs only in an isolated sandbox. Ledger
tampering uses a temporary copy, leaving deployed configs and ledger intact.
"""
import json
import os
from pathlib import Path
import tempfile
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chronos.verify.attest import ledger
from chronos.verify.sandbox import root_path, sandbox


def main():
    root=root_path(); target=root/'demo/portal/nginx.conf'; original=target.read_bytes()
    broken=re.sub(r'ssl_ecdh_curve\s+[^;]+;', 'ssl_ecdh_curve DEFINITELY_NOT_A_GROUP;',original.decode())
    record={'target':'demo/portal/nginx.conf','rendered':broken,'proposal':{'proposal_id':'P-9999'}}
    error=None
    try:
        with sandbox(record):
            raise AssertionError('broken config unexpectedly became healthy')
    except RuntimeError as exc:
        error=str(exc)
    assert error and 'DEFINITELY_NOT_A_GROUP' in error,error
    assert target.read_bytes()==original,'sandbox modified deployed config'
    real=ledger(); original_status=real.verify()
    assert original_status['chain_ok'] and original_status['entries']>0,original_status
    entries=real.entries(); entries[0]['approved_by']='tampered-copy'
    with tempfile.TemporaryDirectory() as temp:
        copy=Path(temp)/'attestations.jsonl'
        copy.write_text(''.join(json.dumps(e)+'\n' for e in entries))
        from chronos.verify.ledger import Ledger
        tamper_status=Ledger(copy,real.signer).verify()
    assert tamper_status['chain_ok'] is False and tamper_status['bad_seq']==1,tamper_status
    result={'broken_config_rejected':True,'deployed_file_unchanged':True,'sandbox_evidence':error,
            'actual_ledger':original_status,'tampered_copy':tamper_status}
    out=Path(os.environ.get('CHRONOS_OUT',root/'out'))/'acceptance'
    out.mkdir(exist_ok=True)
    (out/'negative-checks.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
