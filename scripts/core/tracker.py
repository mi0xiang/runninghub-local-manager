"""Durable scheduled tick: reconcile existing tasks, then continue approved waves."""
from pathlib import Path
import datetime,json,os,html,argparse,hashlib,msvcrt
from urllib.parse import quote
from run_approved_queue import validate,submit
from collector import collect
from runninghub_transport import key
from task_outcomes import counts
from api_policy import retryable
R=Path(__file__).resolve().parent
def now():return datetime.datetime.now().astimezone().isoformat(timespec='seconds')
def read(p,default=None):return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
def save(p,x):
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,p)
def event(kind,batch='',**data):
    with (R/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(time=now(),event=kind,batch=batch,**data),ensure_ascii=False)+'\n')
BLOCKED={'NEEDS_REVIEW','SUBMITTING_OUTCOME_UNKNOWN','UPLOADING','REJECTED_OR_UNKNOWN','REJECTED','FAILED'}
def next_wave(waves,states):
    if any(v in BLOCKED for v in states.values()):return []
    for wave in waves:
        if not all(states.get(n)=='ARCHIVED' for n in wave):return wave
    return []
def rows():
    result=[]
    for name in read(R/'batches.json',[]):
        d=R/name;s=read(d/'task_state.json',{});m=read(d/'manifest.json',{})
        videos=[]
        for manifest in d.glob('results/*/manifest.json'):
            archive=read(manifest)
            for entry in archive['files']:
                p=manifest.parent/entry['name']
                if p.exists():videos.append({'path':p.relative_to(R).as_posix(),'probe':entry['probe'],'receivedAt':archive['receivedAt']})
        result.append({'reference':(m.get('reference_images') or ['assets/storyboard_3x1.png'])[0],'name':name,'state':s.get('status',m.get('status','UNKNOWN')),'updated':s.get('lastCheckedAt',s.get('submittedAt','')),'taskId':str(s.get('taskId','')),'videos':videos,'review':read(d/'review.json',{'status':'待人工复核'}),'reason':s.get('reason',''),'failure':s.get('failure') or read(d/'failure.json',{}),'instanceType':s.get('requestedInstanceType') or m.get('instanceType')})
    return result
def render_html(items,status,events):
    esc=lambda v:html.escape(str(v),quote=True)
    titles={'WAITING_CAPACITY':'等待并发名额','WAITING_INSTANCE':'等待可用实例','QUERY_RATE_LIMITED':'查询限频 · 等待重查','REJECTED_OR_UNKNOWN':'提交结果待核对','FAILED':'失败 · 已结束','CANCELLED':'取消 · 已结束','ARCHIVED':'已下载 · 待复核','APPROVED':'已批准 · 等待提交','RUNNING':'云端生成中','QUEUED':'云端排队中','NEEDS_REVIEW':'需要处理','RETRY_QUERY_OR_DOWNLOAD':'等待重试查询/下载'}
    cards=[]
    for item in sorted(items,key=lambda v:v['updated'],reverse=True):
        name=item['name'];base=quote(name)+'/';media=''
        for v in item['videos']:
            probe=v['probe'];dur=probe.get('format',{}).get('duration','?');streams=probe.get('streams',[]);video=next((s for s in streams if s.get('codec_type')=='video'),{})
            media+=f'<video controls preload="metadata" src="{quote(v["path"])}"></video><p>{esc(dur)} 秒 · {video.get("width","?")} × {video.get("height","?")} · <a href="{quote(v["path"])}">打开原片</a></p>'
        if not media:media='<div class="pending">尚无本地成片</div>'
        failure=item.get('failure') or {}
        if item['state'] in ('FAILED','CANCELLED'):media='<div class="pending" style="color:#ffb3a7">本次运行已失败，没有成片；可在上方选择 Plus 重跑。</div>'
        details=('<section role="alert" style="border:1px solid #ef8c7c;padding:14px;border-radius:8px"><strong>'+esc(failure.get('summary') or item.get('reason') or '运行失败')+'</strong><p>'+esc(failure.get('advice',''))+'</p><details><summary>展开完整失败原因 / 错误码 / 节点</summary><pre>'+esc(failure.get('detail') or item.get('reason','平台未提供详情'))+'</pre></details></section>') if failure or item['state'] in ('FAILED','CANCELLED') else ''
        review_note='' if item['state'] in ('FAILED','CANCELLED') else '<p>画面验收：'+esc(item.get('review',{}).get('status','待人工复核'))+'。下载与容器检查不等于画面合格。</p>'
        cards.append(f'<article data-task-state="{esc(item["state"])}"><header><h2>{esc(name)}</h2><span>{esc(titles.get(item["state"],item["state"]))}</span></header><p class="muted">最后更新 {esc(item["updated"] or "等待执行")} · 任务 {esc(item["taskId"] or "尚未提交")} · 请求机型：{esc(item.get("instanceType") or "平台默认")}</p>{details}<div class="columns"><div><img src="{base}{quote(item.get("reference","assets/storyboard_3x1.png"))}" alt="参考分镜"><p><a href="{base}H3_prompt.txt">H3 提示词</a> · <a href="{base}task_state.json">任务记录</a> · <a href="{base}workflow_prepared.json">工作流</a></p></div><div>{media}</div></div>{review_note}</article>')
    history=''.join('<li>'+esc(e['time'])+' · '+esc(e.get('batch',''))+' · '+esc(e['event'])+' '+esc(e.get('status',''))+'</li>' for e in reversed(events[-100:]))
    completed=sum(bool(i['videos']) for i in items)
    totals=counts(i['state'] for i in items)
    alerts=[i for i in items if i['state'] in BLOCKED or i['state']=='RETRY_QUERY_OR_DOWNLOAD']
    alert=''.join('<p>'+esc(i['name'])+'：'+esc(titles.get(i['state'],i['state']))+' · '+esc(i.get('reason',''))+'</p>' for i in alerts) or '<p>没有已记录的生成异常；已下载成片等待人工复核。</p>'
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>视频生成追踪</title><style>body{margin:0;background:#0c161e;color:#e5edf2;font:15px/1.65 system-ui}main{max-width:1240px;margin:auto;padding:32px}h1{font-size:32px}h2{font-size:20px}a{color:#69d7ef}article,.summary{background:#152630;border:1px solid #29434f;border-radius:14px;padding:22px;margin:22px 0}header{display:flex;justify-content:space-between;gap:20px;align-items:center}header span{color:#69d7ef}.columns{display:grid;grid-template-columns:1.4fr 1fr;gap:24px}img{width:100%;border-radius:9px}video{width:100%;max-height:520px;background:#000;border-radius:9px}.muted{color:#9aadb8;font-size:13px}.pending{padding:60px;text-align:center;color:#9aadb8;background:#0d1b24}button{padding:8px 18px;border-radius:8px;border:0;cursor:pointer}pre{white-space:pre-wrap}li{margin:8px 0}@media(max-width:750px){.columns{grid-template-columns:1fr}main{padding:15px}header{display:block}}</style><main><h1>视频生成 · 过程与复核</h1>'''+f'<p>最近更新倒序 · 本地项目 · 独立批次</p><div class="summary"><strong>{totals['ended']} / {len(items)} 已结束 · 成功 {totals['success']} · 失败 {totals['failed']} · 已下载 {completed}</strong><p>后台状态：{esc({'COMPLETE':'已结束','COMPLETE_WITH_FAILURES':'已结束（含失败）'}.get(status.get('state'),status.get('state','UNKNOWN')))} · <span id="heartbeat"></span></p><p class="muted">记录时间：{esc(status.get("updatedAt",""))}。{"本批运行已结束；失败记录保留，重跑请使用对应按钮。" if totals['ended']==len(items) else "后台每2分钟检查；运行中请勿重复提交。"}</p><button onclick="location.reload()">刷新本地记录</button><label> <input id="auto" type="checkbox" checked>空闲时自动刷新</label></div><section><h2>异常与复核</h2>{alert}</section>'+''.join(cards)+f'<details><summary>展开过程记录（最近100条，倒序）</summary><ol>{history}</ol></details><p class="muted">记录来源：task_state.json / events.jsonl / tracker_status.json。播放本地原始视频，不触发生成；生成重跑仍需批准。</p></main><script>const updated={json.dumps(status.get("updatedAt",""))};const complete={str(status.get("state") in ("COMPLETE","COMPLETE_WITH_FAILURES")).lower()};function pulse(){{const age=(Date.now()-Date.parse(updated))/1000;document.getElementById("heartbeat").textContent=complete?"本批已结束":age>360?"心跳已过期，后台可能中断":"后台最近有更新"}}pulse();setInterval(pulse,10000);setInterval(()=>{{if(document.getElementById("auto").checked&&![...document.querySelectorAll("video")].some(v=>!v.paused))location.reload()}},60000);</script></html>'
def publish():
    events=[]
    if (R/'events.jsonl').exists():
        for line in (R/'events.jsonl').read_text(encoding='utf-8').splitlines():
            try:events.append(json.loads(line))
            except json.JSONDecodeError:pass
    status=read(R/'tracker_status.json',{'state':'NOT_STARTED','updatedAt':now()})
    content=render_html(rows(),status,events);p=R/'index.html';t=R/'index.html.tmp';t.write_text(content,encoding='utf-8');os.replace(t,p)
def tick():
    # OS lock releases automatically on termination, unlike stale PID files.
    with (R/'tracker.process.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        status={'state':'RECONCILING','updatedAt':now(),'pid':os.getpid()};save(R/'tracker_status.json',status);publish()
        try:
            approval=validate();secret=None
            names=[b['name'] for b in approval['approved_batches']]
            for name in names:
                folder=R/name;s=read(folder/'task_state.json',{})
                if s.get('status') in BLOCKED|{'CANCELLED'}:continue
                if not s.get('taskId'):continue
                archive=folder/'results'/('task-'+str(s['taskId']))/'manifest.json'
                if archive.exists():
                    a=read(archive)
                    intact=all((archive.parent/f['name']).exists() and (archive.parent/f['name']).stat().st_size==f['bytes'] for f in a['files'])
                    if intact:
                        if s.get('status')!='ARCHIVED':
                            s.update(status='ARCHIVED',lastCheckedAt=now());save(folder/'task_state.json',s);event('reconciled_archive',name,status='ARCHIVED')
                        continue
                    archive.rename(archive.with_suffix('.invalid.json'))
                age=(datetime.datetime.now().astimezone()-datetime.datetime.fromisoformat(s.get('submittedAt',now()))).total_seconds()
                if age<480:continue
                try:
                    secret=secret or key();result=collect(folder,secret)
                    s.update(result,lastCheckedAt=now());save(folder/'task_state.json',s)
                    event('query_and_receive',name,status=result['status'],taskId=s['taskId'])
                except Exception as exc:
                    s.update(status='RETRY_QUERY_OR_DOWNLOAD',lastCheckedAt=now(),reason=type(exc).__name__);save(folder/'task_state.json',s);event('receive_error',name,errorType=type(exc).__name__)
                status['updatedAt']=now();save(R/'tracker_status.json',status);publish()
            states={n:read(R/n/'task_state.json',{}).get('status','APPROVED') for n in names}
            wave=next_wave(approval['planned_waves'],states)
            for name in wave:
                previous=read(R/name/'task_state.json',{})
                if previous and not retryable(previous):continue
                event('approved_submission_start',name)
                try:
                    secret=secret or key();s=submit(R/name,secret,approval['workflowId']);event('submitted',name,taskId=s.get('taskId'),status=s['status'])
                except Exception as exc:event('submission_stopped',name,errorType=type(exc).__name__);break
            states={n:read(R/n/'task_state.json',{}).get('status','APPROVED') for n in names}
            status.update(state=counts(states.values())['state'] if counts(states.values())['ended']==len(states) else 'NEEDS_REVIEW' if any(v in BLOCKED for v in states.values()) else 'WAITING',updatedAt=now(),batches=states)
            save(R/'tracker_status.json',status)
        except Exception as exc:
            status.update(state='NEEDS_REVIEW',updatedAt=now(),errorType=type(exc).__name__);save(R/'tracker_status.json',status);event('tick_error',errorType=type(exc).__name__)
        finally:publish();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--render-only',action='store_true');a=p.parse_args()
    publish() if a.render_only else tick()
