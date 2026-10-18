"""Run in chronos-base so OPENSSL_CONF controls groups before Python starts.

Each profile runs in a separate process with its own OpenSSL system_default.
All data is synthetic. No route outside the fixed demo endpoints is accepted.
"""
import argparse
import json
import os
from pathlib import Path
import random
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request

PROFILES = {
    'patients': ('X25519:prime256v1', 'portal', 8443, ['/api/patients/1','/api/reminders/1']),
    'clinicians': ('X25519MLKEM768:X25519', 'portal', 8443, ['/api/records/1','/api/labs/1','/api/genomics/1']),
    'partner': ('X25519:prime256v1', 'lab-api', 8001, ['/forward/1']),
    'harvester': ('X25519:prime256v1', 'portal', 8443, ['/api/patients/export?limit=100']),
}


def run(profile, seconds, seed):
    _, host, port, routes = PROFILES[profile]
    context=ssl.create_default_context(cafile=os.environ.get('CHRONOS_CA','/keys/ca.pem'))
    rng=random.Random(seed); end=time.monotonic()+seconds; latencies=[]
    result={'profile':profile,'success':0,'failed':0,'duration_s':seconds,'openssl':ssl.OPENSSL_VERSION}
    while time.monotonic()<end:
        try:
            started=time.monotonic()
            request=urllib.request.Request(f'{"http" if profile=="partner" else "https"}://{host}:{port}{rng.choice(routes)}', data=b'' if profile=='partner' else None)
            with urllib.request.urlopen(request,context=context,timeout=5) as response:
                response.read(); result['success']+=1
                latencies.append(time.monotonic()-started)
        except Exception:
            result['failed']+=1
        time.sleep(.15 if profile=='harvester' else .5)
    latencies.sort()
    result['latency_ms']={f'p{q}': round(latencies[min(len(latencies)-1,int(len(latencies)*q/100))]*1000,3) if latencies else None for q in (50,95)}
    result['requests_per_s']=round(result['success']/seconds,3)
    print(json.dumps(result))


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--seconds',type=int,default=60); parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--profile',choices=PROFILES); args=parser.parse_args()
    if args.profile:
        return run(args.profile,args.seconds,args.seed)
    children=[]
    with tempfile.TemporaryDirectory() as tmp:
        for i,(profile,(groups,*_)) in enumerate(PROFILES.items()):
            conf=Path(tmp)/f'{profile}.cnf'
            conf.write_text(f'openssl_conf = default_conf\n[default_conf]\nssl_conf = ssl_sect\n[ssl_sect]\nsystem_default = system_default_sect\n[system_default_sect]\nGroups = {groups}\n')
            children.append(subprocess.Popen([sys.executable,'-m','chronos.stream.loadgen','--profile',profile,'--seconds',str(args.seconds),'--seed',str(args.seed+i)],env={**os.environ,'OPENSSL_CONF':str(conf)},stdout=subprocess.PIPE,text=True))
        results=[]
        for child in children:
            stdout,_=child.communicate(timeout=args.seconds+30)
            if child.returncode: raise RuntimeError(f'load generator exited {child.returncode}')
            results.append(json.loads(stdout))
        print(json.dumps({'synthetic':True,'profiles':results},indent=2))


if __name__=='__main__': main()
