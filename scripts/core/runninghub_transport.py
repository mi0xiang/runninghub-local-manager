"""RunningHub submit / poll / download; no automatic resubmission."""
from pathlib import Path
import argparse,json,os,urllib.request,urllib.error,uuid,hashlib,sys
ROOT=Path(__file__).parent
HOST='https://www.runninghub.cn'
import local_control
def key():
    value=os.environ.get('RUNNINGHUB_API_KEY','').strip()
    if not value and os.name=='nt':
        import winreg
        for hive,path in [(winreg.HKEY_CURRENT_USER,'Environment'),(winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')]:
            try:
                with winreg.OpenKey(hive,path) as k:value=winreg.QueryValueEx(k,'RUNNINGHUB_API_KEY')[0].strip()
                if value:break
            except FileNotFoundError:pass
    if not value:raise RuntimeError('RUNNINGHUB_API_KEY is unavailable in Process/User/Machine. No request submitted.')
    return value
def post(endpoint,payload,secret):
    local_control.checkpoint();local_control.phase("API_REQUEST",operation="submit" if endpoint.endswith("create") else "query")
    body=json.dumps(payload,ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(HOST+endpoint,data=body,headers={'Content-Type':'application/json','Authorization':'Bearer '+secret})
    try:
        with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)
    except urllib.error.HTTPError as exc:
        try:out=json.loads(exc.read())
        except (ValueError,UnicodeError):raise RuntimeError('HTTP response without usable business code; outcome unknown') from None
        if not isinstance(out,dict) or not isinstance(out.get('code'),int):raise RuntimeError('HTTP response without usable business code; outcome unknown') from None
        out['httpStatus']=exc.code;return out
def upload(path,secret):
    local_control.checkpoint();local_control.phase("API_UPLOAD")
    ext=path.suffix.lower()
    mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.wav':'audio/wav','.mp3':'audio/mpeg','.mp4':'video/mp4'}.get(ext)
    if not mime:raise ValueError('Unsupported reference upload type')
    boundary='----Codex'+uuid.uuid4().hex
    data=bytearray()
    for field,value in [('apiKey',secret),('fileType','input')]:
        data.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'.encode())
    data.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="reference{ext}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
    data.extend(path.read_bytes());data.extend(f'\r\n--{boundary}--\r\n'.encode())
    req=urllib.request.Request(HOST+'/task/openapi/upload',data=bytes(data),headers={'Content-Type':'multipart/form-data; boundary='+boundary,'Authorization':'Bearer '+secret})
    with urllib.request.urlopen(req,timeout=90) as r:out=json.load(r)
    if out.get('code')!=0:raise RuntimeError('Upload rejected, code='+str(out.get('code')))
    return out['data']['fileName']
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
