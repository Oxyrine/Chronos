"""Collect measured artifacts only; missing measurements remain explicitly pending."""
import datetime
import json
from pathlib import Path
import platform


def main():
    out=Path('out')
    def read(path):
        return json.loads(path.read_text()) if path.exists() else {'status':'pending'}
    result={'arch':platform.machine(),'measured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'synthetic':True,'nnpa_acceleration_claimed':False,
            'traffic':{name:read(out/'runs'/name/'loadgen.json') for name in ('before','after')},
            'agent':read(out/'agent_eval.json'),
            'granite_sanity':read(out/'granite_sanity.json'),
            'verification':read(out/'acceptance'/'approval-flow.json')}
    # Keep the benchmark compact; full checks and signatures remain in evidence archives.
    flow=result['verification']
    if 'results' in flow:
        result['verification']=[{'service':row['service'],'duration_s':row['verification']['duration_s'],
                                 'status':row['verification']['status']} for row in flow['results']]
    (out/'bench.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'arch':result['arch'],'bench':'out/bench.json'}))


if __name__=='__main__': main()
