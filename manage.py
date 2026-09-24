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
 hub=rt.APP/'scripts/hub.py'
 if args.action=='web':
  subprocess.run([sys.executable,str(hub),'render'],check=True)
  print('Open http://127.0.0.1:18765/index.html ; Ctrl+C stops this web server.')
  subprocess.run([sys.executable,str(hub),'serve'],check=True)
 else:subprocess.run([sys.executable,str(hub),args.action],check=True)
if __name__=='__main__':main()
