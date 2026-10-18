"""Reclassify the unchanged synthetic database once for a paired crypto comparison.

Run inside the API image after retraining. Preserve original predictions; both
snapshots use the same model/sample so sampling noise cannot mimic a TLS fix.
"""
import datetime
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from chronos.common import store
from chronos.shelflife import model, serve


def main():
    trained=model.CategoryModel.load()
    predictions=serve.classify_database(trained,overrides=store.get('overrides',{}))
    store.put('shelflife',predictions)
    for name in ('before','after'):
        folder=Path(store.ROOT)/'runs'/name
        old=folder/'shelflife.json'
        backup=folder/'shelflife.original.json'
        if old.exists() and not backup.exists(): shutil.copy2(old,backup)
        old.write_text(json.dumps(predictions,indent=1))
        old.chmod(0o644)
        if backup.exists(): backup.chmod(0o644)
    control={'measured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'backend':trained.backend,'model_version':model.MODEL_VERSION,'columns':len(predictions),
             'design':'One real in-database profile and classifier held constant across both snapshots; the seeded database is unchanged by crypto remediation.'}
    (Path(store.ROOT)/'runs'/'classification_control.json').write_text(json.dumps(control,indent=2))
    print(json.dumps(control))


if __name__=='__main__': main()
