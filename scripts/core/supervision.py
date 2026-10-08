"""Derived video lifecycle dashboard. Reading it never performs cloud or queue work."""
import datetime
import hashlib
import html
import json
from pathlib import Path
from urllib.parse import quote
import durable_store as store
import business_lines
import responsibility
import project_order
from archive_integrity import sha256, verify_archive
from postproduction_records import local_file

SCHEMA_VERSION=1
SUGGESTED_THRESHOLDS={'COLLECTION':60,'MATCHING':60,'PLANNING':120,'APPROVAL':0,
                      'UPLOADING':15,'GENERATING':45,'DOWNLOADING':30,'POSTPRODUCTION':120,
                      'REVIEW':0,'LARK_SYNC':60}
STAGES=[('COLLECTION','采集'),('MATCHING','文件与记录匹配'),('PLANNING','编剧 / 分镜 / 配方准备'),
        ('APPROVAL','方案与上传审批'),('QUEUE','统一队列'),('GENERATING','平台生成'),
        ('DOWNLOADING','收片归档'),('POSTPRODUCTION','拼接 / 音轨 / BGM'),
        ('REVIEW','人工审核'),('LARK_SYNC','Lark回写')]
UNKNOWN={'UPLOADING','SUBMITTING_OUTCOME_UNKNOWN','REJECTED_OR_UNKNOWN'}
FAILED={'FAILED','REJECTED','NEEDS_REVIEW','CANCELLED'}
ACTIVE={'RUNNING','QUEUED','QUERY_RATE_LIMITED','RETRY_QUERY_OR_DOWNLOAD'}
LABELS={'PLANNING':'编剧与方案准备','AWAITING_APPROVAL':'待审批','READY_FOR_QUEUE':'可入队',
        'ENQUEUED':'已排队','GENERATING':'平台生成','DOWNLOADING':'收片中',
        'POSTPRODUCTION':'后期中','AWAITING_REVIEW':'生成待审核','ACCEPTED':'已确认',
        'NEEDS_ATTENTION':'需处理','SUBMISSION_UNKNOWN':'提交结果待核对','PAUSED':'暂缓',
        'WAITING_DEPENDENCY':'待前段验收 / 后段输入'}

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def latest_instant(values):
    candidates=[]
    for value in values:
        if not value:continue
        try:
            parsed=datetime.datetime.fromisoformat(value)
            if parsed.tzinfo is None:continue
            candidates.append((parsed.timestamp(),value))
        except (ValueError,TypeError,OverflowError):continue
    return max(candidates,default=(0,''))[1]

def read(path,default=None):
    try:return store.read(path,default)
    except (OSError,ValueError,TypeError):return default

def project_folder(root,entry):
    base=(Path(root)/'projects').resolve();folder=(Path(root)/entry['path']).resolve()
    if not folder.is_relative_to(base) or folder==base:raise ValueError('Project path outside data root')
    return folder

def _records(value):
    if isinstance(value,dict):
        if value.get('project_path') and value.get('source_key'):yield value
        for item in value.values():yield from _records(item)
    elif isinstance(value,list):
        for item in value:yield from _records(item)

def assignment_for(root,folder):
    assignments=read(Path(root)/'coordination/assignments.json',{})
    matches=[x for x in _records(assignments) if (Path(root)/x['project_path']).resolve()==folder]
    if len(matches)>1:raise ValueError('Project has conflicting assignment identities')
    return matches[0] if matches else {}

def _health(timestamp,stage,config):
    threshold=config.get('stage_threshold_minutes',SUGGESTED_THRESHOLDS).get(stage,SUGGESTED_THRESHOLDS.get(stage,60))
    if threshold==0:return {'state':'WAITING_FOR_USER','threshold_minutes':0,'suggested':True}
    try:
        when=datetime.datetime.fromisoformat(timestamp)
        if when.tzinfo is None:raise ValueError('Timezone missing')
        age=(datetime.datetime.now(datetime.timezone.utc)-when).total_seconds()/60
        state='STALE_UNKNOWN' if age>threshold or age<0 else 'OBSERVED'
        return {'state':state,'age_minutes':round(age,1),'threshold_minutes':threshold,'suggested':not bool(config)}
    except (ValueError,TypeError):
        return {'state':'NOT_OBSERVED','threshold_minutes':threshold,'suggested':not bool(config)}

def _media(root,folder,relative):
    try:
        path=local_file(folder,relative)
        if path.suffix.lower() not in ('.mp4','.webm','.mov'):raise ValueError('Not a preview video')
        return '/'+quote(path.relative_to(Path(root).resolve()).as_posix(),safe='/')
    except (OSError,ValueError,TypeError):return None

def _delivery(root,folder,assignment):
    meta=read(folder/'presentation.json',{})
    evidence=read(folder/'delivery.json',{})
    relative=meta.get('result_video') if meta.get('schema_version')==1 else None
    if not relative:relative=assignment.get('delivery_video')
    # An explicit versioned delivery is authoritative, never an arbitrary newest file.
    if evidence.get('schema_version')==1:relative=evidence.get('result_video')
    if not relative:return {'state':'NOT_DELIVERED','video':None,'technical':'NOT_RECORDED'}, {'state':'PENDING'}
    url=_media(root,folder,relative)
    if not url:return {'state':'INVALID','video':None,'technical':'INVALID'}, {'state':'PENDING'}
    try:
        actual=sha256(local_file(folder,relative))
    except OSError:return {'state':'INVALID','video':None,'technical':'INVALID'}, {'state':'PENDING'}
    technical='LEGACY_NOT_REVERIFIED'
    if evidence:
        if evidence.get('complete') is not True or evidence.get('sha256')!=actual:
            return {'state':'INVALID','video':None,'technical':'INVALID'}, {'state':'PENDING'}
        checks=evidence.get('technical',{})
        technical='PASSED' if checks.get('media') is True and checks.get('decode') is True else 'PENDING'
    human=evidence.get('human_review',{}) or read(folder/'final_review.json',{})
    accepted=(human.get('status')=='APPROVED' and human.get('sha256')==actual
              and bool(human.get('evidence') or human.get('source')) and bool(human.get('reviewedAt')))
    review={'state':'ACCEPTED' if accepted else 'PENDING','evidence':human.get('evidence') if accepted else None}
    state='ACCEPTED' if accepted else 'READY_FOR_REVIEW'
    return {'state':state,'video':url,'file':relative,'sha256':actual,'technical':technical,
            'production_version':evidence.get('version')},review

def _approval_ready(folder,names):
    approval=read(folder/'approval.json',{})
    approved={x.get('name'):x for x in approval.get('approved_batches',[])}
    if not names or approval.get('status')!='APPROVED' or approval.get('upload_permitted') is not True or approval.get('submit_permitted') is not True:
        return False
    try:
        for name in names:
            if name not in approved:return False
            for relative,expected in approved[name].get('hashes',{}).items():
                if sha256(local_file(folder/name,relative))!=expected:return False
        return True
    except (OSError,ValueError,TypeError):return False

def _sync_state(root,project_id,revision):
    import lark_diff
    matches=[]
    for path in (Path(root)/'coordination/lark-outbox').glob('*.json'):
        request=read(path,{})
        if request.get('project_id')==project_id and request.get('local_revision')==revision:
            matches.append((path.stat().st_mtime,request,path))
    if not matches:return {'state':'NOT_RECORDED','verified_at':None}
    _,request,path=max(matches,key=lambda x:x[0])
    receipt=read(Path(root)/'coordination/lark-receipts'/f'{request["request_id"]}.json',{})
    if not receipt:return {'state':request.get('status','PENDING'),'verified_at':None}
    checked=lark_diff.check_receipt(request,receipt,request_sha256=sha256(path))
    return {'state':checked['sync_state'],'verified_at':receipt.get('readback_at') if checked['sync_state'] in ('APPLIED','NO_CHANGE') else None,'request_id':request['request_id']}

def project_snapshot(root,entry,config=None):
    root=Path(root).resolve();folder=project_folder(root,entry);config=config or {}
    source=read(folder/'source_reference.json',{})
    try:assignment=assignment_for(root,folder);identity_conflict=False
    except ValueError:assignment={};identity_conflict=True
    source_key=source.get('source_key') or assignment.get('source_key') or entry.get('source_key')
    record_id=source.get('record_id') or assignment.get('record_id') or entry.get('record_id')
    if source.get('record_id') and assignment.get('record_id') and source['record_id']!=assignment['record_id']:identity_conflict=True
    if source.get('source_key') and assignment.get('source_key') and source['source_key']!=assignment['source_key']:identity_conflict=True
    branch=read(folder/'coordination-state.json',{})
    handoff=read(folder/'handoff-state.json',{})
    classification=business_lines.classify(entry,source,assignment,handoff)
    identity_conflict=identity_conflict or classification['conflict']
    names=read(folder/'batches.json',[])
    if not isinstance(names,list):names=[];identity_conflict=True
    execution_plan=read(folder/'execution-plan.json',{})
    lifecycle=None
    if execution_plan.get('schema_version')==1:
        import project_runner
        try:
            lifecycle=project_runner.project_status(root,entry['id'],verify=False)
            names=list(dict.fromkeys([s['segment_id'] for s in lifecycle['segments']]+names))
        except (ValueError,KeyError,TypeError):identity_conflict=True
    owner=handoff.get('owner') or branch.get('owner') or assignment.get('branch_title') or assignment.get('owner') or '待指定'
    if lifecycle:owner=lifecycle['ownerThreadId']
    version=handoff.get('production_version') or entry.get('production_version') or entry.get('version') or folder.name
    segments=[]
    registry=read(root/'projects.json',{}).get('projects',[])
    for number,name in enumerate(names,1):
        if not isinstance(name,str) or (folder/name).resolve().parent!=folder:
            identity_conflict=True;continue
        state=read(folder/name/'task_state.json',{})
        manifest=read(folder/name/'manifest.json',{})
        planned=next((s for s in lifecycle['segments'] if s['segment_id']==name),{}) if lifecycle else {}
        archive_check=verify_archive(folder/name,state.get('taskId')) if state.get('status') in ('ARCHIVED','DOWNLOADED') else None
        attempts=[]
        for candidate in registry:
            if candidate.get('source_project')==entry['id'] and candidate.get('source_batch')==name:
                try:
                    attempt=read(project_folder(root,candidate)/name/'task_state.json',{})
                    attempts.append({'version':candidate.get('title') or candidate['id'],'task_id':attempt.get('taskId'),'status':attempt.get('status','NOT_OBSERVED')})
                except ValueError:identity_conflict=True
        segments.append({'number':number,'label':'整片生成任务' if len(names)==1 else f'生成片段 {number}',
                         'segment_id':name,'status':state.get('status',planned.get('status','NOT_SUBMITTED')),'task_id':state.get('taskId'),
                         'state_recorded':(folder/name/'task_state.json').is_file(),
                         'attempt_count':state.get('submitAttempts'), 'updated_at':state.get('lastCheckedAt') or state.get('submittedAt'),
                         'reason':state.get('reason',planned.get('reason','')),'duration_seconds':manifest.get('duration_seconds',planned.get('requested_seconds')),
                         'global_range':planned.get('global_range'),'ownerThreadId':lifecycle['ownerThreadId'] if lifecycle else None,
                         'depends_on':manifest.get('depends_on',planned.get('depends_on')),'versions':attempts,'archive_check':archive_check})
    statuses=[x['status'] for x in segments]
    delivery,review=_delivery(root,folder,assignment)
    if any(x in UNKNOWN for x in statuses):execution='SUBMISSION_UNKNOWN'
    elif any(x in FAILED for x in statuses) or any(x['archive_check'] is not None and not x['archive_check']['valid'] for x in segments):execution='NEEDS_ATTENTION'
    elif any(x in ('CLOUD_SUCCEEDED','DOWNLOADING','DOWNLOAD_ERROR') for x in statuses):execution='DOWNLOADING'
    elif any(x in ACTIVE for x in statuses):execution='GENERATING'
    elif statuses and all(x in ('ARCHIVED','DOWNLOADED') for x in statuses):execution='ORIGINALS_ARCHIVED'
    elif _approval_ready(folder,names):execution='READY_FOR_QUEUE'
    else:execution='NOT_SUBMITTED'
    post=read(folder/'postproduction.json',{})
    ready=_approval_ready(folder,names)
    queue=read(root/'queue_state.json',{}).get('jobs',[])
    enqueued=any(j.get('project')==entry['id'] and j.get('status') in ('WAITING','WAITING_CAPACITY','WAITING_INSTANCE') for j in queue)
    if identity_conflict or delivery['state']=='INVALID':stage='NEEDS_ATTENTION'
    elif review['state']=='ACCEPTED':stage='ACCEPTED'
    elif delivery['video']:stage='POSTPRODUCTION' if lifecycle and lifecycle['phase']!='REVIEW_PENDING' else 'AWAITING_REVIEW'
    elif execution in ('SUBMISSION_UNKNOWN','NEEDS_ATTENTION','GENERATING','DOWNLOADING'):stage=execution
    elif execution=='ORIGINALS_ARCHIVED':stage='POSTPRODUCTION'
    elif lifecycle and lifecycle['phase']=='WAITING_DEPENDENCY':stage='WAITING_DEPENDENCY'
    elif lifecycle and lifecycle['phase']=='CONTENT_REVIEW_AND_POSTPRODUCTION_PENDING':stage='POSTPRODUCTION'
    elif lifecycle and lifecycle['phase']=='WAITING_APPROVAL':stage='AWAITING_APPROVAL'
    elif ready:stage='ENQUEUED' if enqueued else 'READY_FOR_QUEUE'
    elif assignment.get('stage')=='暂缓':stage='PAUSED'
    elif (folder/'approval.json').exists() or handoff.get('stage') in ('AWAITING_APPROVAL','AWAITING_USER_APPROVAL'):stage='AWAITING_APPROVAL'
    else:stage='PLANNING'
    timestamp=latest_instant([handoff.get('updated_at'),branch.get('updated_at'),branch.get('updatedAt'),execution_plan.get('updated_at'),entry.get('updatedAt')]+[s['updated_at'] for s in segments]) if lifecycle else handoff.get('updated_at') or branch.get('updated_at') or branch.get('updatedAt') or max([s['updated_at'] for s in segments if s['updated_at']]+[entry.get('updatedAt','')])
    health=_health(timestamp,'REVIEW' if stage in ('AWAITING_REVIEW','ACCEPTED') else 'APPROVAL' if stage in ('AWAITING_APPROVAL','PAUSED') else 'GENERATING' if stage=='GENERATING' else stage,config)
    stage_label=LABELS[stage]
    lark_stage='需处理' if stage in ('NEEDS_ATTENTION','SUBMISSION_UNKNOWN') else '已确认' if stage=='ACCEPTED' else '生成待审核' if stage=='AWAITING_REVIEW' else '暂缓' if stage=='PAUSED' else '复刻中' if stage in ('ENQUEUED','GENERATING','DOWNLOADING','POSTPRODUCTION','WAITING_DEPENDENCY') else '准备复刻'
    original=_media(root,folder,source.get('video'))
    stage_states={'COLLECTION':'AVAILABLE' if original else 'NOT_OBSERVED','MATCHING':'CONFLICT' if identity_conflict else 'MATCHED' if source_key and record_id and original else 'NOT_CONFIRMED',
                  'PLANNING':handoff.get('stage',branch.get('step','EVIDENCE_AVAILABLE' if (folder/'approval.json').exists() else 'NOT_OBSERVED')),
                  'APPROVAL':'APPROVED' if ready else 'AWAITING_APPROVAL','QUEUE':'ENQUEUED' if enqueued else 'READY' if ready else 'NOT_READY',
                  'GENERATING':execution,'DOWNLOADING':'ARCHIVED' if execution=='ORIGINALS_ARCHIVED' else execution if execution=='DOWNLOADING' else 'NOT_COMPLETE',
                  'POSTPRODUCTION':post.get('state','COMPLETE_FILE_PRESENT' if delivery['video'] else 'NOT_RECORDED'),
                  'REVIEW':review['state'],'LARK_SYNC':'NOT_RECORDED'}
    stages=[]
    explicit=handoff.get('stages',{})
    for key,label in STAGES:
        details=explicit.get(key,{})
        stages.append({'key':key,'label':label,'state':details.get('state',stage_states[key]),
                       'owner':details.get('owner',owner if key in ('PLANNING','POSTPRODUCTION','REVIEW') else '主协调' if key in ('MATCHING','APPROVAL','LARK_SYNC') else '统一执行器' if key in ('QUEUE','GENERATING','DOWNLOADING') else '信息采集'),
                       'updated_at':details.get('updated_at'),'input_version':details.get('input_version',version),
                       'artifacts':details.get('artifacts',[]),'anomaly':details.get('anomaly',''),
                       'next_step':details.get('next_step','待人工审核' if key=='REVIEW' else '依据已核对记录接续'),
                       'health':_health(details.get('updated_at'),key,config)})
    revision=hashlib.sha256(json.dumps({'segments':segments,'delivery':delivery,'review':review,'handoff':handoff,'business_line':classification['line'],'creation_key':handoff.get('creation_key') or entry.get('creation_key'),'source_key':source_key,'record_id':record_id,'stage':stage},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    sync=_sync_state(root,entry['id'],revision) if classification['line']=='LARK' else {'state':'NOT_APPLICABLE' if classification['line']=='INDEPENDENT' else 'UNCLASSIFIED','verified_at':None}
    stages[-1].update(state=sync['state'],updated_at=sync['verified_at'],health=_health(sync['verified_at'],'LARK_SYNC',config))
    if lifecycle:
        for detail in stages:
            if detail['key'] in ('PLANNING','GENERATING','DOWNLOADING','POSTPRODUCTION'):
                detail['owner']=owner
                detail['next_step']=lifecycle['next_action']
        if lifecycle['phase']=='WAITING_DEPENDENCY':
            next(s for s in stages if s['key']=='POSTPRODUCTION').update(state='WAITING_DEPENDENCY')
    anomalies=[]
    if identity_conflict:anomalies.append('来源、记录或项目身份冲突')
    if execution=='SUBMISSION_UNKNOWN':anomalies.append('上传或提交结果未知；核对原请求，不自动重提')
    if execution=='NEEDS_ATTENTION':anomalies.append('存在失败或待处理生成任务；保留原记录，等待决定')
    if any(x['archive_check'] is not None and not x['archive_check']['valid'] for x in segments):
        anomalies.append('原件归档核验未通过：缺失、损坏或媒体校验不可用；保留原任务，不自动重生')
    if delivery['state']=='INVALID':anomalies.append('完整交付文件或哈希无效；不得标为交付')
    if health['state']=='STALE_UNKNOWN':anomalies.append('进展记录过期，当前情况未知；不等于失败')
    if sync['state'] in ('FAILED','CONFLICT','RECONCILE_REQUIRED'):anomalies.append('表格同步'+sync['state']+'；保留本机成果，核对后接续，不盲目重试')
    result={'project_id':entry['id'],'created_at':project_order.created_at(root,entry),'business_line':classification['line'],'classification':classification,
            'creation_key':handoff.get('creation_key') or entry.get('creation_key'),'title':entry.get('title',entry['id']),'production_version':version,
            'batch_title':entry.get('collection_batch_title',entry.get('collection_batch','已有制作项目')),
            'source_key':source_key,'record_id':record_id,'local_revision':revision,'stage':stage,'stage_label':stage_label,
            'lark_stage':lark_stage,'task_label':f'{entry.get("title",entry["id"])} · {version} · {stage_label}',
            'execution':{'state':execution},'delivery':delivery,'review':review,'health':health,'stages':stages,
            'segments':segments,'owner':owner,'ownerThreadId':lifecycle['ownerThreadId'] if lifecycle else entry.get('conversation_id'),
            'lifecycle':lifecycle,'updated_at':timestamp,'original_video':original,'sync':sync,
            'project_url':'/'+quote(entry['path'],safe='/')+'/index.html','anomalies':anomalies,
            'actions':{'may_create':False,'may_enqueue':ready and not any(s.get('task_id') or s['status'] in UNKNOWN|FAILED for s in segments)}}

    if classification['line']=='INDEPENDENT':
        brief=read(folder/'brief.json',{})
        detail=explicit.get('REQUIREMENTS',{})
        confirmed=brief.get('schema_version')==1 and brief.get('state')=='CONFIRMED' and bool(brief.get('requirements'))
        stages.insert(0,{'key':'REQUIREMENTS','label':'需求','state':detail.get('state','CONFIRMED' if confirmed else 'NOT_OBSERVED'),
                         'artifacts':detail.get('artifacts',['brief.json'] if confirmed else []),'owner':detail.get('owner',owner),'updated_at':detail.get('updated_at')})
    asset_paths=[name for name in ('script.md','storyboard.md','adaptation.md','production-plan.md','production_plan.md','plan.md','brief.json') if (folder/name).is_file()]
    asset_paths.extend(a for st in stages if st['key'] in ('REQUIREMENTS','PLANNING') for a in st.get('artifacts',[]) if isinstance(a,str))
    result['script_files']=[]
    for relative in dict.fromkeys(asset_paths):
        try:
            path=local_file(folder,relative)
            if path.is_file():result['script_files'].append({'name':relative,'url':'/'+quote(path.relative_to(root).as_posix(),safe='/')})
        except (ValueError,OSError):pass
    result['reference_assets']=source.get('assets',[]) if isinstance(source.get('assets',[]),list) else []
    if classification['line']=='UNCLASSIFIED':result['anomalies'].append(classification['reason'])
    result['responsibility']=responsibility.derive(result,handoff if handoff.get('decision') else branch)
    return result

def snapshot(root):
    root=Path(root).resolve();config=read(root/'coordination/supervision-config.json',{})
    result={'schema_version':1,'observed_at':now(),'suggested_threshold_minutes':SUGGESTED_THRESHOLDS,
            'coordination_interval_unchanged':True,'read_only':True,'projects':[],'alerts':[]}
    for entry in read(root/'projects.json',{}).get('projects',[]):
        if entry.get('source_project'):continue
        try:
            item=project_snapshot(root,entry,config);result['projects'].append(item)
            result['alerts'].extend({'project_id':item['project_id'],'title':item['title'],'message':message} for message in item['anomalies'])
        except (ValueError,KeyError,TypeError):result['alerts'].append({'project_id':entry.get('id'),'title':entry.get('title','项目'),'message':'项目记录不可解析或路径无效；需核对'})
    return result

def record_handoff(root,entry,data,expected_revision):
    folder=project_folder(root,entry)
    classification=business_lines.classify(entry,data,read(folder/'source_reference.json',{}))
    line=classification['line']
    required=('creation_key','production_version','owner') if line=='INDEPENDENT' else ('source_key','record_id','production_version','owner')
    if data.get('schema_version')!=1 or data.get('project_id')!=entry['id'] or not all(data.get(k) for k in required) or classification['conflict']:
        raise ValueError('Versioned identified handoff required')
    if data.get('decision'):responsibility.validate(data['decision'])
    current=read(folder/'handoff-state.json',{})
    identity=('project_id','source_key','record_id','creation_key','production_version','owner')
    if current and any(current.get(k)!=data.get(k) for k in identity):
        raise ValueError('Handoff ownership or source/version identity changed')
    if current.get('business_line') and current['business_line']!=data.get('business_line'):raise ValueError('Business identity changed')
    reference=read(folder/'source_reference.json',{})
    if reference.get('record_id') and reference['record_id']!=data.get('record_id'):raise ValueError('Source row conflict')
    if current.get('revision',0)!=expected_revision:raise RuntimeError('Handoff revision changed')
    normalized={k:v for k,v in data.items() if k not in ('revision','updated_at')}
    previous={k:v for k,v in current.items() if k not in ('revision','updated_at')}
    if normalized==previous:return current
    value=dict(normalized,revision=expected_revision+1,updated_at=now())
    path=folder/'handoffs-v1'/f'{value["revision"]:06d}.json'
    if path.exists():raise RuntimeError('Immutable handoff version exists')
    store.save(path,value);store.save(folder/'handoff-state.json',value)
    return value

def register_ready_project(root,entry):
    """Register one ready video/version independently; never submit or upload it."""
    root=Path(root).resolve();folder=project_folder(root,entry)
    classification=business_lines.classify(entry)
    independent=classification['line']=='INDEPENDENT'
    required=('creation_key','production_version') if independent else ('source_key','record_id','production_version')
    if classification['line']=='UNCLASSIFIED' or not all(entry.get(k) for k in required):
        raise ValueError('Confirmed creation or source identity and production version required')
    registry=store.read(root/'projects.json',{'projects':[]})
    identity_key='creation_key' if independent else 'source_key'
    same=[x for x in registry['projects'] if x.get(identity_key)==entry[identity_key] and x.get('production_version')==entry['production_version']]
    if same:
        if len(same)!=1 or same[0].get('record_id')!=entry.get('record_id') or project_folder(root,same[0])!=folder or (independent and business_lines.classify(same[0])['line']!='INDEPENDENT'):
            raise ValueError('Existing source/version identity conflict')
        return {'project_id':same[0]['id'],'duplicate':True,'submitted':False}
    if any(x.get('id')==entry['id'] or project_folder(root,x)==folder for x in registry['projects']):
        raise ValueError('Existing project id or path conflicts')
    if not _approval_ready(folder,read(folder/'batches.json',[])):
        raise ValueError('This project has no current approved frozen batch')
    registry['projects'].append(dict(entry,updatedAt=now()))
    store.save(root/'projects.json',registry)
    return {'project_id':entry['id'],'duplicate':False,'submitted':False}

def persist_observation(root,observed):
    """One local event per changed business state; never send chat notifications."""
    root=Path(root);path=root/'coordination/supervision-events.json'
    journal=read(path,{'schema_version':1,'events':[],'last_fingerprint':None})
    meaningful=[{'project_id':x['project_id'],'revision':x['local_revision'],'health':x['health']['state'],'anomalies':x['anomalies']} for x in observed['projects']]
    fingerprint=hashlib.sha256(json.dumps(meaningful,sort_keys=True).encode()).hexdigest()
    if journal['last_fingerprint']==fingerprint:return False
    journal['events'].append({'observed_at':observed['observed_at'],'fingerprint':fingerprint,'changes':meaningful,'alerts':observed['alerts']})
    journal['last_fingerprint']=fingerprint;store.save(path,journal)
    return True

def generate_lark_requests(root,snap):
    import lark_diff
    requests=[];binding=lark_diff.load_binding(root)
    for item in snapshot(root)['projects']:
        if business_lines.classify(item)['line']!='LARK':continue
        payload=dict(item,stage_label=item['lark_stage'])
        result=lark_diff.build_request(payload,snap,binding=binding)
        request=result['request']
        if request:
            outbox=Path(root)/'coordination/lark-outbox'
            uncertain=False
            for existing_path in outbox.glob('*.json'):
                existing=read(existing_path,{})
                if existing.get('project_id')!=request['project_id']:continue
                returned=read(Path(root)/'coordination/lark-receipts'/f"{existing.get('request_id')}.json",{})
                if returned and lark_diff.check_receipt(existing,returned,request_sha256=sha256(existing_path))['sync_state'] in ('CONFLICT','RECONCILE_REQUIRED'):
                    uncertain=True;break
            if uncertain:
                requests.append(dict(result,status='RECONCILE_REQUIRED',request=None))
                continue
            for existing_path in outbox.glob('*.json'):
                existing=read(existing_path,{})
                if lark_diff.same_diff(existing,request):
                    result['request']=existing
                    if lark_diff.timestamp(existing['expires_at'])<=lark_diff.timestamp(now()):result['status']='EXPIRED_REQUEST'
                    break
            else:
                store.save(outbox/f'{request["request_id"]}.json',request,compare=True,expected_digest=None)
        requests.append(result)
    return requests

def render_panel(data):
    from progress_visual import render_panel as render_visual
    return render_visual(data)
