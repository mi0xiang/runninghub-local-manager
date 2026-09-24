import portable_runtime
"""Opt-in original-audio remux, called only by the central hub download entry."""
from pathlib import Path
import json, hashlib, subprocess, os, datetime
FF=portable_runtime.tool('ffmpeg')
FP=portable_runtime.tool('ffprobe')
def read(p,default=None):return json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else default
def save(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.json.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,p)
def command(args):return subprocess.check_output(args,stderr=subprocess.PIPE,creationflags=0x08000000)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def audio_hash(p):return command([FF,'-v','error','-i',str(p),'-map','0:a:0','-c:a','copy','-f','hash','-hash','sha256','-']).decode().strip()
def process(folder):
 folder=Path(folder).resolve();cfg=read(folder/'manifest.json',{}).get('restore_source_audio')
 if not cfg:return 'DISABLED'
 state=read(folder/'task_state.json',{});task=str(state.get('taskId',''))
 if state.get('status')!='ARCHIVED' or not task:return 'WAITING'
 archive=folder/'results'/('task-'+task);raw=read(archive/'manifest.json',{})
 if not raw.get('files'):return 'WAITING'
 source=(folder/cfg['source']).resolve();video=(archive/raw['files'][0]['name']).resolve()
 if not source.is_relative_to(folder) or not video.is_relative_to(folder):raise ValueError('Media path escapes batch')
 duration=float(cfg['duration']);target=folder/'results'/('source-audio-'+task);dest=target/'final_original_audio.mp4'
 fingerprint={'video':digest(video),'audio':digest(source),'duration':duration}
 prior=read(target/'manifest.json',{})
 if prior.get('sourceFingerprint')==fingerprint and dest.exists() and prior.get('files',[{}])[0].get('sha256')==digest(dest):return 'COMPLETE'
 target.mkdir(parents=True,exist_ok=True);temp=target/'final_original_audio.part.mp4'
 command([FF,'-v','error','-y','-i',str(video),'-i',str(source),'-map','0:v:0','-map','1:a:0','-c','copy','-t',str(duration),'-movflags','+faststart',str(temp)])
 probe=json.loads(command([FP,'-v','error','-show_streams','-show_format','-of','json',str(temp)]))
 if not any(s.get('codec_type')=='audio' for s in probe['streams']):raise ValueError('No original audio in remux')
 if abs(float(probe['format']['duration'])-duration)>0.15:raise ValueError('Unexpected output duration')
 # Source was cut to delivery length before submission; copy must preserve its packets.
 if audio_hash(temp)!=audio_hash(source):raise ValueError('Original audio packets changed or truncated')
 os.replace(temp,dest);now=datetime.datetime.now().astimezone().isoformat(timespec='seconds')
 save(target/'manifest.json',{'taskId':task,'receivedAt':now,'sourceFingerprint':fingerprint,'note':'Original source audio restored; video and AAC packets copied without re-encoding. Raw cloud output retained. Awaiting visual review.','files':[{'name':dest.name,'bytes':dest.stat().st_size,'sha256':digest(dest),'probe':probe}]})
 save(folder/'audio_delivery_status.json',{'status':'COMPLETE','updatedAt':now,'file':str(dest.relative_to(folder))})
 return 'COMPLETE'
def process_all(root):
 root=Path(root)
 for entry in read(root/'projects.json',{}).get('projects',[]):
  p=(root/entry['path']).resolve()
  if not p.is_relative_to((root/'projects').resolve()):continue
  for name in read(p/'batches.json',[]):
   d=(p/name).resolve()
   if d.parent!=p:continue
   try:process(d)
   except Exception as exc:save(d/'audio_delivery_status.json',{'status':'ERROR','reason':type(exc).__name__+': '+str(exc)[:200]})
