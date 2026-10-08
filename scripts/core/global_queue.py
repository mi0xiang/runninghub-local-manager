"""Account-wide FIFO; caller must hold hub.process.lock. No workflow edits."""
import datetime,hashlib,json,os
from pathlib import Path
from local_control import read,save,now
from api_policy import due
ACTIVE={'RUNNING','QUEUED','UPLOADING','SUBMITTING_OUTCOME_UNKNOWN','REJECTED_OR_UNKNOWN','QUERY_RATE_LIMITED','RETRY_QUERY_OR_DOWNLOAD'}
UNKNOWN={'UPLOADING','SUBMITTING_OUTCOME_UNKNOWN','REJECTED_OR_UNKNOWN'}
DONE={'ARCHIVED','DOWNLOADED','FAILED','CANCELLED','REJECTED','EXCLUDED_BY_USER'}
WAIT={'WAITING','WAITING_CAPACITY','WAITING_INSTANCE'}

def select(jobs,external):
 if external is None or any(j.get('status') in UNKNOWN for j in jobs):return []
 occupied=sum(j.get('status') in ACTIVE or (bool(j.get('taskId')) and j.get('status') not in DONE|{'CLOUD_SUCCEEDED','DOWNLOADING','DOWNLOAD_ERROR'}) for j in jobs)
 slots=max(0,3-max(occupied,external));out=[]
 for j in sorted(jobs,key=lambda j:j.get('order',0)):
  if j.get('status') not in WAIT or j.get('taskId') or j.get('blocked'):continue
  if j['status']!='WAITING' and not due(j):break
  out.append(j)
  if len(out)>=slots:break
 return out[:slots]

def signature(approval):
 return hashlib.sha256(json.dumps(approval,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def scan(root):
 root=root.resolve()
 old=read(root/'queue_state.json',{'jobs':[]});known={j['id']:j for j in old['jobs']};jobs=[];entries=read(root/'projects.json')['projects']
 discovered=[];seen_paths={};duplicate_aliases=[]
 for e in entries:
  folder=(root/e['path']).resolve()
  if not folder.is_relative_to((root/'projects').resolve()):raise ValueError('Project path escape')
  if folder in seen_paths:
   duplicate_aliases.append({'project':e['id'],'canonical_project':seen_paths[folder],'previous_jobs':[j for j in old['jobs'] if j.get('project')==e['id']]})
   continue  # One physical approved batch can enter the account queue only once.
  seen_paths[folder]=e['id']
  a=read(folder/'approval.json',{});authorized=a.get('status')=='APPROVED' and a.get('submit_permitted') is True and a.get('upload_permitted') is True and e.get('mode')!='archive_only'
  approvals={b['name']:b for b in a.get('approved_batches',[])}
  for index,name in enumerate(read(folder/'batches.json',[])):
   d=(folder/name).resolve()
   if d.parent!=folder:raise ValueError('Batch path escape')
   s=read(d/'task_state.json',{});ident=e['id']+'/'+name;previous=known.get(ident,{})
   if not s and not (authorized and name in approvals):continue
   m=read(d/'manifest.json',{});j=dict(previous,id=ident,project=e['id'],source_project=e.get('source_project',e['id']),title=e['title'],batch=name,path=d.relative_to(root).as_posix(),status=s.get('status','WAITING'),taskId=s.get('taskId'),reason=s.get('reason',''),instanceType=s.get('requestedInstanceType') or m.get('instanceType'),nextSubmitAt=s.get('nextSubmitAt'),lastCheckedAt=s.get('lastCheckedAt'),submittedAt=s.get('submittedAt'))
   j.pop('blocked',None)
   if j['status'] in WAIT:
    if not authorized or name not in approvals:j.update(blocked='批准已撤回',status='NEEDS_REVIEW')
    else:
     digest=signature(approvals[name]);j.setdefault('approvedFingerprint',digest)
     if j['approvedFingerprint']!=digest:j.update(blocked='入队后批准快照变化，需要新版本',status='NEEDS_REVIEW')
     dep=m.get('depends_on')
     if e.get('pipeline')=='continuous_speaker' and a.get('reference_strategy')!='fixed_first_frame' and index>0:dep=read(folder/'batches.json')[index-1]
     if dep:
      if not isinstance(dep,str) or (folder/dep).resolve().parent!=folder:j['blocked']='依赖路径无效'
      elif read(folder/dep/'task_state.json',{}).get('status')!='ARCHIVED':j['blocked']='等待前段下载归档：'+dep
     if (folder/'execution-plan.json').is_file():
      import project_runner
      gate=project_runner.generation_gate(folder,name)
      if gate:j['blocked']=gate
   if 'order' not in j:discovered.append((a.get('approvedAt') or e.get('updatedAt',''),index,j))
   jobs.append(j)
 order=max([j.get('order',0) for j in known.values()]+[0])
 for _,_,j in sorted(discovered,key=lambda x:(x[0],x[1],x[2]['id'])):order+=1;j['order']=order;j['enqueuedAt']=now()
 snapshot={'updatedAt':now(),'limit':3,'jobs':sorted(jobs,key=lambda j:j['order']),'account':old.get('account',{}),'duplicate_aliases':duplicate_aliases}
 save(root/'queue_state.json',snapshot);return snapshot

def account(secret):
 from runninghub_transport import post
 response=post('/uc/openapi/accountStatus',{'apikey':secret},secret)
 if response.get('code')!=0:raise ValueError('Account status unavailable')
 value=response.get('data',{}).get('currentTaskCounts')
 if value is None or isinstance(value,bool):raise ValueError('Account occupancy unavailable')
 count=int(value)
 if count<0:raise ValueError('Invalid account occupancy')
 return count

def verify(root,j):
 d=root/j['path'];folder=d.parent;a=read(folder/'approval.json');b=next(x for x in a['approved_batches'] if x['name']==j['batch'])
 if not (a.get('status')=='APPROVED' and a.get('upload_permitted') is True and a.get('submit_permitted') is True):raise ValueError('Approval revoked')
 if signature(b)!=j['approvedFingerprint']:raise ValueError('Approval changed after enqueue')
 for rel,h in b['hashes'].items():
  f=(d/rel).resolve()
  if not f.is_relative_to(d.resolve()) or hashlib.sha256(f.read_bytes()).hexdigest()!=h:raise ValueError('Approved file changed: '+rel)
 return a

def schedule(root,force_project=None,submit=True):
 root=root.resolve()
 import collector,run_approved_queue as submitter
 snapshot=scan(root);secret=None;results=[]
 # Query every known nonterminal job, even when its old approval is no longer active.
 for j in snapshot['jobs']:
  if not j.get('taskId') or j['status'] in DONE|{'CLOUD_SUCCEEDED','DOWNLOADING','DOWNLOAD_ERROR'}:continue
  d=root/j['path'];s=read(d/'task_state.json',{})
  try:
   age=(datetime.datetime.now().astimezone()-datetime.datetime.fromisoformat(s.get('submittedAt',now()))).total_seconds()
   forced=force_project in (j['project'],j['source_project'],'*')
   if age<480 and not forced:continue
   secret=secret or collector.key();collector.ROOT=d.parent
   result=collector.collect(d,secret,query_only=True);s.update(result,lastCheckedAt=now());save(d/'task_state.json',s)
   results.append({'batch':j['batch'],'status':s['status']})
  except Exception as exc:results.append({'batch':j['batch'],'error':type(exc).__name__})
 snapshot=scan(root)
 # Recheck account before each create; local reservation remains authoritative if account lags.
 while submit:
  if not select(snapshot['jobs'],0):break
  try:
   secret=secret or collector.key();external=account(secret);snapshot['account']={'occupied':external,'checkedAt':now()}
  except Exception as exc:snapshot['account']={'occupied':None,'checkedAt':now(),'error':type(exc).__name__};break
  candidates=select(snapshot['jobs'],external)
  if not candidates:break
  j=candidates[0];d=root/j['path']
  try:
   a=verify(root,j);entry=next(e for e in read(root/'projects.json')['projects'] if e['id']==j['project'])
   if entry.get('pipeline')=='continuous_speaker':
    import speaker_pipeline as sp
    folder=d.parent;names=read(folder/'batches.json');idx=names.index(j['batch']);fixed=a.get('reference_strategy')=='fixed_first_frame'
    if not read(folder/'workflow_preflight.json',{}).get('existing_workflow_schema_reused'):raise ValueError('Speaker preflight missing')
    sp.check_graph(read(d/'workflow_prepared.json'))
    previous=names[idx-1] if idx and not fixed else None
    if not fixed:sp.bind(folder,j['batch'],previous)
    sp.verify_bound(folder,j['batch'],previous,a)
   submitter.R=d.parent;submitter.validate=lambda:verify(root,j)
   submitter.submit(d,secret,a['workflowId'])
  except Exception as exc:
   state=read(d/'task_state.json',{})
   if not state or state.get('status') in WAIT:save(d/'task_state.json',dict(state,status='NEEDS_REVIEW',reason=type(exc).__name__+': '+str(exc)[:180]))
  acct=snapshot['account'];snapshot=scan(root);snapshot['account']=acct
 save(root/'queue_state.json',snapshot)
 for e in read(root/'projects.json')['projects']:
  rows=[j for j in snapshot['jobs'] if j['project']==e['id']]
  if not rows:continue
  folder=root/e['path'];states={j['batch']:j['status'] for j in rows}
  state='COMPLETE' if all(s in DONE for s in states.values()) else 'WAITING'
  if any(s in {'FAILED','NEEDS_REVIEW'}|UNKNOWN for s in states.values()):state='NEEDS_REVIEW'
  save(folder/'tracker_status.json',{'state':state,'updatedAt':now(),'batches':states})
 return results

def download(root):
 import collector
 secret=None
 for j in read(root/'queue_state.json',{'jobs':[]})['jobs']:
  d=root/j['path'];s=read(d/'task_state.json',{})
  if s.get('status') not in ('CLOUD_SUCCEEDED','DOWNLOADING','DOWNLOAD_ERROR'):continue
  if s.get('integrityBlocked'):continue  # Existing damaged originals require explicit recovery review.
  if s.get('status')=='DOWNLOAD_ERROR' and not due(s,'nextDownloadAt'):continue
  try:
   s.update(status='DOWNLOADING');save(d/'task_state.json',s)
   secret=secret or collector.key();collector.ROOT=d.parent;s.update(collector.collect(d,secret),lastCheckedAt=now());save(d/'task_state.json',s)
  except Exception as exc:
   from api_policy import next_time
   attempts=s.get('downloadAttempts',0)+1;s.update(status='DOWNLOAD_ERROR',reason=type(exc).__name__,downloadAttempts=attempts,nextDownloadAt=next_time(attempts));save(d/'task_state.json',s)
