"""Single-record Lark request contract with local target binding; no cloud action."""
import datetime
import json
from pathlib import Path
import re
import uuid

FIELD_TYPES={'复刻阶段':3,'复刻任务':1}
STAGES={'准备复刻','复刻中','生成待审核','已确认','需处理','暂缓'}
VERSION='lark-snapshot/v1'
TTL=datetime.timedelta(minutes=15)

def load_binding(root):
    """Absent/invalid local configuration blocks only new Lark diff requests."""
    path=Path(root)/'coordination/lark-target.json'
    try:return json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:return None
    except (OSError,ValueError):return {}

def validate_binding(binding):
    if not isinstance(binding,dict) or type(binding.get('schema_version')) is not int or binding['schema_version']!=1:
        raise ValueError('Lark binding schema_version 1 required')
    target=binding.get('target');fields=binding.get('fields')
    if not isinstance(target,dict) or set(target)!={'base_token','table_id','view_id'}:
        raise ValueError('Exact Lark target identity required')
    for name,prefix in (('base_token',''),('table_id','tbl'),('view_id','vew')):
        value=target[name]
        if not isinstance(value,str) or not re.fullmatch(prefix+'[A-Za-z0-9]{1,120}',value):
            raise ValueError('Invalid Lark resource identity')
    if not isinstance(fields,dict) or set(fields)!=set(FIELD_TYPES):
        raise ValueError('Both adapter field definitions required')
    for name,kind in FIELD_TYPES.items():
        field=fields[name]
        if (not isinstance(field,dict) or set(field)!={'field_id','type'}
                or type(field['type']) is not int or field['type']!=kind
                or not isinstance(field['field_id'],str) or not re.fullmatch('fld[A-Za-z0-9]{1,120}',field['field_id'])):
            raise ValueError('Invalid adapter field identity or type')
    if len({field['field_id'] for field in fields.values()})!=len(fields):
        raise ValueError('Distinct adapter fields required')
    return target,fields

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def timestamp(value):
    parsed=datetime.datetime.fromisoformat(value)
    if parsed.tzinfo is None:raise ValueError('Timezone required')
    return parsed

def text_value(value):
    if isinstance(value,list):
        if not all(isinstance(x,dict) and isinstance(x.get('text'),str) for x in value):
            raise ValueError('Unsupported text representation')
        return ''.join(x['text'] for x in value) or None
    if value is None or isinstance(value,str):return value or None
    raise ValueError('Unsupported text representation')

def request_id(value):
    if not isinstance(value,str) or str(uuid.UUID(value))!=value:raise ValueError('Canonical UUID required')
    return value

def build_request(item,snapshot,max_age_minutes=15,*,binding=None):
    result={'status':'BLOCKED','request':None,'may_dispatch':False,'project_id':item.get('project_id'),
            'local_revision':item.get('local_revision')}
    if binding is None:return dict(result,status='LARK_NOT_CONFIGURED')
    try:target,fields=validate_binding(binding)
    except (KeyError,TypeError,ValueError):return dict(result,status='INVALID_LARK_CONFIGURATION')
    try:
        created=timestamp(now());observed=timestamp(snapshot['captured_at'])
        age=created-observed
        if age<datetime.timedelta(0) or age>min(TTL,datetime.timedelta(minutes=max_age_minutes)):
            return dict(result,status='STALE_SNAPSHOT')
        if (snapshot.get('schema_version')!=1 or snapshot.get('version')!=VERSION
                or snapshot.get('status')!='ok' or snapshot.get('read_source')!='live'
                or snapshot.get('target')!=target):raise ValueError('Fresh live configured-target snapshot required')
        snapshot_id=request_id(snapshot['snapshot_id'])
        digest=snapshot.get('_file_sha256')
        if not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):
            raise ValueError('Actual snapshot file hash required')
        for name,field in fields.items():
            definitions=[f for f in snapshot['fields'] if f.get('field_name')==name]
            if len(definitions)!=1 or definitions[0].get('field_id')!=field['field_id'] or definitions[0].get('type')!=field['type']:
                raise ValueError('Field identity or type changed')
        for name in ('project_id','local_revision'):
            if not isinstance(item.get(name),str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,119}',item[name]):
                raise ValueError('Invalid local identifier')
        if not re.fullmatch('rec[A-Za-z0-9]{1,40}',item.get('record_id','')):raise ValueError('Invalid record identity')
        if not re.fullmatch('tiktok:[0-9]{10,25}',item.get('source_key','')):raise ValueError('Invalid source identity')
        records=snapshot['records']
        by_id=[r for r in records if r.get('record_id')==item['record_id']]
        by_source=[r for r in records if text_value(r.get('fields',{}).get('来源去重键'))==item['source_key']]
        if len(by_id)!=1 or len(by_source)!=1 or by_source[0]!=by_id[0]:raise ValueError('Ambiguous record/source identity')
        desired={'复刻阶段':item['stage_label'],'复刻任务':item['task_label']}
        if desired['复刻阶段'] not in STAGES or not isinstance(desired['复刻任务'],str) or len(desired['复刻任务'])>4000:
            raise ValueError('Invalid desired values')
        expected={name:text_value(by_id[0].get('fields',{}).get(name)) for name in fields}
        expires=min(created+TTL,observed+TTL)
        if expires<=created:raise ValueError('Snapshot validity exhausted')
        req={'schema_version':1,'request_id':str(uuid.uuid4()),
             **{name:item[name] for name in ('project_id','record_id','source_key','local_revision')},
             'snapshot_revision':snapshot_id,'observed_at':snapshot['captured_at'],
             'created_at':created.isoformat(),'expires_at':expires.isoformat(),'target':dict(target),
             'input_snapshot':{'snapshot_id':snapshot_id,'captured_at':snapshot['captured_at'],'version':VERSION,'sha256':digest},
             'expected':expected,'desired':desired}
        status='NO_CHANGE' if all(text_value(desired[k])==v for k,v in expected.items()) else 'READY'
        return dict(result,status=status,request=req)
    except (KeyError,TypeError,ValueError,OverflowError):
        return dict(result,status='IDENTITY_OR_SNAPSHOT_CONFLICT')

def same_diff(left,right):
    """Only reuse an immutable request when every semantic input is identical."""
    return {k:v for k,v in left.items() if k not in ('request_id','created_at','expires_at')}=={
            k:v for k,v in right.items() if k not in ('request_id','created_at','expires_at')}

def check_receipt(request,receipt,request_sha256=None):
    status=receipt.get('status')
    keys=('request_id','project_id','record_id','source_key','local_revision','snapshot_revision','target','input_snapshot')
    identity=all(k in request and receipt.get(k)==request[k] for k in keys)
    digest_ok=bool(request_sha256 and receipt.get('request_sha256')==request_sha256)
    if not identity or not digest_ok or status not in ('APPLIED','NO_CHANGE','CONFLICT','FAILED','UNKNOWN','RECONCILE_REQUIRED'):
        status='CONFLICT'
    elif status in ('UNKNOWN','RECONCILE_REQUIRED'):
        status='RECONCILE_REQUIRED'
    elif status in ('APPLIED','NO_CHANGE'):
        try:
            timestamp(receipt['readback_at'])
            readback=receipt['readback']
            if (not isinstance(readback,dict) or set(readback)!=set(request['desired'])
                    or request['record_id'] not in receipt.get('verified_record_ids',[])
                    or any(text_value(readback[k])!=text_value(v) for k,v in request['desired'].items())):
                status='CONFLICT'
        except (KeyError,TypeError,ValueError):status='CONFLICT'
    return {'sync_state':status,'preserve_local_results':True,'may_dispatch':False,'may_retry':False}
