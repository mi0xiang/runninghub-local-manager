import portable_runtime
"""Local execution state and cooperative stop; no cloud cancellation claims."""
from pathlib import Path
import os,json,datetime,subprocess,time,threading,uuid
ROOT=portable_runtime.ROOT
ENABLED=False
class LocalStop(RuntimeError):pass
def read(p,default=None):
 import durable_store
 return durable_store.read(p,default)

def save(p,x):
 import durable_store
 durable_store.save(p,x)
def now():return datetime.datetime.now().astimezone().isoformat(timespec='seconds')
def paused():return read(ROOT/'local_control.json',{}).get('paused',False)
def checkpoint():
 if ENABLED and paused():raise LocalStop('Local processing stopped by user; cloud task is not cancelled')
def phase(name,**kw):
 if ENABLED:save(ROOT/'runtime_status.json',dict(pid=os.getpid(),phase=name,updatedAt=now(),**kw))
def media(args,timeout=900):
 checkpoint();phase('MEDIA_PROCESS',tool=Path(str(args[0])).name)
 with subprocess.Popen([str(a) for a in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as proc:
  start=time.monotonic()
  while True:
   try:
    out,err=proc.communicate(timeout=0.3);break
   except subprocess.TimeoutExpired:
    if (ENABLED and paused()) or time.monotonic()-start>timeout:
     proc.kill();proc.communicate()
     if ENABLED and paused():raise LocalStop('Stopped local media processing')
     raise TimeoutError('Local media processing timeout')
  if proc.returncode:raise subprocess.CalledProcessError(proc.returncode,args,output=out,stderr=err)
 checkpoint();phase('PROCESSING');return out

def alive(pid):
 if not pid:return False
 if os.name!='nt':
  try:os.kill(int(pid),0);return True
  except OSError:return False
 import ctypes
 k=ctypes.windll.kernel32;k.OpenProcess.restype=ctypes.c_void_p
 handle=k.OpenProcess(0x1000,False,int(pid))
 if not handle:return False
 try:
  code=ctypes.c_ulong();return bool(k.GetExitCodeProcess(ctypes.c_void_p(handle),ctypes.byref(code))) and code.value==259
 finally:k.CloseHandle(ctypes.c_void_p(handle))

def status():
 s=read(ROOT/'runtime_status.json',{});active=s.get('phase') not in ('IDLE','STOPPED','ERROR',None) and alive(s.get('pid'))
 return {'paused':paused(),'active':active,'runtime':s,'updatedAt':now(),'message':'本地处理已停止；云端已提交任务可能继续' if paused() else ('本地脚本正在运行：'+s.get('phase','') if active else '本地空闲；已完成项目不再运行媒体检测')}
def set_paused(value):
 save(ROOT/'local_control.json',{'paused':bool(value),'updatedAt':now(),'source':'Explicit local UI click'})
 return status()
