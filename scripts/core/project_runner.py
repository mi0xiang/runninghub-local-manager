"""Branch-owned film plans and finite reception of explicitly selected existing tasks.

task_state.json/archives/delivery remain authoritative. Receive checkpoints contain
only scope, retries and progress; there is no upload, create, or agent wake-up path.
"""
import contextlib, datetime, hashlib, json, math, os, re, time
from pathlib import Path
import durable_store as store
from archive_integrity import sha256, verify_archive
from postproduction_records import local_file

TERMINAL={'ARCHIVED','DOWNLOADED','FAILED','CANCELLED','REJECTED','EXCLUDED_BY_USER','NEEDS_REVIEW'}
BLOCKED={'RECONCILE_REQUIRED','QUERY_BUDGET_EXHAUSTED','INTEGRITY_BLOCKED'}
ACTIVE={'RUNNING','QUEUED','CLOUD_SUCCEEDED','DOWNLOADING','DOWNLOAD_ERROR','QUERY_RATE_LIMITED','RETRY_QUERY_OR_DOWNLOAD'}
SAFE_NAME=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}$')
def now():return datetime.datetime.now(datetime.timezone.utc)
def stamp(value=None):return (value or now()).isoformat()
class StateConflict(RuntimeError):pass
def project(root, project_id):
    root=Path(root).resolve()
    entries=[x for x in store.read(root/'projects.json',{}).get('projects',[]) if x.get('id')==project_id]
    if len(entries)!=1:raise ValueError('Project identity must be registered and unique')
    entry=entries[0];folder=(root/entry['path']).resolve()
    if not folder.is_relative_to(root/'projects') or folder==root/'projects':raise ValueError('Project path escape')
    return entry,folder
def owner_of(entry,folder):
    plan=store.read(folder/'execution-plan.json',{})
    handoff=store.read(folder/'handoff-state.json',{})
    branch=store.read(folder/'coordination-state.json',{})
    candidates=[v for v in (plan.get('ownerThreadId'),entry.get('conversation_id'),handoff.get('ownerThreadId'),
                            branch.get('owner_thread_id'),branch.get('thread_id')) if v]
    if len(set(candidates))>1:raise ValueError('Owner identity conflict')
    return candidates[0] if candidates else entry.get('owner') or handoff.get('owner')
def check_owner(entry,folder,owner):
    if not owner or owner!=owner_of(entry,folder):raise ValueError('Exact project ownerThreadId required')
def _normal(record):return {k:v for k,v in record.items() if k not in ('revision','updated_at')}
def register_plan(root,project_id,record,expected_revision):
    entry,folder=project(root,project_id)
    check_owner(entry,folder,record.get('ownerThreadId'))
    version=entry.get('production_version') or store.read(folder/'handoff-state.json',{}).get('production_version')
    if record.get('schema_version')!=1 or record.get('project_id')!=project_id or not record.get('production_version'):
        raise ValueError('Versioned whole-film execution plan required')
    if version and record['production_version']!=version:raise ValueError('Frozen production version mismatch')
    segments=record.get('segments')
    if not isinstance(segments,list) or not segments:raise ValueError('Explicit whole-film segments required')
    graph={};ranges=[]
    for segment in segments:
        name=segment.get('segment_id')
        if not isinstance(name,str) or not SAFE_NAME.fullmatch(name) or name in graph:raise ValueError('Unique local segment IDs required')
        kind=segment.get('kind','generation')
        bounds=segment.get('global_range',[])
        if kind=='generation':
            seconds=float(segment.get('requested_seconds',0))
            if not math.isfinite(seconds) or not 0<seconds<=15:raise ValueError('New H3 requests must be <=15 seconds')
        elif kind=='local_media':
            if sha256(local_file(folder,segment.get('file','')))!=segment.get('sha256'):raise ValueError('Frozen reused local media hash required')
        else:raise ValueError('Explicit generation or local_media segment required')
        if len(bounds)!=2 or not all(isinstance(x,(float,int)) and math.isfinite(x) for x in bounds) or not 0<=bounds[0]<bounds[1]:
            raise ValueError('Global timeline bounds required')
        deps=segment.get('depends_on',[])
        if not isinstance(deps,list) or any(not isinstance(d,str) for d in deps):raise ValueError('Explicit dependency IDs required')
        graph[name]=deps;ranges.append(bounds)
    if ranges!=sorted(ranges):raise ValueError('Film order must follow global timeline')
    visited=set()
    def visit(name,stack):
        if name not in graph or name in stack:raise ValueError('Invalid dependency or cycle')
        if name in visited:return
        for dep in graph[name]:visit(dep,stack|{name})
        visited.add(name)
    for name in graph:visit(name,set())
    path=folder/'execution-plan.json';digest=store.digest(path);old=store.read(path,{})
    if old.get('revision',0)!=expected_revision:raise RuntimeError('Execution plan revision changed')
    if old and _normal(old)==_normal(record):return old
    if old and (old.get('production_version'),old.get('ownerThreadId'))!=(record['production_version'],record['ownerThreadId']):
        raise ValueError('Execution plan identity cannot be overwritten')
    value=dict(_normal(record),revision=expected_revision+1,updated_at=stamp())
    with store.process_lock(folder/'project-runner.process.lock'):
        if store.digest(path)!=digest:raise RuntimeError('Execution plan changed since read')
        history=folder/'execution-plans'/f'{value["revision"]:06d}.json'
        if history.exists():
            recovered=store.read(history,{})
            if _normal(recovered)!=_normal(value):raise RuntimeError('Immutable plan revision already exists')
            value=recovered  # Recover an interrupted history-before-current save.
        else:store.save(history,value)
        store.save(path,value,expected_digest=digest,compare=True)
    return value
def generation_gate(folder,name):
    folder=Path(folder);plan=store.read(folder/'execution-plan.json',{})
    segment=next((s for s in plan.get('segments',[]) if s['segment_id']==name),None)
    if not segment:return None
    reviews=store.read(folder/'segment-reviews.json',{}).get('segments',{})
    for dep in segment.get('depends_on',[]):
        task=store.read(folder/dep/'task_state.json',{})
        review=reviews.get(dep,{})
        if task.get('status') not in ('ARCHIVED','DOWNLOADED'):return '等待前段收片：'+dep
        if review.get('status')!='ACCEPTED' or review.get('taskId')!=task.get('taskId'):return '等待前段内容验收：'+dep
        try:
            if sha256(local_file(folder,review['file']))!=review['sha256'] or not review.get('evidence'):return '前段验收证据无效：'+dep
            for evidence in review['evidence']:local_file(folder,evidence)
        except (OSError,ValueError,KeyError):return '前段验收证据无效：'+dep
        if segment.get('requires_accepted_frame'):
            frame=review.get('stable_frame',{})
            try:
                if frame.get('human_accepted') is not True or not frame.get('evidence') or sha256(local_file(folder,frame['file']))!=frame['sha256']:
                    return '等待真实稳定帧人工确认：'+dep
                for evidence in frame['evidence']:local_file(folder,evidence)
            except (OSError,ValueError,KeyError):return '等待真实稳定帧人工确认：'+dep
    return None
def record_segment_review(root,project_id,record,expected_revision):
    entry,folder=project(root,project_id);check_owner(entry,folder,record.get('ownerThreadId'))
    name=record.get('segment_id','')
    if not SAFE_NAME.fullmatch(name) or record.get('schema_version')!=1 or record.get('status') not in ('ACCEPTED','REJECTED'):
        raise ValueError('Explicit identified segment content review required')
    original=store.read(folder/name/'task_state.json',{})
    if original.get('taskId')!=record.get('taskId') or original.get('status') not in ('ARCHIVED','DOWNLOADED'):
        raise ValueError('Review must bind this actual archived task')
    media=local_file(folder,record['file'])
    if not media.is_relative_to(folder/name/'results'/('task-'+record['taskId'])) or sha256(media)!=record['sha256']:
        raise ValueError('Review original hash/path mismatch')
    if not record.get('evidence'):raise ValueError('Content inspection evidence required')
    for evidence in record['evidence']:local_file(folder,evidence)
    if record.get('stable_frame'):
        frame=record['stable_frame']
        if sha256(local_file(folder,frame['file']))!=frame['sha256']:raise ValueError('Stable frame changed')
        for evidence in frame.get('evidence',[]):local_file(folder,evidence)
    path=folder/'segment-reviews.json';before=store.digest(path);old=store.read(path,{})
    if old.get('revision',0)!=expected_revision:raise RuntimeError('Segment review revision changed')
    if old.get('segments',{}).get(name)==record:return old
    value=dict(old,schema_version=1,revision=expected_revision+1,ownerThreadId=record['ownerThreadId'],updated_at=stamp())
    value['segments']=dict(old.get('segments',{}),**{name:record})
    store.save(path,value,expected_digest=before,compare=True)
    return value
def project_status(root,project_id,verify=True):
    entry,folder=project(root,project_id);plan=store.read(folder/'execution-plan.json',{})
    specs=plan.get('segments',[])
    if not specs:specs=[{'segment_id':n} for n in store.read(folder/'batches.json',[])]
    approval=store.read(folder/'approval.json',{})
    approved={s.get('name') for s in approval.get('approved_batches',[])} if approval.get('status')=='APPROVED' and approval.get('submit_permitted') is True and approval.get('upload_permitted') is True else set()
    rows=[]
    for number,spec in enumerate(specs,1):
        name=spec['segment_id'];state=store.read(folder/name/'task_state.json',{})
        status=state.get('status')
        reason=state.get('reason','')
        if spec.get('kind')=='local_media':
            try:
                if sha256(local_file(folder,spec['file']))!=spec['sha256']:raise ValueError('Changed reused media')
                status='LOCAL_MEDIA_READY';reason='复用本地片段已绑定哈希，仍需子对话检查衔接与整片内容'
            except (OSError,KeyError,ValueError):status='INTEGRITY_BLOCKED';reason='复用片段缺失或哈希变化'
        elif not status:
            gate=generation_gate(folder,name)
            status='WAITING_DEPENDENCY' if gate else 'WAITING_SUBMISSION' if name in approved else 'WAITING_APPROVAL'
            reason=gate or '待具体批次批准' if name not in approved or gate else '已有批准，等待原FIFO执行'
        check=verify_archive(folder/name,state.get('taskId')) if verify and status in ('ARCHIVED','DOWNLOADED') else None
        if check and not check['valid']:status='INTEGRITY_BLOCKED';reason=check['reason']
        rows.append(dict(spec,number=number,status=status,taskId=state.get('taskId'),
                         lastCheckedAt=state.get('lastCheckedAt'),reason=reason,archive_check=check))
    delivery=store.read(folder/'delivery.json',{})
    registration=store.read(folder/'delivery-registration.json',{})
    if any(s['status'] in ('FAILED','REJECTED','NEEDS_REVIEW','INTEGRITY_BLOCKED') for s in rows):phase='FAILURE'
    elif any(s['status'] in ACTIVE for s in rows):phase='RECEIVING'
    elif any(s['status']=='WAITING_DEPENDENCY' for s in rows):phase='WAITING_DEPENDENCY'
    elif any(s['status'] in ('WAITING_APPROVAL','WAITING_SUBMISSION') for s in rows):phase='WAITING_APPROVAL'
    elif delivery and registration.get('sha256')==delivery.get('sha256') and registration.get('delivery_revision')==delivery.get('revision'):phase='REVIEW_PENDING'
    else:phase='CONTENT_REVIEW_AND_POSTPRODUCTION_PENDING'
    next_action={'FAILURE':'子对话核对失败原任务和已有原件，提出处理选项；新费用另批',
                 'RECEIVING':'持续查询和接收原task；不重新提交',
                 'WAITING_DEPENDENCY':'子对话验收前段及真实稳定帧，再核对后段输入与具体批准',
                 'WAITING_APPROVAL':'等待具体批次审批/原FIFO；不自动生成',
                 'REVIEW_PENDING':'整片已登记，等待用户播放确认；不自动confirmed',
                 'CONTENT_REVIEW_AND_POSTPRODUCTION_PENDING':'子对话对照音画匹配表审片，完成已批准后期并登记回读'}[phase]
    return {'project_id':project_id,'ownerThreadId':owner_of(entry,folder),'production_version':plan.get('production_version') or entry.get('production_version'),
            'phase':phase,'segments':rows,'next_action':next_action,'agent_invoked':False,'may_generate':False}
def _sync_scope(root,jobs,current):
    """Refresh only existing selected queue rows and own branch tracking, under hub lock."""
    with store.process_lock(root/'hub.process.lock'):
        path=root/'queue_state.json';before=store.digest(path);queue=store.read(path,{'jobs':[]})
        selected={(j['project_id'],j['batch']):j for j in jobs};changed=False
        for row in queue.get('jobs',[]):
            job=selected.get((row.get('project'),row.get('batch')))
            if not job:continue
            if row.get('path')!=job['path'] or row.get('taskId')!=job['taskId']:
                raise StateConflict('Selected queue identity changed')
            original=store.read(root/job['path']/'task_state.json',{})
            if original.get('taskId')!=job['taskId']:raise StateConflict('Original task identity changed')
            updated=dict(row,status=original['status'],reason=original.get('reason',''),
                         lastCheckedAt=original.get('lastCheckedAt'))
            if updated!=row:row.update(updated);changed=True
        if changed:
            queue['updatedAt']=stamp(current);store.save(path,queue,expected_digest=before,compare=True)
        for project_id in dict.fromkeys(j['project_id'] for j in jobs):
            _,folder=project(root,project_id);view=project_status(root,project_id,verify=False)
            path=folder/'tracker_status.json';before=store.digest(path);old=store.read(path,{})
            value=dict(old,state=view['phase'],ownerThreadId=view['ownerThreadId'],
                       batches={s['segment_id']:s['status'] for s in view['segments']},
                       whole_film_complete=False,next_action=view['next_action'],
                       may_generate=False,agent_invoked=False)
            if any(old.get(k)!=v for k,v in value.items() if k not in ('revision','updatedAt')):
                value.update(revision=old.get('revision',0)+1,updatedAt=stamp(current))
                store.save(path,value,expected_digest=before,compare=True)

def selection_id(selection):
    return hashlib.sha256(json.dumps(selection,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24]
def _jobs(root,selection):
    allowed={'schema_version','projects','max_errors','max_minutes','poll_seconds'}
    if set(selection)-allowed or selection.get('schema_version')!=1 or not selection.get('projects'):raise ValueError('Exact receive-only selection required')
    for field,lo,hi,default in [('max_errors',1,20,5),('max_minutes',1,240,120),('poll_seconds',15,900,120)]:
        value=selection.get(field,default)
        if isinstance(value,bool) or not isinstance(value,int) or not lo<=value<=hi:raise ValueError('Invalid finite '+field)
    jobs=[];seen=set()
    for requested in selection['projects']:
        if set(requested)!= {'project_id','ownerThreadId','task_ids'}:raise ValueError('Exact project owner and original task IDs required')
        entry,folder=project(root,requested['project_id']);check_owner(entry,folder,requested['ownerThreadId'])
        if not requested['task_ids'] or len(set(requested['task_ids']))!=len(requested['task_ids']):raise ValueError('Unique existing task IDs required')
        found={}
        for name in store.read(folder/'batches.json',[]):
            if not isinstance(name,str) or not SAFE_NAME.fullmatch(name):raise ValueError('Invalid local batch')
            path=folder/name;state=store.read(path/'task_state.json',{})
            if state.get('taskId'):found.setdefault(state['taskId'],[]).append(path)
        for task in requested['task_ids']:
            if not isinstance(task,str) or not SAFE_NAME.fullmatch(task) or len(found.get(task,[]))!=1 or task in seen:raise ValueError('Original task identity is missing or duplicated')
            seen.add(task);path=found[task][0]
            jobs.append({'project_id':entry['id'],'ownerThreadId':requested['ownerThreadId'],'taskId':task,
                         'batch':path.name,'path':path.relative_to(Path(root).resolve()).as_posix()})
    return jobs
def run_lock(root,run_id):
    if not re.fullmatch('[0-9a-f]{24}',run_id):raise ValueError('Invalid run identity')
    return store.process_lock(Path(root)/'coordination/receive-runs'/(run_id+'.process.lock'))
def _step(root,selection,receive=None,secret=None,clock=None):
    root=Path(root).resolve();current=clock or now();jobs=_jobs(root,selection);run_id=selection_id(selection)
    path=root/'coordination/receive-runs'/(run_id+'.json');digest=store.digest(path);prior=store.read(path,{})
    previous={j['taskId']:j for j in prior.get('jobs',[])}
    budget=selection.get('max_errors',5);interval=selection.get('poll_seconds',120)
    started=prior.get('started_at') or stamp(current);progress=[]
    for job in jobs:
        checkpoint=dict(previous.get(job['taskId'],{}),**job);checkpoint.setdefault('errors',0)
        folder=root/job['path'];state_path=folder/'task_state.json';before=store.digest(state_path);state=store.read(state_path,{})
        checkpoint['status']=state.get('status','RECONCILE_REQUIRED')
        if checkpoint['status'] in TERMINAL:
            if checkpoint['status'] in ('ARCHIVED','DOWNLOADED'):
                check=verify_archive(folder,job['taskId'])
                if not check['valid']:checkpoint.update(status='INTEGRITY_BLOCKED',reason=check['reason'])
        elif checkpoint['errors']>=budget:checkpoint['status']='QUERY_BUDGET_EXHAUSTED'
        elif previous.get(job['taskId'],{}).get('status') in BLOCKED:checkpoint['status']=previous[job['taskId']]['status']
        elif checkpoint.get('next_poll_at') and current<datetime.datetime.fromisoformat(checkpoint['next_poll_at']):pass
        else:
            try:
                import collector
                secret=secret or collector.key()
                with store.process_lock(root/'hub.process.lock'),store.process_lock(root/'download.process.lock'):
                    if store.digest(state_path)!=before:raise StateConflict('Original task state changed')
                    collector.ROOT=folder.parent
                    result=(receive or collector.collect)(folder,secret,persist_task_state=False)
                    if result.get('taskId',job['taskId'])!=job['taskId']:raise StateConflict('Original task identity changed')
                    merged=dict(state,**result,lastCheckedAt=stamp(current),ownerThreadId=job['ownerThreadId'])
                    store.save(state_path,merged,expected_digest=before,compare=True)
                checkpoint.update(status=merged['status'],last_progress=stamp(current),errors=0)
                checkpoint.pop('error',None)
            except RuntimeError as exc:
                if isinstance(exc,StateConflict) or 'changed since read' in str(exc).lower():
                    checkpoint.update(status='RECONCILE_REQUIRED',error='State conflict; reread original record before resuming')
                elif 'busy' in str(exc).lower():
                    checkpoint.update(error='BUSY: another shared executor holds the lock')
                else:
                    checkpoint.update(errors=checkpoint['errors']+1,error=type(exc).__name__)
                    if checkpoint['errors']>=budget:checkpoint['status']='QUERY_BUDGET_EXHAUSTED'
            except Exception as exc:
                checkpoint.update(errors=checkpoint['errors']+1,error=type(exc).__name__)
                if checkpoint['errors']>=budget:checkpoint['status']='QUERY_BUDGET_EXHAUSTED'
            delay=min(interval*2**max(checkpoint['errors']-1,0),900)
            checkpoint['next_poll_at']=stamp(current+datetime.timedelta(seconds=delay))
        progress.append(checkpoint)
    try:_sync_scope(root,jobs,current)
    except RuntimeError as exc:
        if isinstance(exc,StateConflict) or 'changed since read' in str(exc).lower():
            for checkpoint in progress:checkpoint.update(status='RECONCILE_REQUIRED',error='Selected tracking conflict; preserve current records')
        elif 'busy' in str(exc).lower():
            for checkpoint in progress:checkpoint['error']='BUSY: tracking refresh deferred'
        else:raise
    terminal=all(j['status'] in TERMINAL for j in progress)
    blocked=any(j['status'] in BLOCKED for j in progress) and all(j['status'] in TERMINAL|BLOCKED for j in progress)
    session_started=prior.get('session_started_at') or started
    timed_out=(current-datetime.datetime.fromisoformat(session_started)).total_seconds()>=selection.get('max_minutes',120)*60
    state='TERMINAL' if terminal else 'BLOCKED' if blocked else 'TIME_LIMIT' if timed_out else 'RUNNING'
    result={'schema_version':1,'run_id':run_id,'selection':selection,'revision':prior.get('revision',0)+1,
            'started_at':started,'session_started_at':session_started,'session_count':prior.get('session_count',0),
            'updated_at':stamp(current),'state':state,'jobs':progress,
            'next_action':'由各owner子对话继续内容验收、已批准后期及成片登记' if terminal else '核对受阻项；保留原task，不生成重试',
            'paid_calls':0,'agent_invoked':False}
    store.save(path,result,expected_digest=digest,compare=True)
    return result
def step(root,selection,**kwargs):
    _jobs(root,selection)
    with run_lock(root,selection_id(selection)):return _step(root,selection,**kwargs)
def run(root,selection,once=False,on_progress=None,resume_errors=False):
    _jobs(root,selection)
    with run_lock(root,selection_id(selection)):
        path=Path(root)/'coordination/receive-runs'/(selection_id(selection)+'.json')
        before=store.digest(path);old=store.read(path,{})
        old.update(session_started_at=stamp(),session_count=old.get('session_count',0)+1)
        if resume_errors:
            for job in old.get('jobs',[]):
                if job.get('status') in BLOCKED:
                    job.update(errors=0,status='RESUME_ORIGINAL_ONLY',next_poll_at=None)
            old['manual_error_resume_at']=stamp()
        store.save(path,old,expected_digest=before,compare=True)
        start=time.monotonic()
        try:
            while True:
                result=_step(root,selection)
                if on_progress:on_progress(result)
                if once or result['state']!='RUNNING':return result
                if time.monotonic()-start>=selection.get('max_minutes',120)*60:return result
                # Finite, foreground and interruptible. Closing this process stops polling.
                time.sleep(min(selection.get('poll_seconds',120),30))
        except KeyboardInterrupt:
            before=store.digest(path);value=store.read(path,{})
            value.update(state='STOPPED',updated_at=stamp(),next_action='Manually restart this selection; original cloud tasks were not cancelled')
            store.save(path,value,expected_digest=before,compare=True)
            return value
def register_delivery(root,project_id,owner,expected_revision):
    entry,folder=project(root,project_id);check_owner(entry,folder,owner)
    delivery=store.read(folder/'delivery.json',{})
    if delivery.get('revision')!=expected_revision:raise RuntimeError('Delivery revision changed')
    video=local_file(folder,delivery.get('result_video',''))
    digest=sha256(video);technical=delivery.get('technical',{});content=delivery.get('content_review',{})
    if delivery.get('complete') is not True or digest!=delivery.get('sha256') or not all(technical.get(k) is True for k in ('media','decode')):
        raise ValueError('Exact complete technical delivery required')
    if content.get('status')!='ACCEPTED' or content.get('sha256')!=digest or content.get('ownerThreadId')!=owner or not content.get('evidence'):
        raise ValueError('Branch whole-film content review required')
    for evidence in content['evidence']:local_file(folder,evidence)
    presentation=store.read(folder/'presentation.json',{})
    if presentation.get('result_video')!=delivery['result_video']:raise ValueError('Presentation points to another result')
    from html.parser import HTMLParser
    from urllib.parse import unquote,urlsplit
    class MediaPaths(HTMLParser):
        def __init__(self):super().__init__();self.paths=[]
        def handle_starttag(self,tag,attrs):
            if tag in ('video','source','a'):
                for key,value in attrs:
                    if key in ('src','href') and value:self.paths.append(unquote(urlsplit(value).path).replace('\\','/'))
    parser=MediaPaths();parser.feed((folder/'index.html').read_text(encoding='utf-8-sig'))
    expected=delivery['result_video'].replace('\\','/')
    absolute='/'+video.relative_to(Path(root).resolve()).as_posix()
    if expected not in parser.paths and absolute not in parser.paths:raise ValueError('Project page has not registered this complete result')
    # Read the same status source the supervision API uses; no cloud or Lark calls.
    import supervision
    observed=supervision.project_snapshot(root,entry)
    if observed['delivery'].get('sha256')!=digest:raise ValueError('Tracking readback does not match delivery')
    record={'schema_version':1,'project_id':project_id,'ownerThreadId':owner,'delivery_revision':expected_revision,
            'sha256':digest,'result_video':delivery['result_video'],'tracking_revision':observed['local_revision'],
            'state':'REVIEW_PENDING','registered_at':stamp(),'human_confirmation':False}
    path=folder/'delivery-registration.json';before=store.digest(path);prior=store.read(path,{})
    if all(prior.get(k)==record.get(k) for k in record if k!='registered_at'):return prior
    store.save(path,record,expected_digest=before,compare=True);return record
