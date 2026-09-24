"""Ordered per-segment versions and explicit local assembly jobs."""
from pathlib import Path
import re,json
import local_control as lc
read=lc.read;save=lc.save

def context(root,pid):
 from control_server import project
 entry,p=project(root,pid)
 names=read(p/'batches.json',[]);state=read(p/'assembly_selection.json',{'order':names,'pinned':{}})
 state['order']=list(names)  # Dialogue/audio sequence is authoritative, including legacy saved selections.
 return entry,p,names,state

def view(root,pid):
 from version_timing import timing
 entry,p,names,state=context(root,pid);reg=read(root/'projects.json')['projects'];segments=[]
 for batch in state['order']:
  candidates=[entry]+sorted([x for x in reg if x.get('source_project')==pid and x.get('source_batch')==batch],key=lambda x:x.get('updatedAt',''))
  versions=[]
  for idx,e in enumerate(candidates,1):
   d=root/e['path']/batch;s=read(d/'task_state.json',{});target=d/'results'/('task-'+str(s.get('taskId','')));a=read(target/'manifest.json',{});files=a.get('files',[])
   video=target/files[0]['name'] if len(files)==1 else None
   ready=s.get('status')=='ARCHIVED' and video is not None and video.is_file() and video.resolve().is_relative_to(target.resolve())
   versions.append({**timing(s,a),'id':e['id'],'label':'V'+str(idx),'createdAt':e.get('updatedAt',''),'status':s.get('status','WAITING'),'ready':ready,'video':video.relative_to(root).as_posix() if ready else None,'taskId':s.get('taskId'),'sha256':files[0].get('sha256') if ready else None,'nextSubmitAt':s.get('nextSubmitAt'),'nextQueryAt':s.get('nextQueryAt'),'failure':s.get('failure') or read(d/'failure.json',{}),'reason':s.get('reason',''),'instanceType':s.get('requestedInstanceType') or read(d/'manifest.json',{}).get('instanceType'),'review':state.get('rejected',{}).get(batch,{}).get(e['id'])})
  pinned=state.get('pinned',{}).get(batch);ready=[v for v in versions if v['ready'] and not v['review']]
  selected=pinned or (ready[-1]['id'] if ready else None)
  if pinned and not any(v['id']==pinned and v['ready'] and not v['review'] for v in versions):selected=None
  final=state.get('finalized',{}).get(batch)
  chosen=next((v for v in versions if v['id']==selected and v['ready']),None)
  finalized=bool(final and chosen and final['version']==selected and final['sha256']==chosen['sha256'] and final['taskId']==chosen['taskId'])
  segments.append({'batch':batch,'selected':selected,'pinned':bool(pinned),'versions':versions,'finalized':finalized,'finalization':final if finalized else None})
 assemblies=[]
 if (p/'final/continuous_speaker.mp4').exists():assemblies.append({'id':'original','state':'COMPLETE','label':'初始自动合成','video':(p/'final/continuous_speaker.mp4').relative_to(root).as_posix()})
 for request in sorted((p/'manual_assemblies').glob('*/request.json')):
  q=read(request);s=read(request.parent/'status.json',{});video=request.parent/'final/continuous_speaker.mp4'
  assemblies.append({'id':request.parent.name,'createdAt':q['createdAt'],'label':'人工合成 '+q['createdAt'],'state':s.get('state','QUEUED'),'video':video.relative_to(root).as_posix() if s.get('state')=='COMPLETE' and video.exists() else None,'selection':q['selection'],'reason':s.get('reason','')})
 fingerprint=[{'batch':x['batch'],'version':x['selected']} for x in segments]
 assemblies.sort(key=lambda x:x.get('createdAt',''))
 complete=[x for x in assemblies if x['video']];latest=complete[-1] if complete else None
 initial=[{'batch':n,'version':pid} for n in names]
 current_fingerprint=([{'batch':x['batch'],'version':x['version']} for x in latest.get('selection',[])]) if latest and latest['id']!='original' else initial
 assembly_ready=bool(segments) and all(x['selected'] for x in segments)
 all_finalized=all(x['finalized'] for x in segments) and bool(segments)
 review=read(p/'final_review.json',{})
 final_approved=bool(assembly_ready and latest and review.get('assembly')==latest['id'] and review.get('fingerprint')==fingerprint and fingerprint==current_fingerprint and review.get('status')=='APPROVED')
 return {'order':state['order'],'segments':segments,'assemblies':assemblies,'current_final':latest,'assembly_ready':assembly_ready,'needs_assembly':not latest or fingerprint!=current_fingerprint,'fingerprint':fingerprint,'all_finalized':all_finalized,'final_approved':final_approved}

def choose(root,pid,batch,version,confirmed):
 if confirmed is not True:raise ValueError('Confirm review and finalization')
 _,p,names,state=context(root,pid)
 if batch not in names:raise ValueError('Unknown segment')
 if version=='latest':
  state.setdefault('pinned',{}).pop(batch,None);state.setdefault('finalized',{}).pop(batch,None)
 else:
  segment=next(x for x in view(root,pid)['segments'] if x['batch']==batch)
  if not any(v['id']==version and v['ready'] for v in segment['versions']):raise ValueError('Version is not downloaded and ready')
  from control_server import project
  import speaker_pipeline as sp
  _,source=project(root,version);video,task=sp.archive_video(source,batch)
  state.setdefault('pinned',{})[batch]=version
  state.setdefault('finalized',{})[batch]={'version':version,'sha256':sp.sha(video),'taskId':task,'reviewedAt':lc.now(),'status':'APPROVED'}
  state.setdefault('rejected',{}).setdefault(batch,{}).pop(version,None)
 state['updatedAt']=lc.now();save(p/'assembly_selection.json',state);return view(root,pid)

def reject(root,pid,batch,version,confirmed):
 if confirmed is not True:raise ValueError('Review rejection needs confirmation')
 _,p,names,state=context(root,pid)
 segment=next((x for x in view(root,pid)['segments'] if x['batch']==batch),None)
 if not segment or not any(v['id']==version for v in segment['versions']):raise ValueError('Unknown version')
 state.setdefault('rejected',{}).setdefault(batch,{})[version]={'status':'REJECTED','reviewedAt':lc.now()}
 if state.get('finalized',{}).get(batch,{}).get('version')==version:state['finalized'].pop(batch,None)
 save(p/'assembly_selection.json',state);return view(root,pid)

def approve_final(root,pid,assembly,confirmed):
 if context(root,pid)[0].get('pipeline')!='continuous_speaker':raise ValueError('Standalone clips do not have an assembly timeline')
 if confirmed is not True:raise ValueError('Final review confirmation required')
 info=view(root,pid)
 if not info['assembly_ready']:raise ValueError('部分片段没有可用版本，请完成生成或选择可用版本')
 if info['needs_assembly']:raise ValueError('现有成片与定稿不同，请先重新拼接')
 current=info['current_final']
 if not current or current['id']!=assembly:raise ValueError('成片已变化，请刷新后复核')
 _,p,_,_=context(root,pid)
 import speaker_pipeline as sp
 from control_server import project
 video=root/current['video'];manifest=read(video.parent/'manifest.json',{})
 if manifest.get('sha256')!=sp.sha(video):raise ValueError('Final output hash changed')
 sources=[]
 for segment in info['segments']:
  _,source=project(root,segment['selected']);source_video,_=sp.archive_video(source,segment['batch']);sources.append(sp.sha(source_video))
 if sources!=manifest.get('source_sha256'):raise ValueError('成片来源与当前定稿不匹配')
 review={'status':'APPROVED','assembly':assembly,'fingerprint':info['fingerprint'],'sha256':manifest['sha256'],'reviewedAt':lc.now(),'source':'Explicit final review click; no regeneration or reassembly'}
 save(p/'final_review.json',review)
 with (p/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'time':lc.now(),'event':'final_review_approved','status':'APPROVED','assembly':assembly},ensure_ascii=False)+'\n')
 return view(root,pid)

def reorder(root,pid,order):
 if context(root,pid)[0].get('pipeline')!='continuous_speaker':raise ValueError('Standalone clips do not have an assembly timeline')
 _,p,names,state=context(root,pid)
 if order!=names:raise ValueError('台词与音频顺序固定，不支持调整片段顺序')
 state.update(order=order,updatedAt=lc.now());save(p/'assembly_selection.json',state);return view(root,pid)

def enqueue(root,pid,request_id,confirmed,expected=None):
 if context(root,pid)[0].get('pipeline')!='continuous_speaker':raise ValueError('Standalone clips do not have an assembly timeline')
 if confirmed is not True or not re.fullmatch('[a-f0-9]{32}',request_id):raise ValueError('Explicit assembly confirmation and request id required')
 _,p,names,state=context(root,pid);job=p/'manual_assemblies'/request_id
 if (job/'request.json').exists():return {'job_id':request_id,'duplicate':True}
 info=view(root,pid)
 if not info['assembly_ready']:raise ValueError('部分片段没有可用版本，请完成生成或选择可用版本')
 if expected is not None and info['fingerprint']!=expected:raise ValueError('选用版本刚刚变化，请刷新后重新确认拼接')
 from control_server import project
 import speaker_pipeline as sp
 selected=[]
 for segment in info['segments']:
  if not segment['selected']:raise ValueError('Every segment needs a ready selected version')
  _,source=project(root,segment['selected']);video,task=sp.archive_video(source,segment['batch'])
  selected.append({'batch':segment['batch'],'version':segment['selected'],'taskId':task,'source_video':video.relative_to(root).as_posix(),'sha256':sp.sha(video)})
 # Compare actual source hashes too; unchanged versions cannot conceal changed media.
 current=info['current_final']
 if not info['needs_assembly'] and current:
  manifest=read((root/current['video']).parent/'manifest.json',{})
  if manifest.get('source_sha256')==[x['sha256'] for x in selected] and manifest.get('sha256')==sp.sha(root/current['video']):
   return {'unchanged':True,'duplicate':False,'assembly_id':current['id']}
 for existing in (p/'manual_assemblies').glob('*/request.json'):
  q=read(existing);status=read(existing.parent/'status.json',{})
  if q.get('selection')==selected and status.get('state') in ('QUEUED','RUNNING','LOCAL_STOPPED'):
   return {'job_id':existing.parent.name,'duplicate':True}
 job.mkdir(parents=True,exist_ok=True)
 save(job/'request.json',{'project':pid,'createdAt':lc.now(),'selection':selected,'source':'Explicit manual assembly click; frozen order and selected versions'})
 save(job/'status.json',{'state':'QUEUED','updatedAt':lc.now()});return {'job_id':request_id,'duplicate':False}

def process(root,pid):
 if context(root,pid)[0].get('pipeline')!='continuous_speaker':raise ValueError('Standalone clips do not have an assembly timeline')
 _,p,names,_=context(root,pid)
 import speaker_pipeline as sp
 from control_server import project
 for request in sorted((p/'manual_assemblies').glob('*/request.json')):
  lc.checkpoint();job=request.parent;s=read(job/'status.json',{})
  if s.get('state') not in ('QUEUED','RUNNING','LOCAL_STOPPED'):continue
  try:
   q=read(request);paths=[]
   if [x['batch'] for x in q['selection']]!=names:raise ValueError('拼接顺序必须与原始台词和音频顺序一致')
   for item in q['selection']:
    _,source=project(root,item['version']);video,task=sp.archive_video(source,item['batch'])
    if task!=item['taskId'] or sp.sha(video)!=item['sha256'] or video.relative_to(root).as_posix()!=item['source_video']:raise ValueError('Selected source changed since confirmation')
    paths.append(video)
   save(job/'status.json',{'state':'RUNNING','updatedAt':lc.now()});lc.phase('MANUAL_ASSEMBLY',project=pid)
   result=sp.concat(job,[x['batch'] for x in q['selection']],sources=paths)
   save(job/'status.json',{'state':'COMPLETE','updatedAt':lc.now(),'sha256':result['sha256']})
   sp.event(p,'manual_assembly_complete',status='COMPLETE',job=job.name)
  except lc.LocalStop:
   save(job/'status.json',{'state':'LOCAL_STOPPED','updatedAt':lc.now()});raise
  except Exception as exc:
   save(job/'status.json',{'state':'FAILED','updatedAt':lc.now(),'reason':str(exc)[:200]})
