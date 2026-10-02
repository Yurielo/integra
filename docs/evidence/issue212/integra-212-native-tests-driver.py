import json,os,subprocess,sys,time,uuid,shutil
from pathlib import Path
sys.path.insert(0,'/private/tmp/integra-issue-212')
from scripts import temp_workspace_lifecycle as l, candidate_retention as r
repo=Path('/private/tmp/integra-issue-212');base=Path('/private/tmp')/('integra-212-native-'+uuid.uuid4().hex[:12]);base.mkdir()
outer,_=l.create_workspace(purpose='native-evidence-inputs',base=base,expected_bytes=512*1024**2,reserve_bytes=r.FREE_FLOOR)
store=Path.home()/'Library/Application Support/Integra/Validation'/base.name
result={'issue':212,'source':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'before_free':shutil.disk_usage(base).free,'native_runs':[],'new_archive_root':str(store),'base':str(base)}
try:
 component=outer/'seminartext'
 component.mkdir()
 subprocess.run(['git','init',str(component)],check=True,timeout=10)
 subprocess.run(['git','fetch','--depth=1','https://github.com/Yurielo/seminartext.git','13644d262776aacdf36221b9a9fc7ebd0a7c0737'],cwd=component,check=True,timeout=120)
 subprocess.run(['git','checkout','--detach','FETCH_HEAD'],cwd=component,check=True,timeout=60)
 video_component=outer/'videotext'
 video_component.mkdir()
 subprocess.run(['git','init',str(video_component)],check=True,timeout=10)
 subprocess.run(['git','fetch','--depth=1','https://github.com/Yurielo/videotext.git','2e098d1705b6815628bee1e023f4742718eabf02'],cwd=video_component,check=True,timeout=120)
 subprocess.run(['git','checkout','--detach','FETCH_HEAD'],cwd=video_component,check=True,timeout=60)
 wheels=outer/'review-wheels'
 subprocess.run([sys.executable,'-m','pip','download','--disable-pip-version-check','--require-hashes','--only-binary=:all:','-r',str(repo/'scripts/review-runtime-requirements.txt'),'--dest',str(wheels)],check=True,timeout=120)
 env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',INTEGRA_REVIEW_WHEELS=str(wheels),INTEGRA_SEMINARTEXT_BUILD_CHECKOUT=str(component),INTEGRA_VIDEOTEXT_BUILD_CHECKOUT=str(video_component),INTEGRA_BOOKTEXT_BUILD_CHECKOUT='/Users/yurielokhin/Documents/integra/.runtime-components/booktext-pinned',INTEGRA_WORD_ALIGNMENT_SITE_PACKAGES=Path('/private/tmp/integra-212-runtime-path.txt').read_text().strip())
 for label,extra in [('native-tests',['--native-tests'])]:
  command=[sys.executable,'-B',str(repo/'scripts/build_macos_candidate.py'),'--base',str(base),'--purpose','issue212-'+label,'--timeout-seconds','1800',*extra]
  start=time.monotonic();log=Path('/private/tmp')/('integra-212-'+label+'.log')
  print('RUN',label,flush=True)
  completed=subprocess.run(command,cwd=repo,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=1900)
  log.write_text(completed.stdout+'\nSTDERR\n'+completed.stderr)
  item={'label':label,'command':command,'exit':completed.returncode,'seconds':round(time.monotonic()-start,2),'log':str(log),'remaining_owned_roots':[str(p) for p in base.glob('integra-owned-*') if p!=outer]}
  if completed.returncode==0:item['result']={'validation':'NATIVE_TESTS_PASS','pass_markers':[line for line in completed.stdout.splitlines() if 'PASS' in line]}
  else:item['error_tail']=completed.stderr[-4000:]
  result['native_runs'].append(item);Path('/private/tmp/integra-212-native-tests-evidence.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in item.items() if k!='result'}),flush=True)
  if completed.returncode:break
finally:
 l.cleanup_workspace(outer,reason='NATIVE_EVIDENCE_FINISHED',allow_live_owner=True)
 result['remaining_owned_roots_after']=[str(p) for p in base.glob('integra-owned-*')]
 result['after_free']=shutil.disk_usage(base).free
 result['temporary_inputs_removed']=not outer.exists()
 Path('/private/tmp/integra-212-native-tests-evidence.json').write_text(json.dumps(result,indent=2))
 # Only this new fixture base, never a user's historical path.
 for p in base.iterdir():
  if p.is_file():p.unlink()
 base.rmdir()
