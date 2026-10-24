"""Invoke the accepted canonical exact-withdrawal transaction, without bypasses."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path('/private/tmp/integra-issue279-k2-supersession')
OUT=Path(__file__).parent
assert not subprocess.check_output(['git','-C',ROOT,'status','--porcelain'],text=True)
assert subprocess.check_output(['git','-C',ROOT,'rev-parse','HEAD'],text=True)==subprocess.check_output(['git','-C',ROOT,'rev-parse','origin/main'],text=True)
sys.path.insert(0,str(ROOT))
from scripts import candidate_retention as retention

identity=dict(candidate_id='candidate-v1-19e3438fea443e1d917b6575131fd67b47b5f44f71202a6940f85adda12b3b56',
              bundle_digest='1fe98fb2822b50077f78f22db960dc1f457f5b6374736a3dace704e99e8fe7e0',
              manifest_digest='0704fd913f525d050cdf52f16eefae938cd6d2c9776c92abaf39881f7973efbb')
hashes={'current_product_baseline_v2.json':'bdd2ea30b3102c59cd8e47bc56a0d53c6b57d3bfb0347e667663b1be951e52e2',
        'current_canonical_baseline_v1.json':'0493fbad50f1a5518b01be90e3ffb0cd10d3d8b7a97ae12918fc4595c4438840'}
def current():
    for name,digest in hashes.items():
        assert hashlib.sha256((ROOT/'state'/name).read_bytes()).hexdigest()==digest
def save(name,value): (OUT/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
current()
root=Path.home()/'Library/Application Support/Integra/Build Archive'
catalog=retention.catalog_path(root)
before=json.loads(catalog.read_bytes());save('catalog-before-exact-retirement.json',before)
assert not before.get('deletions'), 'existing journal needs governed recovery'
paths=retention.cleanup_exact(catalog,identity)
after=json.loads(catalog.read_bytes());save('catalog-after-exact-retirement.json',after)
records=[r for tid,r in after.get('retirements',{}).items()
         if tid not in before.get('retirements',{}) and r.get('candidate_id')==identity['candidate_id']]
assert len(paths)==1 and len(records)==1
assert records[0]['state']=='RETIRED_NOT_AVAILABLE' and records[0]['execution_result']=='PASS'
assert not Path(paths[0]).exists()
current()
save('exact-retirement-receipt.json',dict(status='PASS',strategy='EXACT_OWNER_AUTHORIZED_WITHDRAWAL_RETIREMENT',
     paths=paths,physical_retirement=records[0],publication_sequence=before['artifacts'][paths[0]]['publication_sequence'],
     current_unchanged=True))
print(json.dumps(dict(status='PASS',paths=paths,current_unchanged=True)),flush=True)
