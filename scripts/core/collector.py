import portable_runtime
"""Background collector. Never submits or retries generation."""
from pathlib import Path
import argparse,datetime,json,time,subprocess,hashlib,os,sys
from runninghub_transport import key,post
import urllib.request
from urllib.parse import quote

def download_url(url):
    return quote(url,safe=":/?#[]@!$&'()*+,;=%")
import local_control
from task_outcomes import failure_info
from api_policy import due,next_time
ROOT=Path(__file__).parent
def stamp():return datetime.datetime.now().astimezone().isoformat(timespec='seconds')
def save(path,data):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,path)
def log(msg):
    with (ROOT/'receiver.log').open('a',encoding='utf-8') as f:f.write(stamp()+' '+msg+'\n')
def collect(folder,secret,query_only=False):
    local_control.checkpoint()
    state=json.loads((folder/'task_state.json').read_text(encoding='utf-8'));task=state.get('taskId')
    if state.get('status') in ('FAILED','CANCELLED'):return state
    if state.get('status')=='QUERY_RATE_LIMITED' and not due(state,'nextQueryAt'):return state
    if not task:return {'status':'NEEDS_REVIEW','reason':'No taskId; will not submit generation.'}
    target=folder/'results'/f'task-{task}';target.mkdir(parents=True,exist_ok=True)
    if (target/'manifest.json').exists():return {'failure':{},'reason':'','queryRateAttempts':0,'nextQueryAt':None,'status':'ARCHIVED','taskId':task}
    response_path=folder/'outputs_response.json'
    out=json.loads(response_path.read_text(encoding='utf-8')) if response_path.exists() else {}
    if out.get('code') not in (0,805) or (out.get('code')==0 and not isinstance(out.get('data'),list)):
        out=post('/task/openapi/outputs',{'apiKey':secret,'taskId':task},secret)
        save(response_path,out)
    if out.get('code')==1003:
        attempt=state.get('queryRateAttempts',0)+1;failure=failure_info(out)
        return {'status':'QUERY_RATE_LIMITED','taskId':task,'code':1003,'queryRateAttempts':attempt,'nextQueryAt':next_time(attempt),'failure':failure,'reason':failure['summary']}
    if out.get('code')==805:
        failure=failure_info(out);save(folder/'failure.json',failure)
        return {'status':'FAILED','taskId':task,'code':805,'reason':failure['summary'],'failure':failure}
    if out.get('code') in (804,813):
        (folder/'failure.json').unlink(missing_ok=True)
        return {'failure':{},'reason':'','queryRateAttempts':0,'nextQueryAt':None,'status':'RUNNING' if out['code']==804 else 'QUEUED','taskId':task}
    if out.get('code')!=0:
        failure=failure_info(out);save(folder/'failure.json',failure)
        return {'status':'NEEDS_REVIEW','taskId':task,'code':out.get('code'),'reason':failure['summary'],'failure':failure}
    if query_only:return {'status':'CLOUD_SUCCEEDED','taskId':task,'failure':{},'reason':''}
    meta=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    audio_only=meta.get('media_type')=='audio'
    allowed=('mp3','wav','flac','ogg','m4a') if audio_only else ('mp4','webm','mov')
    files=[]
    for i,item in enumerate(out.get('data') or []):
        ext=str(item.get('fileType','')).lower().lstrip('.')
        if ext not in allowed or not item.get('fileUrl'):continue
        name=f'video__{folder.name}__15s__task-{task}__node-{item.get("nodeId","unknown")}__{i+1}.{ext}'
        dest=target/name
        if not dest.exists():
            existing=folder/'outputs'/f'batch{state["batch"]}_{i+1}.{ext}'
            if existing.exists():
                import shutil;shutil.copy2(existing,dest)
            else:
                url=item['fileUrl']
                if not url.startswith('https://'):raise RuntimeError('Output URL must be HTTPS')
                partial=dest.with_suffix(dest.suffix+'.part')
                with urllib.request.urlopen(download_url(url),timeout=180) as r,partial.open('wb') as f:
                    while chunk:=r.read(1024*1024):
                        local_control.checkpoint();f.write(chunk)
                os.replace(partial,dest)
        probe=local_control.media([portable_runtime.tool('ffprobe'),'-v','error','-show_entries','stream=codec_name,codec_type,width,height','-show_entries','format=duration,size','-of','json',str(dest)])
        files.append({'name':name,'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'probe':json.loads(probe),'taskCostTime':item.get('taskCostTime'),'consumeCoins':item.get('consumeCoins')})
    if not files:return {'status':'NEEDS_REVIEW','taskId':task,'reason':'Successful response contains no expected media.'}
    save(target/'manifest.json',{'batch':folder.name,'taskId':task,'receivedAt':stamp(),'files':files,'note':'Original API output, no re-encoding. Automated container verification only; not a visual quality approval.'})
    # Reproducible archive contains no API key or signed websocket connection details.
    import shutil
    for name in ('H3_prompt.txt','workflow_submitted.json','manifest.json'):
        if (folder/name).exists():shutil.copy2(folder/name,target/('input_'+name))
    state['status']='ARCHIVED';state['archive']=str(target.relative_to(ROOT));save(folder/'task_state.json',state)
    log('Archived '+folder.name+' task='+task)
    return {'failure':{},'reason':'','queryRateAttempts':0,'nextQueryAt':None,'status':'ARCHIVED','taskId':task,'archive':str(target.relative_to(ROOT))}
