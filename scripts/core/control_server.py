import portable_runtime
import native_references
"""Loopback-only UI bridge. Mutations need token, exact origin, JSON and explicit UI confirmation."""
from pathlib import Path
import json,os,secrets,hashlib,shutil,re,subprocess,threading,msvcrt,mimetypes
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import unquote,urlsplit
import local_control as lc
ROOT=lc.ROOT;PORT=18765;ORIGIN=f'http://127.0.0.1:{PORT}';MUTEX=threading.Lock()
read=lc.read;save=lc.save

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def token():
 p=ROOT/'control_token.json';v=read(p,{})
 if not v: v={'token':secrets.token_urlsafe(32)};save(p,v)
 return v['token']
def project(root,pid):
 entry=next((x for x in read(root/'projects.json',{})['projects'] if x['id']==pid),None)
 if not entry:raise ValueError('Unknown project')
 path=(root/entry['path']).resolve()
 if not path.is_relative_to((root/'projects').resolve()):raise ValueError('Invalid project path')
 return entry,path

def batch_path(root,pid,batch):
 entry,p=project(root,pid)
 if batch not in read(p/'batches.json',[]):raise ValueError('Unknown segment')
 d=(p/batch).resolve()
 if d.parent!=p:raise ValueError('Invalid segment path')
 return entry,p,d

def create_reroll(root,pid,batch,request_id,confirmed,instance_type=None,preserve_seed=False,source_version=None,edit=None):
 if confirmed is not True:raise ValueError('Explicit paid generation confirmation required')
 if not re.fullmatch('[a-f0-9]{32}',request_id):raise ValueError('Invalid request id')
 if instance_type not in (None,'default','plus','ultra'):raise ValueError('Unsupported instanceType')
 entry,p,src=batch_path(root,pid,batch)
 if entry.get('source_project'):
  source_version=source_version or pid;pid=entry['source_project'];entry,p,src=batch_path(root,pid,batch)
 if source_version and source_version!=pid:
  source_entry,source_path,src=batch_path(root,source_version,batch)
  if source_entry.get('source_project')!=pid or source_entry.get('source_batch')!=batch:raise ValueError('Version is not part of this segment')
 new_id='reroll_'+request_id;reg=read(root/'projects.json')
 exists=next((x for x in reg['projects'] if x['id']==new_id),None)
 if exists:
  if exists.get('source_project')!=pid or exists.get('source_batch')!=batch:raise ValueError('Request id conflict')
  existing_meta=read(root/exists['path']/batch/'manifest.json',{})
  if existing_meta.get('edit_preview_id')!=(edit or {}).get('preview_id'):raise ValueError('Request id conflicts with edited content')
  if existing_meta.get('source_version',pid)!=(source_version or pid):raise ValueError('Request id conflicts with source version')
  if (instance_type is not None and existing_meta.get('instanceType')!=instance_type) or bool(existing_meta.get('preserve_seed'))!=preserve_seed:raise ValueError('Request id conflicts with selected retry mode')
  return {'project_id':new_id,'path':exists['path'],'duplicate':True}
 m=read(src/'manifest.json');old_approval=read(src.parent/'approval.json',{})
 if preserve_seed and read(src/'task_state.json',{}).get('status') not in ('FAILED','CANCELLED'):raise ValueError('Plus retry requires a confirmed ended failure')
 wid=old_approval.get('workflowId') or read(root/'workflow_routes.json',{}).get(pid)
 if not wid:raise ValueError('This historical project needs its workflow ID configured before reroll')
 videos=m.get('reference_videos',[]);video_nodes=m.get('video_node_ids',[])
 if len(videos)!=len(video_nodes) or len(set(video_nodes))!=len(video_nodes):raise ValueError('Video mapping incomplete')
 images=m['reference_images'];nodes=m['image_node_ids'];audios=m.get('reference_audio',[]);audio_nodes=m.get('audio_node_ids',[])
 if len(audios)!=len(audio_nodes):raise ValueError('音频参考与节点映射不完整')
 assets=images+audios+videos
 if len(images)!=len(nodes) or not images:raise ValueError('Reference mapping incomplete')
 graph=read(src/m['workflow'])
 for node in audio_nodes:
  if graph.get(node,{}).get('class_type')!='LoadAudio' or 'audio' not in graph[node].get('inputs',{}):raise ValueError('音频加载节点无效')
 for node in video_nodes:
  native_references.video_field(graph.get(node,{}))
 prompt=(src/m['prompt']).read_bytes()
 if edit:
  old=prompt.decode('utf-8-sig');matched=0
  for node in graph.values():
   for field,value in node.get('inputs',{}).items():
    if isinstance(value,str) and value.replace('\r\n','\n').strip()==old.replace('\r\n','\n').strip():node['inputs'][field]=edit['prompt'];matched+=1
  if matched!=1:raise ValueError('未找到唯一的工作流提示词节点，拒绝提交旧提示词')
  prompt=edit['prompt'].encode('utf-8');m['dialogue']=edit['dialogue'];m['hanzi_count']=edit['count'];m['edit_preview_id']=edit['preview_id'];m['edit_fields']=edit['fields']
 else:m.pop('edit_preview_id',None)
 sources=[]
 for rel in assets:
  f=(src/rel).resolve()
  if not f.is_relative_to(src) or not f.is_file():raise ValueError('Reference asset missing or outside segment')
  sources.append((rel,f,sha(f)))
 lineage=read(src/'lineage.json',{})
 if lineage and (len(images)!=1 or sources[0][2]!=lineage.get('frame_sha256')):raise ValueError('Digital-speaker reference hash differs from bound frame')
 seed=secrets.randbelow(2**50);changed=False
 for n in graph.values():
  if n.get('class_type')=='RandomNoise':
   if preserve_seed:seed=n['inputs']['noise_seed']
   else:
    while seed==n['inputs'].get('noise_seed'):seed=secrets.randbelow(2**50)
   n['inputs']['noise_seed']=seed;changed=True
 if not changed:raise ValueError('No known random seed node; refuse indistinguishable reroll')
 dest=p/'versions'/new_id
 if dest.exists():raise ValueError('Partial request exists; inspect locally before retrying')
 d=dest/batch;d.mkdir(parents=True)
 for rel,f,digest in sources:
  target=d/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,target)
  if sha(target)!=digest:raise ValueError('Asset copy verification failed')
 for node in nodes:graph[node]['inputs']['image']='__APPROVED_REROLL_REFERENCE__'
 for node in audio_nodes:graph[node]['inputs']['audio']='__APPROVED_REROLL_AUDIO__'
 for node in video_nodes:graph[node]['inputs'][native_references.video_field(graph[node])]='__APPROVED_REROLL_VIDEO__'
 for n in graph.values():
  if n.get('class_type')=='VHS_VideoCombine':n['inputs']['filename_prefix']=new_id
 (d/'H3_prompt.txt').write_bytes(prompt);save(d/'workflow_prepared.json',graph)
 m.update(batch=1,name=batch,prompt='H3_prompt.txt',workflow='workflow_prepared.json',status='APPROVED',depends_on=None,reroll_source={'project':pid,'batch':batch,'seed':seed})
 if instance_type is not None:m['instanceType']=instance_type
 m['preserve_seed']=preserve_seed;m['source_version']=source_version or pid
 save(d/'manifest.json',m);save(dest/'batches.json',[batch])
 files=['H3_prompt.txt','workflow_prepared.json','manifest.json']+assets
 save(dest/'approval.json',{'status':'APPROVED','upload_permitted':True,'submit_permitted':True,'workflowId':wid,'approvedAt':lc.now(),'approval_source':'Explicit paid-generation confirmation from local UI','request_id':request_id,'approved_batches':[{'name':batch,'hashes':{f:sha(d/f) for f in files}}],'planned_waves':[[batch]],'excluded_batches':[],'max_concurrent':1,'scope':'One in-project segment version only; original media and downstream chain remain intact; no retries'})
 save(dest/'tracker_status.json',{'state':'APPROVED_WAITING_SCRIPT','updatedAt':lc.now()})
 save(dest/'reroll_source.json',{'source_project':pid,'source_batch':batch,'source_prompt_sha256':hashlib.sha256(prompt).hexdigest(),'assets':[{'path':rel,'sha256':h} for rel,_,h in sources],'source_lineage':lineage,'seed':seed})
 (dest/'events.jsonl').write_text(json.dumps({'time':lc.now(),'event':'user_confirmed_reroll','batch':batch,'status':'APPROVED'},ensure_ascii=False)+'\n',encoding='utf-8')
 new={'id':new_id,'title':entry['title']+' · '+batch+(' · Plus重跑 ' if preserve_seed else ' · 重抽 ')+lc.now()[11:19],'path':dest.relative_to(root).as_posix(),'kind':'segment_version','mode':'queue','conversation':entry.get('conversation',''),'conversation_id':entry.get('conversation_id',''),'updatedAt':lc.now(),'source_project':pid,'source_batch':batch}
 reg['projects'].append(new);save(root/'projects.json',reg)
 return {'project_id':new_id,'path':new['path'],'seed':seed,'duplicate':False}

def output_folder(root,pid,batch):
 if batch=='__final__':
  _,p=project(root,pid);dest=p/'final'
  if not (dest/'continuous_speaker.mp4').exists():raise ValueError('Final output not available')
  return dest
 _,p,d=batch_path(root,pid,batch);s=read(d/'task_state.json',{})
 target=(d/'results'/('task-'+str(s.get('taskId','')))).resolve()
 if not target.is_relative_to(d) or not (target/'manifest.json').exists():raise ValueError('No archived output folder yet')
 return target

def static_path(root,url):
 rel=unquote(urlsplit(url).path).lstrip('/') or 'index.html';p=(root/rel).resolve()
 if not p.is_relative_to(root.resolve()) or '..' in Path(rel).parts:raise ValueError('Invalid path')
 if rel not in ('index.html','使用指引.html','ui_controls.js'):
  if not rel.startswith('projects/'):raise ValueError('Private path')
  if p.suffix.lower() not in ('.html','.png','.jpg','.jpeg','.webp','.mp4','.mov','.webm','.mp3','.wav','.flac','.ogg','.m4a') and p.name not in ('H3_prompt.txt','manifest.json','workflow_prepared.json','task_state.json','proposal.json','approval_proposal.json','workflow_preflight.json','README.md','segmentation_preflight.json'):raise ValueError('Private file')
 return p

def launch(action='tick'):
 subprocess.Popen([portable_runtime.tool('pythonw'),str(portable_runtime.APP/'scripts/hub.py'),action],cwd=ROOT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def valid_origin(self):return self.headers.get('Origin') in (None,'null',ORIGIN)
 def send_common(self,status=200,kind='application/json; charset=utf-8',length=None):
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
  if self.valid_origin():self.send_header('Access-Control-Allow-Origin',self.headers.get('Origin') or ORIGIN)
  self.send_header('Access-Control-Allow-Methods','POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Content-Type, X-Hub-Token');self.send_header('Access-Control-Allow-Private-Network','true')
  if length is not None:self.send_header('Content-Length',str(length))
 def respond(self,status,obj):
  data=json.dumps(obj,ensure_ascii=False).encode();self.send_common(status,length=len(data));self.end_headers();self.wfile.write(data)
 def host_ok(self):return self.headers.get('Host')==f'127.0.0.1:{PORT}'
 def do_OPTIONS(self):
  if not self.host_ok() or not self.valid_origin():return self.respond(403,{'error':'Origin rejected'})
  self.send_common(204);self.end_headers()
 def do_POST(self):
  if getattr(self.server,'read_only',False):return self.respond(403,{'error':'Read-only preview; actions are disabled'})
  import durable_store
  with durable_store.configured_session(ROOT):self._do_POST()
 def _do_POST(self):
  if not self.host_ok() or not self.valid_origin() or not secrets.compare_digest(self.headers.get('X-Hub-Token',''),token()) or self.headers.get('Content-Type')!='application/json':return self.respond(403,{'error':'Unauthorized local control request'})
  try:
   size=int(self.headers.get('Content-Length','0'))
   if not 0<size<160000:raise ValueError('Invalid body size')
   data=json.loads(self.rfile.read(size));action=data.get('action')
   if self.path!='/api/control':raise ValueError('Unknown endpoint')
   if action in ('edit_load','edit_save','edit_preview'):
    import segment_editor as editor
    with MUTEX:
     if action=='edit_load':result=editor.load(ROOT,data['project'],data['batch'],data.get('source_version'))
     else:result=editor.prepare(ROOT,data['project'],data['batch'],data.get('source_version'),data['fields'],data['fingerprint'],preview=action=='edit_preview')
    return self.respond(200,result)
   if action=='status':return self.respond(200,lc.status())
   if action=='queue_status':
    snapshot=read(ROOT/'queue_state.json',{'jobs':[],'limit':3})
    for job in snapshot['jobs']:
     folder=(ROOT/job['path']).resolve()
     if not folder.is_relative_to((ROOT/'projects').resolve()):raise ValueError('Invalid queue path')
     state=read(folder/'task_state.json',{})
     if state:job.update(status=state.get('status',job['status']),reason=state.get('reason',''),taskId=state.get('taskId'),lastCheckedAt=state.get('lastCheckedAt'))
    return self.respond(200,snapshot)
   if action in ('fetch_results','fetch_results_status'):
    entry,folder=project(ROOT,data['project']);status_file=folder/'manual_fetch_status.json'
    if action=='fetch_results_status':return self.respond(200,read(status_file,{'state':'IDLE'}))
    with MUTEX:
     state=read(status_file,{})
     if state.get('state') in ('QUEUED','RUNNING') and lc.alive(state.get('pid')):return self.respond(200,state)
     save(status_file,{'state':'QUEUED','updatedAt':lc.now()})
     proc=subprocess.Popen([portable_runtime.tool('pythonw'),str(portable_runtime.APP/'scripts/hub.py'),'fetch-results','--project',entry['id']],cwd=ROOT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
     state=read(status_file,{})
     state['pid']=proc.pid;save(status_file,state)
    return self.respond(200,state)
   if action in ('versions','choose_version','reject_version','approve_final','order','assemble'):
    import speaker_versions as versions
    with MUTEX:
     if action=='versions':result=versions.view(ROOT,data['project'])
     elif action=='choose_version':result=versions.choose(ROOT,data['project'],data['batch'],data['version'],data.get('confirmed'))
     elif action=='reject_version':result=versions.reject(ROOT,data['project'],data['batch'],data['version'],data.get('confirmed'))
     elif action=='approve_final':result=versions.approve_final(ROOT,data['project'],data['assembly'],data.get('confirmed'))
     elif action=='order':result=versions.reorder(ROOT,data['project'],data['order'])
     else:result=versions.enqueue(ROOT,data['project'],data['request_id'],data.get('confirmed'),data.get('expected'))
    if action=='assemble' and not result.get('unchanged') and not result.get('duplicate'):launch()
    return self.respond(200,result)
   if action=='stop':return self.respond(200,lc.set_paused(True))
   if action=='resume':
    result=lc.set_paused(False);launch();return self.respond(200,result)
   if action=='assembly_folder':
    import speaker_versions as versions
    state=versions.view(ROOT,data['project']);a=next((x for x in state['assemblies'] if x['id']==data['assembly'] and x['video']),None)
    if not a:raise ValueError('Assembly not available')
    dest=(ROOT/a['video']).parent;os.startfile(str(dest));return self.respond(200,{'opened':str(dest)})
   if action=='folder':
    dest=output_folder(ROOT,data['project'],data['batch']);os.startfile(str(dest));return self.respond(200,{'opened':str(dest)})
   if action in ('reroll','retry_plus','edit_generate'):
    with MUTEX,(ROOT/'hub.process.lock').open('a+b') as lock:
     lock.seek(0)
     try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
     except OSError:return self.respond(409,{'error':'中心脚本正在更新，请稍后再点；尚未创建任务。'})
     try:
      edit=None
      if action=='edit_generate':
       import segment_editor as editor
       edit=editor.snapshot(ROOT,data['project'],data['batch'],data.get('preview_id'))
       data['source_version']=edit['source_version']
      result=create_reroll(ROOT,data['project'],data['batch'],data['request_id'],data.get('confirmed'),instance_type='plus' if action=='retry_plus' else None,preserve_seed=action=='retry_plus',source_version=data.get('source_version'),edit=edit)
     finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
    launch();return self.respond(200,result)
   raise ValueError('Unknown action')
  except (ValueError,KeyError,FileNotFoundError) as exc:self.respond(400,{'error':str(exc)})
  except Exception as exc:self.respond(500,{'error':type(exc).__name__+'; no automatic generation retry'})
 def do_GET(self):
  if not self.host_ok():return self.respond(403,{'error':'Invalid host'})
  try:
   if urlsplit(self.path).path in ('/supervision.html','/api/supervision'):
    import supervision
    observed=supervision.snapshot(ROOT)
    if urlsplit(self.path).path=='/api/supervision':return self.respond(200,observed)
    payload=supervision.render_panel(observed).encode('utf-8')
    self.send_common(200,'text/html; charset=utf-8',len(payload));self.end_headers();self.wfile.write(payload);return
   p=static_path(ROOT,self.path)
   if not p.is_file():return self.respond(404,{'error':'File not found'})
   size=p.stat().st_size;start=0;end=size-1;code=200
   requested=self.headers.get('Range')
   if requested:
    match=re.fullmatch(r'bytes=(\d+)-(\d*)',requested)
    if not match:return self.respond(416,{'error':'Unsupported range'})
    start=int(match[1]);end=min(int(match[2]) if match[2] else end,end);code=206
    if start>end:return self.respond(416,{'error':'Range outside file'})
   kind=mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
   if p.suffix in ('.html','.txt','.js','.md'):kind+='; charset=utf-8'
   self.send_common(code,kind,end-start+1);self.send_header('Accept-Ranges','bytes')
   if code==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
   self.end_headers()
   with p.open('rb') as f:
    f.seek(start);left=end-start+1
    while left:
     chunk=f.read(min(left,1024*1024))
     if not chunk:break
     self.wfile.write(chunk);left-=len(chunk)
  except (ValueError,OSError):
   try:self.respond(404,{'error':'Unavailable'})
   except OSError:pass

class ExclusiveServer(ThreadingHTTPServer):
 allow_reuse_address=False
 def server_bind(self):
  import socket
  if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
  super().server_bind()

def collection_loop(stopped):
 """Receive existing task IDs only; never tick/resume the paid queue."""
 while not stopped.is_set():
  try:launch('collect-results')
  except OSError:
   save(ROOT/'collection_service_status.json',{'state':'ERROR','error':'LaunchError','updatedAt':lc.now()})
  if stopped.wait(120):return

def serve(read_only=False):
 if not read_only:token()
 try:server=ExclusiveServer(('127.0.0.1',PORT),Handler)
 except OSError:return
 server.read_only=read_only
 stopped=threading.Event()
 save(ROOT/'control_service_status.json',{'pid':os.getpid(),'listen':ORIGIN,'startedAt':lc.now(),'collectionOnly':not read_only,'readOnly':read_only,'collectionIntervalSeconds':None if read_only else 120})
 if not read_only:threading.Thread(target=collection_loop,args=(stopped,),daemon=True).start()
 try:server.serve_forever()
 finally:stopped.set();server.server_close()
