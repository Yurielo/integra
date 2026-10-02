import hashlib,json,os,stat
from pathlib import Path
before_path=Path('/private/tmp/integra-212-protected-before.json')
before=json.loads(before_path.read_text());base=Path.home()/'Library/Application Support/Integra'
roots=[base/'Build Archive/retained',base/'Recovery Archive',base/'Build Archive Recovery',base/'Candidate Builds']
after={}
for root in roots:
 for parent,dirs,files in os.walk(root,followlinks=False):
  for p in [Path(parent),*[Path(parent)/x for x in files],*[Path(parent)/x for x in dirs if (Path(parent)/x).is_symlink()]]:
   s=p.lstat();after[str(p)]=[s.st_dev,s.st_ino,s.st_size,s.st_mode,s.st_mtime_ns,s.st_ctime_ns]
for key,value in before.items():
 if isinstance(value,str):after[key]=hashlib.sha256(Path(key).read_bytes()).hexdigest()
changed=[key for key in before if key in after and before[key]!=after[key]]
missing=sorted(set(before)-set(after));added=sorted(set(after)-set(before))
canonical=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
result={'validation':'PROTECTED_ARTIFACT_PRESERVATION','before_snapshot_sha256':hashlib.sha256(before_path.read_bytes()).hexdigest(),'entries_before':len(before),'entries_after':len(after),'before_stat_identity_digest':canonical(before),'after_stat_identity_digest':canonical(after),'changed':changed,'missing':missing,'added':added,'protected_roots':[str(x) for x in roots],'checks':['device','inode','size','mode','mtime_ns','ctime_ns'],'governance_json_sha256':{key:after[key] for key,value in before.items() if isinstance(value,str)},'payload_scope':'metadata invariance of all entries; no repeated full-payload hashes; readonly runtime subset verified separately','result':'PASS' if not(changed or missing or added) else 'FAIL'}
Path('/private/tmp/integra-212-protected-preservation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));assert result['result']=='PASS'
