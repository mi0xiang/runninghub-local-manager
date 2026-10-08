"""Installation CLI; init/doctor/confirm never send requests to RunningHub."""
import argparse,datetime,html,json,os,shutil,socket,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'scripts/core'))
import portable_runtime as rt

def doctor():
 cfg=rt.load();checks=[]
 def add(name,ok,detail,required=True):checks.append(dict(name=name,ok=bool(ok),detail=detail,required=required))
 add('Windows Python ≥3.10',os.name=='nt' and sys.version_info>=(3,10),sys.executable)
 add('初始化配置',bool(cfg),'运行 manage.py init 指定本机数据目录')
 try:
  rt.validate_data_dir(rt.ROOT)
  with tempfile.TemporaryFile(dir=rt.ROOT):pass
  data=json.loads((rt.ROOT/'projects.json').read_text(encoding='utf-8-sig'))
  add('本机数据目录',isinstance(data.get('projects'),list),str(rt.ROOT))
 except (OSError,ValueError):add('本机数据目录',False,str(rt.ROOT))
 for tool in ('ffmpeg','ffprobe'):
  try:ok=subprocess.run([rt.tool(tool),'-version'],capture_output=True,timeout=10).returncode==0
  except (OSError,subprocess.TimeoutExpired):ok=False
  add(tool,ok,rt.tool(tool)+'；未安装时只能浏览，下载校验/合成不可用',False)
 try:
  from runninghub_transport import key
  available=bool(key())
 except (OSError,RuntimeError):available=False
 add('RUNNINGHUB_API_KEY',available,'仅检查存在；不会显示或验证密钥。缺失时可浏览，不能对接 API',False)
 with socket.socket() as sock:
  try:sock.bind(('127.0.0.1',18765));available=True
  except OSError:available=False
 add('本地端口 18765',available,'占用时核实已有服务，不自动关闭其他进程',False)
 passed=all(x['ok'] for x in checks if x['required'])
 report={'passed':passed,'time':datetime.datetime.now().astimezone().isoformat(),'checks':checks}
 rt.ROOT.mkdir(parents=True,exist_ok=True)
 (rt.ROOT/'environment_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 rows=''.join('<tr><td>'+html.escape(x['name'])+'</td><td>'+('通过' if x['ok'] else '待处理' if x['required'] else '功能受限')+'</td><td>'+html.escape(x['detail'])+'</td></tr>' for x in checks)
 (rt.ROOT/'环境检查.html').write_text('<!doctype html><meta charset="utf-8"><title>本机环境检查</title><style>body{font:16px/1.8 system-ui;max-width:1000px;margin:40px auto}td{padding:12px;border-bottom:1px solid #bbb}</style><h1>本机环境检查</h1><table>'+rows+'</table><p>此检查不联网，不验证余额和 API 权限，不批准任何生成任务。</p>',encoding='utf-8')
 for item in checks:print(('OK' if item['ok'] else 'FAIL' if item['required'] else 'WARN')+' '+item['name'])
 print('Report:',rt.ROOT/'环境检查.html');return passed

def main():
 parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
 init=sub.add_parser('init');init.add_argument('--data-dir',required=True);init.add_argument('--ffmpeg',default='ffmpeg');init.add_argument('--ffprobe',default='ffprobe')
 for name in ('doctor','confirm','web','render','tick','status'):sub.add_parser(name)
 panel=sub.add_parser('panel');panel.add_argument('--output')
 dashboard=sub.add_parser('dashboard')
 handoff=sub.add_parser('handoff');handoff.add_argument('--project',required=True);handoff.add_argument('--record',required=True);handoff.add_argument('--expected-revision',type=int,required=True);handoff.add_argument('--writer');handoff.add_argument('--epoch',type=int)
 plan=sub.add_parser('postproduction-plan');plan.add_argument('--project',required=True);plan.add_argument('--record',required=True);plan.add_argument('--expected-revision',type=int,required=True)
 delivery=sub.add_parser('delivery-record');delivery.add_argument('--project',required=True);delivery.add_argument('--record',required=True);delivery.add_argument('--expected-revision',type=int,required=True)
 lark=sub.add_parser('lark-diff');lark.add_argument('--snapshot',required=True)
 receipt=sub.add_parser('lark-receipt');receipt.add_argument('--request',required=True);receipt.add_argument('--receipt',required=True)
 register=sub.add_parser('register-ready');register.add_argument('--record',required=True)
 audit=sub.add_parser('audit-archives');audit.add_argument('--project',required=True)
 execution=sub.add_parser('execution-plan');execution.add_argument('--project',required=True);execution.add_argument('--record',required=True);execution.add_argument('--expected-revision',type=int,required=True)
 review=sub.add_parser('segment-review');review.add_argument('--project',required=True);review.add_argument('--record',required=True);review.add_argument('--expected-revision',type=int,required=True)
 watch=sub.add_parser('watch-results');watch.add_argument('--selection',required=True);watch.add_argument('--once',action='store_true');watch.add_argument('--resume-errors',action='store_true')
 inspect=sub.add_parser('project-status');inspect.add_argument('--project',required=True)
 assembly=sub.add_parser('assemble-project');assembly.add_argument('--project',required=True);assembly.add_argument('--owner',required=True)
 binding=sub.add_parser('delivery-register');binding.add_argument('--project',required=True);binding.add_argument('--owner',required=True);binding.add_argument('--expected-revision',type=int,required=True)
 args=parser.parse_args()
 if args.action=='init':
  if rt.CONFIG.exists():raise SystemExit('Configuration exists. Edit .local/config.json deliberately, then doctor and confirm again. Data will not be erased.')
  root=rt.validate_data_dir(args.data_dir);rt.initialize(root)
  rt.save_config({'data_dir':str(root),'python':sys.executable,'ffmpeg':args.ffmpeg,'ffprobe':args.ffprobe,'schema_version':1})
  print('Initialized empty local center:',root);return
 if args.action=='doctor':raise SystemExit(0 if doctor() else 1)
 if args.action=='confirm':
  if not doctor():raise SystemExit('Resolve required checks first.')
  if input('确认目录正确且没有另一台机器运行同一数据队列。输入 CONFIRM（不提交任务）: ')!='CONFIRM':raise SystemExit('Not confirmed')
  rt.save_config(rt.bind(rt.load()));print('Confirmed; no background task started.');return
 rt.require_ready()
 if args.action in ('execution-plan','segment-review','watch-results','project-status','assemble-project','delivery-register'):
  import durable_store,project_runner
  with durable_store.configured_session(rt.ROOT):
   if args.action=='watch-results':
    selected=json.loads(Path(args.selection).read_text(encoding='utf-8-sig'))
    def progress(value):
     print(json.dumps({'run_id':value['run_id'],'state':value['state'],'updated_at':value['updated_at'],
                       'jobs':[{k:j.get(k) for k in ('project_id','ownerThreadId','taskId','status','errors','error')} for j in value['jobs']],
                       'paid_calls':0,'agent_invoked':False},ensure_ascii=False),flush=True)
    result=project_runner.run(rt.ROOT,selected,once=args.once,on_progress=progress,resume_errors=args.resume_errors)
   elif args.action=='project-status':result=project_runner.project_status(rt.ROOT,args.project)
   elif args.action in ('execution-plan','segment-review'):
    record=json.loads(Path(args.record).read_text(encoding='utf-8-sig'))
    result=(project_runner.register_plan if args.action=='execution-plan' else project_runner.record_segment_review)(rt.ROOT,args.project,record,args.expected_revision)
   elif args.action=='delivery-register':result=project_runner.register_delivery(rt.ROOT,args.project,args.owner,args.expected_revision)
   else:
    entry,folder=project_runner.project(rt.ROOT,args.project);project_runner.check_owner(entry,folder,args.owner)
    import postproduction_executor
    result=postproduction_executor.assemble(folder)
   if args.action!='watch-results':print(json.dumps(result,ensure_ascii=False,indent=2))
   return
 if args.action in ('panel','dashboard','handoff','postproduction-plan','delivery-record','lark-diff','lark-receipt','register-ready','audit-archives'):
  import durable_store,supervision,contextlib
  session=durable_store.session(rt.ROOT,args.writer,args.epoch) if args.action=='handoff' and args.writer else durable_store.configured_session(rt.ROOT)
  with session:
   if args.action=='panel':
    observed=supervision.snapshot(rt.ROOT);page=supervision.render_panel(observed)
    output=Path(args.output) if args.output else rt.ROOT/'supervision.html'
    if not output.resolve().is_relative_to(rt.ROOT):raise SystemExit('Panel output must stay inside configured data root')
    output.write_text(page,encoding='utf-8');supervision.persist_observation(rt.ROOT,observed);print('Local read-only panel:',output);return
   if args.action=='dashboard':
    import control_server
    print('Read-only preview: http://127.0.0.1:18765/supervision.html ; no collection or paid actions.')
    control_server.serve(read_only=True);return
   if args.action=='lark-diff':
    snapshot_path=Path(args.snapshot).resolve();snapshot_bytes=snapshot_path.read_bytes()
    snapshot=json.loads(snapshot_bytes.decode('utf-8-sig'));snapshot['_path']=str(snapshot_path);snapshot['_file_sha256']=__import__('hashlib').sha256(snapshot_bytes).hexdigest()
    result=supervision.generate_lark_requests(rt.ROOT,snapshot)
   elif args.action=='lark-receipt':
    import lark_diff
    request_path=Path(args.request).resolve();request_bytes=request_path.read_bytes()
    request=json.loads(request_bytes.decode('utf-8-sig'));returned=json.loads(Path(args.receipt).read_text(encoding='utf-8-sig'))
    lark_diff.request_id(request.get('request_id'))
    local_path=rt.ROOT/'coordination/lark-outbox'/f'{request["request_id"]}.json'
    if request_path!=local_path.resolve():raise ValueError('Receipt must bind the original local outbox request')
    result=lark_diff.check_receipt(request,returned,request_sha256=__import__('hashlib').sha256(request_bytes).hexdigest())
    durable_store.save(rt.ROOT/'coordination/lark-receipts'/f'{request["request_id"]}.json',dict(returned,validated=result))
   elif args.action=='register-ready':
    result=supervision.register_ready_project(rt.ROOT,json.loads(Path(args.record).read_text(encoding='utf-8-sig')))
   else:
    entry=next(x for x in durable_store.read(rt.ROOT/'projects.json')['projects'] if x['id']==args.project)
    folder=supervision.project_folder(rt.ROOT,entry)
    if args.action=='audit-archives':
     import archive_integrity
     result=[]
     for name in durable_store.read(folder/'batches.json',[]):
      state=durable_store.read(folder/name/'task_state.json',{})
      if state.get('taskId'):result.append(archive_integrity.verify_archive(folder/name,state['taskId']))
    else:
     record=json.loads(Path(args.record).read_text(encoding='utf-8-sig'))
     if args.action=='handoff':result=supervision.record_handoff(rt.ROOT,entry,record,args.expected_revision)
     else:
      import postproduction_records
      result=(postproduction_records.register_plan if args.action=='postproduction-plan' else postproduction_records.register_delivery)(folder,record,args.expected_revision)
   print(json.dumps(result,ensure_ascii=False,indent=2));return
 hub=rt.APP/'scripts/hub.py'
 if args.action=='web':
  subprocess.run([sys.executable,str(hub),'render'],check=True)
  print('Open http://127.0.0.1:18765/index.html ; Ctrl+C stops this web server.')
  subprocess.run([sys.executable,str(hub),'serve'],check=True)
 else:subprocess.run([sys.executable,str(hub),args.action],check=True)
if __name__=='__main__':main()
