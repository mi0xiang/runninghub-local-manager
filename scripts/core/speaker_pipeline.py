import portable_runtime
"""Serial digital-speaker pipeline. Called only by hub under its account lock."""
from pathlib import Path
import json, hashlib, datetime, os, subprocess, html
import local_control
from api_policy import retryable
FFMPEG=Path(portable_runtime.tool('ffmpeg')); FFPROBE=Path(portable_runtime.tool('ffprobe'))
BLOCKED={'FAILED','REJECTED','NEEDS_REVIEW','UPLOADING','SUBMITTING_OUTCOME_UNKNOWN','REJECTED_OR_UNKNOWN'}
def read(p,default=None):
 import durable_store
 return durable_store.read(p,default)
def save(p,x):
 import durable_store
 durable_store.save(p,x)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()
def now():return datetime.datetime.now().astimezone().isoformat(timespec='seconds')
def event(root,kind,**kw):
 with (root/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(time=now(),event=kind,**kw),ensure_ascii=False)+'\n')
def run(args):return local_control.media(args)

def probe(p):return json.loads(run([FFPROBE,'-v','error','-count_frames','-show_streams','-show_format','-of','json',p]))
def next_segment(names,states):
 if any(s.get('status') in BLOCKED for s in states.values()):return None
 for n in names:
  if n not in states or retryable(states[n]):return n
  if states[n].get('status')!='ARCHIVED':return None
 return None

def check_graph(g):
 n=g.get('265',{})
 if n.get('class_type')!='MiniMaxH3ReferenceToVideo' or n.get('inputs',{}).get('ref_images.ref_image_0')!=['51',0]:raise ValueError('Exactly one image reference is required')
 if set(k for k in n['inputs'] if k.startswith('ref_images.') or k.startswith('ref_audio') or k.startswith('ref_video'))!={'ref_images.ref_image_0'}:raise ValueError('Unexpected reference inputs')
 if g['259']['inputs']['value']!=15 or g['252']['inputs']['megapixels']!=0.5 or abs(g['283']['inputs']['value']-1.5)>1e-9:raise ValueError('Locked generation parameters changed')

def last_frame(video,dest):
 info=probe(video); v=next(s for s in info['streams'] if s['codec_type']=='video'); count=int(v['nb_read_frames'])
 if count<1:raise ValueError('No decoded frames')
 dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_name(dest.stem+'.part.png')
 run([FFMPEG,'-v','error','-y','-i',video,'-map','0:v:0','-vf',f'select=eq(n\\,{count-1})','-fps_mode','passthrough','-frames:v','1',tmp])
 if not tmp.exists():raise ValueError('Last frame extraction produced no image')
 os.replace(tmp,dest)
 return {'source_sha256':sha(video),'frame_index_zero_based':count-1,'decoded_frame_count':count,'frame_sha256':sha(dest),'method':'full decode; select final presentation-order frame; no approximate seek'}

def archive_video(root,name):
 d=root/name;s=read(d/'task_state.json',{});task=s.get('taskId')
 if not task or s.get('status')!='ARCHIVED':raise ValueError('Predecessor not archived')
 manifest=d/'results'/('task-'+str(task))/'manifest.json';a=read(manifest,{})
 files=a.get('files',[])
 if len(files)!=1:raise ValueError('Expected exactly one output video; select manually if multiple')
 f=files[0];p=manifest.parent/f['name']
 if not p.resolve().is_relative_to(manifest.parent.resolve()) or not p.exists() or sha(p)!=f['sha256']:raise ValueError('Archive hash mismatch')
 return p,task

def bind(root,name,previous):
 dest=root/name/'assets/first_frame.png'
 if previous:
  source,task=archive_video(root,previous)
  lineage=last_frame(source,dest)
  lineage.update(source_batch=previous,source_task_id=task,source_video=source.relative_to(root).as_posix(),derived_for=name)
 else:
  source=root/'assets/speaker_reference.png'
  import shutil
  dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
  lineage={'source_image':'assets/speaker_reference.png','source_sha256':sha(source),'frame_sha256':sha(dest),'method':'byte-identical user image; full-reference opening target','derived_for':name}
 save(root/name/'lineage.json',lineage);event(root,'first_frame_bound',batch=name,sha256=lineage['frame_sha256'])
 return lineage

def verify_bound(root,name,previous,a):
 line=read(root/name/'lineage.json',{});dest=root/name/'assets/first_frame.png'
 if not dest.exists() or sha(dest)!=line.get('frame_sha256'):raise ValueError('Derived first frame changed')
 if previous:
  if a.get('derived_asset_policy')!='previous_approved_output_last_decoded_frame':raise ValueError('Derived asset policy not explicitly approved')
  source,task=archive_video(root,previous)
  if line.get('source_task_id')!=task or line.get('source_batch')!=previous or line.get('source_sha256')!=sha(source):raise ValueError('Derived provenance mismatch')
  # Reproduce the derivation and compare pixels encoded by the same deterministic tool.
  check=dest.with_name('verification.png');proof=last_frame(source,check)
  try:
   if proof['frame_sha256']!=line['frame_sha256']:raise ValueError('Frame is not the approved predecessor last frame')
  finally:check.unlink(missing_ok=True)
 else:
  if sha(dest)!=a['reference_sha256'] or sha(root/'assets/speaker_reference.png')!=a['reference_sha256'] or line.get('source_sha256')!=a['reference_sha256']:raise ValueError('Reference changed')

def concat(root,names,sources=None):
 out=root/'final';out.mkdir(exist_ok=True);inputs=[];streams=[];hashes=[]
 # Check existing verified final BEFORE ffprobe/full decode. Hashes still catch changed sources.
 source_paths=list(sources) if sources is not None else [archive_video(root,n)[0] for n in names]
 source_hashes=[sha(p) for p in source_paths]
 old=read(out/'manifest.json',{})
 if old.get('timing_verified') and old.get('source_sha256')==source_hashes and (out/'continuous_speaker.mp4').exists() and old.get('sha256')==sha(out/'continuous_speaker.mp4'):return old
 for p in source_paths:
  inputs+=['-i',p];i=probe(p)
  v=next(s for s in i['streams'] if s['codec_type']=='video');a=next((s for s in i['streams'] if s['codec_type']=='audio'),None)
  if a is None:raise ValueError('Missing generated audio')
  vd=float(v.get('duration',i['format']['duration']));ad=float(a.get('duration',i['format']['duration']))
  if abs(vd-ad)>0.1 or abs(float(v.get('start_time',0))-float(a.get('start_time',0)))>0.1:raise ValueError('Source audio/video duration or start mismatch')
  streams.append((v,vd));hashes.append(sha(p))
 if len({(v['width'],v['height'],v['r_frame_rate']) for v,_ in streams})!=1:raise ValueError('Segment geometries differ')
 old=read(out/'manifest.json',{})
 if old.get('source_sha256')==hashes and (out/'continuous_speaker.mp4').exists() and old.get('sha256')==sha(out/'continuous_speaker.mp4'):return old
 filters=[]
 for idx,(_,dur) in enumerate(streams):
  filters += [f'[{idx}:v]setpts=PTS-STARTPTS[v{idx}]',f'[{idx}:a]aresample=48000,apad,atrim=duration={dur},asetpts=PTS-STARTPTS[a{idx}]']
 filters.append(''.join(f'[v{i}][a{i}]' for i in range(len(names)))+f'concat=n={len(names)}:v=1:a=1[v][a]')
 temp=out/'continuous_speaker.part.mp4';save(root/'pipeline_state.json',{'state':'CONCATENATING','updatedAt':now()})
 run([FFMPEG,'-v','error','-y',*inputs,'-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',temp])
 info=probe(temp);v=next(s for s in info['streams'] if s['codec_type']=='video');a=next(s for s in info['streams'] if s['codec_type']=='audio');delta=abs(float(v['duration'])-float(a['duration']))
 if delta>0.1 or abs(float(v['duration'])-sum(d for _,d in streams))>0.1:raise ValueError('Final timing verification failed')
 run([FFMPEG,'-v','error','-i',temp,'-f','null','-'])
 dest=out/'continuous_speaker.mp4';os.replace(temp,dest)
 data={'state':'ASSEMBLED_PENDING_VISUAL_REVIEW','source_sha256':hashes,'sha256':sha(dest),'probe':info,'av_duration_delta_seconds':delta,'timing_verified':True,'lip_sync_verified':False,'note':'Original segments retained. Final re-encoded at original dimensions. Timing checks cannot prove phoneme/lip sync.','updatedAt':now()}
 save(out/'manifest.json',data);event(root,'concatenation_complete',status=data['state']);return data

def tick(root,validate,account_available,submit,collect,key):
 status={'state':'WAITING','updatedAt':now()}
 try:
  a=validate();names=read(root/'batches.json');secret=None
  if a.get('reference_strategy')=='fixed_first_frame':return tick_fixed(root,a,account_available,submit,collect,key)
  if [w for w in a['planned_waves']]!=[[n] for n in names]:raise ValueError('Serial approval waves required')
  if sha(root/'assets/speaker_reference.png')!=a.get('reference_sha256'):raise ValueError('Original reference changed')
  # Receive confirmed jobs even if the cloud preflight later expires. Never retry a failed generation.
  for n in names:
   local_control.checkpoint()
   d=root/n;s=read(d/'task_state.json',{})
   if not s.get('taskId') or s.get('status') in BLOCKED or s.get('status')=='ARCHIVED':continue
   if (datetime.datetime.now().astimezone()-datetime.datetime.fromisoformat(s['submittedAt'])).total_seconds()<480:continue
   try:
    secret=secret or key();result=collect(d,secret);s.update(result,lastCheckedAt=now());save(d/'task_state.json',s);event(root,'query_and_receive',batch=n,status=s['status'])
   except Exception as exc:
    s.update(status='RETRY_QUERY_OR_DOWNLOAD',lastCheckedAt=now(),reason=type(exc).__name__);save(d/'task_state.json',s);event(root,'receive_deferred',batch=n,errorType=type(exc).__name__)
  states={n:read(root/n/'task_state.json') for n in names if (root/n/'task_state.json').exists()}
  if all(states.get(n,{}).get('status')=='ARCHIVED' for n in names):
   status['state']='ASSEMBLED_PENDING_VISUAL_REVIEW' if (root/'final/continuous_speaker.mp4').exists() else 'AWAITING_SEGMENT_REVIEW'
  else:
   n=next_segment(names,states)
   if n:
    preflight=read(root/'workflow_preflight.json',{})
    if preflight.get('existing_workflow_schema_reused') is not True:status['state']='BLOCKED_WORKFLOW_PREFLIGHT'
    elif not account_available():status['state']='WAITING_ACCOUNT_SLOT'
    else:
     idx=names.index(n);previous=names[idx-1] if idx else None
     check_graph(read(root/n/'workflow_prepared.json'));bind(root,n,previous);verify_bound(root,n,previous,a)
     secret=secret or key();submit(root/n,secret,a['workflowId']);event(root,'submitted',batch=n)
   elif any(s.get('status') in BLOCKED for s in states.values()):status['state']='NEEDS_REVIEW'
 except local_control.LocalStop:
  status.update(state='LOCAL_STOPPED',updatedAt=now())
 except Exception as exc:
  status.update(state='NEEDS_REVIEW',errorType=type(exc).__name__,reason=str(exc)[:300]);event(root,'pipeline_stopped',errorType=type(exc).__name__)
 save(root/'tracker_status.json',status);save(root/'pipeline_state.json',status)

def render(root,entry,rows,status,events):
 e=lambda v:html.escape(str(v),quote=True)
 plan=read(root/'proposal.json',{});fixed=read(root/'approval.json',{}).get('reference_strategy')=='fixed_first_frame';final=root/'final/continuous_speaker.mp4'
 cards=[]
 for r in reversed(rows):
  n=r['name'];prompt=(root/n/'H3_prompt.txt').read_text(encoding='utf-8');m=read(root/n/'manifest.json')
  media=''.join('<video controls preload="metadata" src="'+e(v['path'])+'"></video>' for v in r['videos']) or '<p>尚未生成</p>'
  cards.append(f'<article><h2>{e(n)} · {e(r["state"])}</h2><p>{e(m["dialogue"])}</p><p>初始版本依赖：{e(m.get("depends_on") or "用户参考图")} · 任务 {e(r["taskId"] or "未提交")}</p>{media}<details><summary>H3 提示词</summary><pre>{e(prompt)}</pre></details><a href="{n}/workflow_prepared.json">工作流</a> · <a href="{n}/manifest.json">分段参数</a></article>')
 final_html='<video controls src="final/continuous_speaker.mp4"></video>' if final.exists() else '<p>最终合成：等待三段完成</p>'
 return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+e(entry['title'])+'</title><style>body{background:#111827;color:#eef2ff;font:16px/1.8 system-ui;max-width:1050px;margin:auto;padding:28px}a{color:#93c5fd}article,section{background:#1f2937;padding:22px;border-radius:14px;margin:20px 0}img{max-height:440px;max-width:100%}video{max-height:600px;width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}small{color:#cbd5e1}</style><a href="../../index.html">← 统一追踪中心</a><h1>'+e(entry['title'])+'</h1><p>'+e(status.get('state','待批准'))+' · 中文 · 3 × 15秒设定 · 9:16 · '+('固定首图 · 独立生成' if fixed else '尾帧接续 · 串行')+'</p><small>本对话 '+e(entry.get('conversation_id',''))+'</small><section><img src="assets/speaker_reference.png"><p>保留粉发、蓝金白服装、室内场景。'+('所有片段使用同一张已批准首图，不取前段尾帧。' if fixed else '首段使用原图；后段使用上段最后一个解码帧。')+'保留现有全参考节点，以提示词指定开场，不承诺硬首帧锁定。</p><p>'+e(plan.get('limitations',''))+'</p><p>0.5MP / 32对齐 / 1.5倍原放大器 / 24fps / 12步，8+4两阶段。参考音频、视频均关闭，生成音频VAE保留。362帧约15.083秒，三段约45.25秒，以实测为准。</p><a href="proposal.json">原始生成参数</a> · <a href="approval_proposal.json">原始审核哈希清单</a> · <a href="workflow_preflight.json">工作流能力核验</a> · <a href="README.md">接手说明</a></section><section><h2>最终合成</h2>'+final_html+'</section>'+''.join(cards)+'<section><h2>过程记录（倒序）</h2><pre>'+e('\n'.join(json.dumps(x,ensure_ascii=False) for x in reversed(events[-100:])))+'</pre></section></html>'


def tick_fixed(root,a,account_available,submit,collect,key):
 """Independent initial segments share one hash-locked reference; never use a predecessor."""
 names=read(root/'batches.json');status={'state':'WAITING','updatedAt':now()};secret=None
 try:
  if a.get('derived_asset_policy')!='same_approved_reference_every_segment':raise ValueError('Fixed reference policy required')
  if sum(a['planned_waves'],[])!=names:raise ValueError('Fixed segment order differs from approval')
  if sha(root/'assets/speaker_reference.png')!=a['reference_sha256']:raise ValueError('Master reference changed')
  for n in names:
   local_control.checkpoint();d=root/n;s=read(d/'task_state.json',{})
   if not s or retryable(s):
    states=[read(root/x/'task_state.json',{}) for x in names]
    if any(x.get('status') in ('UPLOADING','SUBMITTING_OUTCOME_UNKNOWN','REJECTED_OR_UNKNOWN') for x in states):continue
    if not account_available():continue
    if not read(root/'workflow_preflight.json',{}).get('existing_workflow_schema_reused'):raise ValueError('Workflow preflight required')
    check_graph(read(d/'workflow_prepared.json'))
    if sha(d/'assets/first_frame.png')!=a['reference_sha256']:raise ValueError('Segment reference differs from approved master')
    verify_bound(root,n,None,a);secret=secret or key();submit(d,secret,a['workflowId']);event(root,'submitted_fixed_reference',batch=n)
   elif s.get('taskId') and s.get('status') not in BLOCKED|{'ARCHIVED','CANCELLED'}:
    if (datetime.datetime.now().astimezone()-datetime.datetime.fromisoformat(s['submittedAt'])).total_seconds()<480:continue
    try:
     secret=secret or key();s.update(collect(d,secret),lastCheckedAt=now());save(d/'task_state.json',s)
    except local_control.LocalStop:raise
    except Exception as exc:event(root,'receive_deferred',batch=n,errorType=type(exc).__name__)
  states=[read(root/n/'task_state.json',{}) for n in names]
  if all(x.get('status')=='ARCHIVED' for x in states):
   status['state']='AWAITING_SEGMENT_REVIEW'
   job=read(root/'initial_assembly.json',{})
   if a.get('initial_assembly_authorized') is True and job.get('state') not in ('COMPLETE','FAILED'):
    save(root/'initial_assembly.json',{'state':'RUNNING','updatedAt':now(),'selection':[{'batch':n,'taskId':x['taskId']} for n,x in zip(names,states)]})
    try:
     result=concat(root,names)
     save(root/'initial_assembly.json',{'state':'COMPLETE','updatedAt':now(),'sha256':result['sha256'],'review':'PENDING_USER_REVIEW'})
    except local_control.LocalStop:raise
    except Exception as exc:
     save(root/'initial_assembly.json',{'state':'FAILED','updatedAt':now(),'reason':str(exc)[:300]});raise
   if (root/'final/continuous_speaker.mp4').exists():status['state']='ASSEMBLED_PENDING_VISUAL_REVIEW'
  elif all(x.get('status') in ('ARCHIVED','FAILED','CANCELLED') for x in states):status['state']='COMPLETE_WITH_FAILURES'
  elif any(x.get('status') in BLOCKED for x in states):status['state']='NEEDS_REVIEW'
  else:status['state']='GENERATING_FIXED_REFERENCE'
 except local_control.LocalStop:status['state']='LOCAL_STOPPED'
 except Exception as exc:status.update(state='NEEDS_REVIEW',reason=str(exc)[:300])
 save(root/'tracker_status.json',status);save(root/'pipeline_state.json',status)
