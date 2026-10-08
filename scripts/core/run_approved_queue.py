"""One approved run, at most three jobs per wave; never retry generation."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,time
from runninghub_transport import key,post,upload
from collector import collect
import local_control
import native_references
from api_policy import retryable,rejected,WAITING
R=Path(__file__).parent
def stamp():return datetime.datetime.now().astimezone().isoformat(timespec='seconds')
def save(p,x):
    import durable_store
    durable_store.save(p,x)
def log(msg):
    with (R/'queue.log').open('a',encoding='utf-8') as f:f.write(stamp()+' '+msg+'\n')
def validate():
    a=json.loads((R/'approval.json').read_text(encoding='utf-8'))
    assert a['status']=='APPROVED' and a['upload_permitted'] and a['submit_permitted']
    flattened=sum(a['planned_waves'],[])
    assert len(flattened)==len(set(flattened))
    assert set(flattened)=={b['name'] for b in a['approved_batches']}
    assert all(len(w)<=3 for w in a['planned_waves'])
    assert not set(flattened)&set(a['excluded_batches'])
    for b in a['approved_batches']:
        d=R/b['name'];assert d.parent==R and d.is_dir()
        for n,h in b['hashes'].items():
            assert hashlib.sha256((d/n).read_bytes()).hexdigest()==h, 'Approved asset changed: '+b['name']+'/'+n
    return a
def submission_payload(secret,workflow_id,graph,instance_type=None,node_info=None):
    payload={'apiKey':secret,'workflowId':workflow_id,'workflow':json.dumps(graph,ensure_ascii=False)}
    if node_info is not None:payload['nodeInfoList']=node_info
    if instance_type is not None:
        if instance_type not in ('default','plus','ultra'):raise ValueError('Unsupported instanceType')
        payload['instanceType']=instance_type
    return payload

def submit(folder,secret,workflow_id):
    statefile=folder/'task_state.json'
    attempt=1
    if statefile.exists():
        state=json.loads(statefile.read_text(encoding='utf-8'))
        if state.get('taskId'):return state
        if not retryable(state):return state
        attempt=state.get('submitAttempts',0)+1
    local_control.checkpoint()
    validate()
    meta=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    graph=json.loads((folder/meta['workflow']).read_text(encoding='utf-8'))
    native_references.verify(graph,meta)
    instance_type=meta.get('instanceType')
    submission_payload(secret,workflow_id,graph,instance_type)  # validate before uploads
    if len(meta.get('reference_audio',[]))!=len(meta.get('audio_node_ids',[])):raise ValueError('Audio mapping incomplete')
    for node in meta.get('audio_node_ids',[]):
        if node not in graph or 'audio' not in graph[node].get('inputs',{}):raise ValueError('Audio loader missing')
    videos=meta.get('reference_videos',[])
    video_nodes=meta.get('video_node_ids',[])
    if len(videos)!=len(video_nodes) or len(set(video_nodes))!=len(video_nodes):
        raise ValueError('Video mapping incomplete or duplicated')
    for node in video_nodes:
        loader=graph.get(node,{})
        native_references.video_field(loader)
    # Reserve before any upload. A crash can never silently resubmit this batch.
    save(statefile,{'status':'UPLOADING','batch':meta['batch'],'startedAt':stamp(),'submitAttempts':attempt})
    mapping=[]
    for node,rel in zip(meta['image_node_ids'],meta['reference_images']):
        remote=upload(folder/rel,secret);graph[node]['inputs']['image']=remote
        mapping.append({'node':node,'local':rel,'remote':remote})
    for node,rel in zip(meta.get('audio_node_ids',[]),meta.get('reference_audio',[])):
        remote=upload(folder/rel,secret);graph[node]['inputs']['audio']=remote
        mapping.append({'node':node,'local':rel,'remote':remote,'type':'audio'})
    for node,rel in zip(video_nodes,videos):
        remote=upload(folder/rel,secret);graph[node]['inputs'][native_references.video_field(graph[node])]=remote
        mapping.append({'node':node,'local':rel,'remote':remote,'type':'video'})
    save(folder/'uploaded_assets.json',mapping);save(folder/'workflow_submitted.json',graph)
    save(statefile,{'status':'SUBMITTING_OUTCOME_UNKNOWN','batch':meta['batch'],'submittedAt':stamp(),'submitAttempts':attempt})
    node_info=None
    if meta.get('reference_switch_schema')=='native_20260924':
        node_info=[{'nodeId':x['node'],'fieldName':native_references.video_field(graph[x['node']]) if x.get('type')=='video' else 'audio' if x.get('type')=='audio' else 'image','fieldValue':x['remote']} for x in mapping]
        save(folder/'reference_bindings_submitted.json',node_info)
    out=post('/task/openapi/create',submission_payload(secret,workflow_id,graph,instance_type,node_info),secret)
    # Store only needed response data, excluding websocket credentials.
    data=out.get('data') if isinstance(out.get('data'),dict) else {}
    save(folder/'submit_response.json',{'code':out.get('code'),'msg':out.get('msg'),'taskId':data.get('taskId'),'taskStatus':data.get('taskStatus'),'requestedInstanceType':instance_type})
    if out.get('code')!=0 or not data.get('taskId'):
        from task_outcomes import failure_info
        failure=failure_info(out);save(folder/'failure.json',failure)
        wait=rejected(out,attempt)
        if wait:
            if wait['status']=='NEEDS_REVIEW':
                failure['summary']=wait['reason'];failure['advice']='核对平台并发、实例和账户状态后再人工处理。'
                save(folder/'failure.json',failure)
            wait.update(batch=meta['batch'],code=out.get('code'),failure=failure,requestedInstanceType=instance_type)
            wait.setdefault('reason',failure['summary']);save(statefile,wait);return wait
        confirmed_rejection=out.get('code') in (801,802,803,806,808,809,810,811,812,433,435,436) and not data.get('taskId') and not out.get('taskId')
        save(statefile,{'status':'REJECTED' if confirmed_rejection else 'REJECTED_OR_UNKNOWN','batch':meta['batch'],'code':out.get('code'),'taskId':data.get('taskId'),'reason':failure['summary'],'failure':failure,'requestedInstanceType':instance_type})
        raise RuntimeError('Submission not confirmed; no automatic retry; code='+str(out.get('code')))
    state={'requestedInstanceType':instance_type,'status':data.get('taskStatus','QUEUED'),'taskId':data['taskId'],'batch':meta['batch'],'submittedAt':stamp(),'submitAttempts':attempt,'failure':{},'reason':''}
    (folder/'failure.json').unlink(missing_ok=True)
    save(statefile,state);log('Submitted '+folder.name+' task='+str(state['taskId']))
    return state
def main():
    raise RuntimeError('Use scripts/hub.py as the only execution entry.')
if __name__=='__main__':main()
