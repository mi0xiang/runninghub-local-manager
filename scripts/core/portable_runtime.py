"""Code belongs to Git; data and credentials belong to this machine."""
import hashlib,json,os,platform,sys
from pathlib import Path
APP=Path(__file__).resolve().parents[2]
CONFIG=Path(os.environ.get('RUNNINGHUB_CONFIG_FILE',str(APP/'.local/config.json')))
def load():
 return json.loads(CONFIG.read_text(encoding='utf-8-sig')) if CONFIG.exists() else {}
def validate_data_dir(path):
 path=Path(path).expanduser().resolve()
 if path==APP or path.is_relative_to(APP):raise ValueError('Data must be outside the code repository.')
 return path
ROOT=validate_data_dir(load().get('data_dir',APP.parent/'runninghub-local-data'))
def machine():
 try:
  import winreg
  with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Cryptography',0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:return winreg.QueryValueEx(key,'MachineGuid')[0]
 except (ImportError,OSError):return platform.node()
def digest(cfg):return hashlib.sha256(json.dumps({k:v for k,v in cfg.items() if not k.startswith('confirmed_')},sort_keys=True).encode()).hexdigest()
def bind(cfg):return dict(cfg,confirmed_machine=machine(),confirmed_digest=digest(cfg),confirmed_app=str(APP))
def is_confirmed(cfg):return cfg.get('confirmed_machine')==machine() and cfg.get('confirmed_digest')==digest(cfg) and cfg.get('confirmed_app')==str(APP)
def require_ready():
 if not is_confirmed(load()):raise RuntimeError('Run manage.py init, doctor, then confirm before starting this installation.')
def save_config(cfg):
 CONFIG.parent.mkdir(parents=True,exist_ok=True);temp=CONFIG.with_suffix('.tmp');temp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,CONFIG)
def tool(name):
 if name=='pythonw':
  candidate=Path(sys.executable).with_name('pythonw.exe');return str(candidate) if candidate.exists() else sys.executable
 if name=='python':return sys.executable
 return load().get(name) or name
def initialize(root):
 root=validate_data_dir(root);root.mkdir(parents=True,exist_ok=True)
 for folder in ('projects','workflow_baselines','reports'): (root/folder).mkdir(exist_ok=True)
 for filename,value in {'projects.json':{'schema_version':1,'projects':[]},'workflow_routes.json':{}}.items():
  path=root/filename
  if not path.exists():path.write_text(json.dumps(value,indent=2),encoding='utf-8')
