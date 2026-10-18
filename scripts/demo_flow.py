"""Exercise the real API approval path inside chronos-api, after baseline snapshot.

Use --approve explicitly for acceptance on the synthetic demo. The server still
enforces owner authentication and its security_engineer dependency.
"""
import argparse
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request


def request(path, body=None):
    req=urllib.request.Request('http://localhost:8000/api'+path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+os.environ['CHRONOS_API_TOKEN'],'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=600) as response: return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'{path}: {exc.code} {exc.read().decode()}') from exc


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--approve',action='store_true'); args=parser.parse_args()
    findings=request('/findings'); results=[]
    for service,name in [('portal','nginx.conf'),('reminders','nginx.conf'),('ops-ssh','sshd_config'),('lab-api','openssl.cnf')]:
        target=f'demo/{service}/{name}'
        eligible=[f for f in findings if f.get('location',{}).get('path')==target and f.get('usage')=='key_exchange' and f.get('quantum_status')=='vulnerable']
        if not eligible: raise RuntimeError(f'no baseline vulnerable finding for {target}')
        record=request('/proposals',{'finding_id':eligible[0]['finding_id']})
        pid=record.get('proposal',record)['proposal_id']
        request(f'/proposals/{pid}/verify',{})
        for _ in range(240):
            verification=request('/verifications/'+pid)
            if verification.get('status')!='pending': break
            time.sleep(1)
        if verification.get('status')!='passed': raise RuntimeError(json.dumps(verification))
        row={'proposal_id':pid,'service':service,'verification':verification}
        if args.approve: row['attestation']=request(f'/proposals/{pid}/approve',{})
        results.append(row)
        print(json.dumps({'service':service,'proposal_id':pid,'status':'approved' if args.approve else 'verified'}),flush=True)
        # Approvals rescan and can renumber F-ids. Always select from the latest scan.
        findings=request('/findings')
    ledger=request('/ledger/verify')
    if not ledger['chain_ok']: raise RuntimeError(ledger)
    out=Path(os.environ.get('CHRONOS_OUT','out'))
    (out/'acceptance').mkdir(exist_ok=True)
    (out/'acceptance'/'approval-flow.json').write_text(json.dumps({'results':results,'ledger':ledger},indent=2))


if __name__=='__main__': main()
