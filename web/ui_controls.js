(function(root){
 const running=new Set(['RUNNING','UPLOADING','QUERY_RATE_LIMITED','RETRY_QUERY_OR_DOWNLOAD']);
 const waiting=new Set(['WAITING','WAITING_CAPACITY','WAITING_INSTANCE','QUEUED']);
 const done=new Set(['CLOUD_SUCCEEDED','DOWNLOADING','DOWNLOAD_ERROR','ARCHIVED','DOWNLOADED']);
 const group=j=>running.has(j.status)?0:waiting.has(j.status)?1:done.has(j.status)?2:3;
 const time=j=>Date.parse(j.submittedAt||'')||0;
 const order=j=>Number.isFinite(Number(j.order))?Number(j.order):Number.MAX_SAFE_INTEGER;
 function matches(j,mode){return mode==='all'||(mode==='active'&&group(j)<2)||(mode==='running'&&group(j)===0)||(mode==='waiting'&&group(j)===1)||(mode==='done'&&group(j)===2)||(mode==='issues'&&group(j)===3);}
 function compare(a,b){const ga=group(a),gb=group(b);return ga-gb||(ga<2?order(a)-order(b):time(b)-time(a))||order(a)-order(b)||String(a.id).localeCompare(String(b.id));}
 const api={matches,compare,time,order,group,select:(jobs,mode)=>jobs.filter(j=>matches(j,mode)).sort(compare),belongs:(j,id)=>(j.source_project||j.project)===id};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.HubQueueView=api;
})(typeof window!=='undefined'?window:globalThis);

(()=>{
 const cfg=window.HUB_CONTROL;if(!cfg)return;
 const base='http://127.0.0.1:18765';
 const style=document.createElement('style');style.textContent='.hub-panel{background:#173b46;border:1px solid #5b9da9;border-radius:12px;padding:16px 20px;margin:18px 0;color:#eefaff}.hub-panel button,.hub-action{border:1px solid #62b9cd;border-radius:7px;background:#193f4a;color:#e9fbff;padding:9px 14px;margin:6px;cursor:pointer;font-size:14px}.hub-action{float:right}.hub-panel[data-alert="true"]{border-color:#f8b75c;background:#423423}.hub-message{white-space:pre-wrap;font-size:14px}header h2{order:0;flex:1}header .hub-action{order:1;float:none}header span{order:2}.hub-panel small{display:block;color:#bfd0d5}';document.head.append(style);
 const panel=document.createElement('section');panel.className='hub-panel';panel.innerHTML='<strong>本机脚本监测</strong><p id="hub-live" role="status">正在检测本机控制服务…</p><button id="hub-stop">停止本地处理</button><button id="hub-resume">恢复处理</button><button id="hub-notify">开启桌面提醒</button><small>停止后禁止后续上传/提交，并中断本地检测、拼接；已发出的网络请求需等待返回。云端已提交任务不会被取消。停止设置在重启后仍保留。</small><p class="hub-message" id="hub-message" role="status"></p>';
 const main=document.querySelector('main')||document.body;const h1=main.querySelector('h1');if(h1)h1.after(panel);else main.prepend(panel);
 const message=t=>document.getElementById('hub-message').textContent=t;
 async function call(action,data={}){
  const r=await fetch(base+'/api/control',{method:'POST',headers:{'Content-Type':'application/json','X-Hub-Token':cfg.token},body:JSON.stringify({action,...data}),signal:AbortSignal.timeout(20000)});const value=await r.json();if(!r.ok)throw Error(value.error||'操作失败');return value;
 }
 let previous=null;
 async function status(){try{const s=await call('status');document.getElementById('hub-live').textContent=s.message;panel.dataset.alert=String(s.active||s.paused);if(previous&&previous.active&&!s.active&&('Notification'in window)&&Notification.permission==='granted')new Notification('RunningHub 本地脚本状态',{body:s.message});previous=s;}catch(e){document.getElementById('hub-live').textContent='控制服务未连接：按钮尚不可用。请启动“RunningHub-Video-Local-Control”任务，或打开本机服务页面。';}}
 document.getElementById('hub-stop').onclick=async()=>{try{await call('stop');message('已保存停止指令。媒体子进程将停止，后续调度不再执行处理；云端任务继续保留。');status();}catch(e){message(e.message);}};
 document.getElementById('hub-resume').onclick=async()=>{try{await call('resume');message('已恢复脚本；仅执行已有授权，未知提交不自动重试。');status();}catch(e){message(e.message);}};
 document.getElementById('hub-notify').onclick=async()=>{if(!('Notification'in window))return message('此浏览器不支持桌面提醒；页面提醒仍可用。');message('桌面提醒权限：'+await Notification.requestPermission());};
 async function ask(text){return new Promise(resolve=>{const d=document.createElement('dialog');d.style.cssText='max-width:580px;background:#18303d;color:#eef8ff;border:1px solid #67b8ca;border-radius:12px;padding:24px';const p=document.createElement('p');p.style.whiteSpace='pre-wrap';p.textContent=text;const yes=document.createElement('button');yes.textContent='确认';const no=document.createElement('button');no.textContent='取消';for(const b of [yes,no]){b.className='hub-action';b.style.float='none';}const finish=v=>{d.close();d.remove();resolve(v);};yes.onclick=()=>finish(true);no.onclick=()=>finish(false);d.oncancel=e=>{e.preventDefault();finish(false);};d.append(p,yes,no);document.body.append(d);d.showModal();});}
 const guide=document.createElement('a');guide.href=base+'/使用指引.html';guide.textContent='网页操作指引：重跑、版本与定稿';panel.append(guide);
 for(const id of ['hub-stop','hub-resume'])document.getElementById(id).hidden=true;
 panel.querySelector('small').textContent='确认生成后自动进入全局队列；最多3并发，先进先出。有名额自动提交，生成结束即补位；下载独立处理。';
 if(cfg.project){
  const fetchButton=document.createElement('button');fetchButton.textContent='手动获取生成结果';panel.append(fetchButton);
  fetchButton.onclick=async()=>{
   fetchButton.disabled=true;message('正在查询已有任务；完成后释放名额、安排下载，并自动提交下一条已批准任务…');
   try{
    await call('fetch_results',{project:cfg.project});
    for(let i=0;i<180;i++){
     await new Promise(r=>setTimeout(r,2000));
     const s=await call('fetch_results_status',{project:cfg.project});
     if(s.state==='DONE'){
      const errors=(s.results||[]).filter(x=>x.error);
      if(errors.length){message('部分任务获取失败：'+errors.map(x=>x.batch+' '+x.error).join('；')+'。可稍后再试。');break;}
      message('查询完成，下载在后台进行，队列已调度；正在刷新…');location.reload();return;
     }
     if(s.state==='BUSY'||s.state==='ERROR'){message(s.message||('获取失败：'+s.error));break;}
     if(i===179)message('接收仍在后台进行，稍后刷新查看；没有重新生成。');
    }
   }catch(e){message('获取未完成：'+e.message);}finally{fetchButton.disabled=false;}
  };
 }
 const queuePanel=document.createElement('section');queuePanel.className='hub-panel';panel.after(queuePanel);
 const labels={WAITING:'排队中',WAITING_CAPACITY:'等待并发名额',WAITING_INSTANCE:'等待实例',UPLOADING:'上传中',SUBMITTING_OUTCOME_UNKNOWN:'提交结果待核对',REJECTED_OR_UNKNOWN:'受理结果待核对',RUNNING:'生成中',QUEUED:'云端排队',CLOUD_SUCCEEDED:'待下载',DOWNLOADING:'下载中',DOWNLOAD_ERROR:'下载待重试',REJECTED:'未受理，需处理',FAILED:'失败',CANCELLED:'取消',NEEDS_REVIEW:'需处理',QUERY_RATE_LIMITED:'查询限频',RETRY_QUERY_OR_DOWNLOAD:'查询待重试',ARCHIVED:'已归档'};
 const view=window.HubQueueView;
 let queueMode=sessionStorage.getItem('hub-queue-mode')||'active',homePage=Number(sessionStorage.getItem('hub-project-page'))||1,lastJobs=[];
 function filters(options,current,change){const bar=document.createElement('div');bar.setAttribute('role','group');bar.setAttribute('aria-label','状态筛选');for(const [value,label] of options){const b=document.createElement('button');b.textContent=label;b.setAttribute('aria-pressed',String(value===current));b.style.background=value===current?'#287385':'#193f4a';b.onclick=()=>change(value);bar.append(b);}return bar;}
 let homeBar;
 if(!cfg.project){for(const card of document.querySelectorAll('article[data-search]')){const href=card.querySelector('h2 a')?.getAttribute('href')||'';card.dataset.project=card.dataset.project||href.split('/')[1];card.dataset.completed=card.dataset.completed||'0';const history=card.querySelector('p strong')?.parentElement;if(history&&!history.dataset.historyLabel){history.prepend('原始批次记录：');history.dataset.historyLabel='true';}}homeBar=document.createElement('nav');homeBar.className='hub-panel';homeBar.id='hub-project-pagination';homeBar.setAttribute('aria-label','项目分页');main.append(homeBar);document.getElementById('filter')?.addEventListener('input',()=>{homePage=1;applyHome();});}
 function paginate(items,requested){const pages=Math.max(1,Math.ceil(items.length/10)),page=Math.min(pages,Math.max(1,Math.floor(Number(requested)||1)));return {items:items.slice((page-1)*10,page*10),page,pages,total:items.length};}

 function applyHome(){
  if(!homeBar)return;
  const query=(document.getElementById('filter')?.value||'').toLowerCase();
  const cards=[...document.querySelectorAll('article[data-project]')].map(card=>{const jobs=lastJobs.filter(j=>view.belongs(j,card.dataset.project));if(!jobs.length)jobs.push({id:card.dataset.project,status:Number(card.dataset.completed)>0?'ARCHIVED':'UNKNOWN',submittedAt:card.dataset.updated});return {card,key:view.select(jobs,'all')[0]};});
  cards.sort((a,b)=>view.compare(a.key,b.key));
  const found=cards.filter(x=>x.card.dataset.search.toLowerCase().includes(query));const result=paginate(found,homePage);homePage=result.page;sessionStorage.setItem('hub-project-page',String(homePage));const shown=new Set(result.items.map(x=>x.card));
  for(const {card,key} of cards){card.hidden=!shown.has(card);let line=card.querySelector('[data-live-project]');if(!line){line=document.createElement('p');line.dataset.liveProject='true';card.querySelector('h2').after(line);}line.textContent=(labels[key.status]||key.status)+' · 队列序号 '+(key.order??'—')+' · 执行时间 '+(key.submittedAt?new Date(key.submittedAt).toLocaleString():'尚未执行');main.append(card);}
  homeBar.replaceChildren();const info=document.createElement('span');info.textContent=`共 ${result.total} 个项目 · 每页10个 · 第 ${result.page} / ${result.pages} 页`;homeBar.append(info);
  const add=(label,page,disabled=false)=>{const b=document.createElement('button');b.textContent=label;b.disabled=disabled;if(page===homePage)b.setAttribute('aria-current','page');b.onclick=()=>{homePage=page;applyHome();document.querySelector('article[data-project]:not([hidden])')?.scrollIntoView({block:'start'});};homeBar.append(b);};
  add('首页',1,homePage===1);add('上一页',homePage-1,homePage===1);
  for(let n=Math.max(2,homePage-2);n<=Math.min(result.pages,Math.max(5,homePage+2));n++)add(String(n),n,n===homePage);
  add('下一页',homePage+1,homePage===result.pages);add('末页',result.pages,homePage===result.pages);
  if(!result.total){const empty=document.createElement('p');empty.textContent='没有匹配的项目，请调整搜索条件。';homeBar.append(empty);}main.append(homeBar);
 }
 applyHome();
 async function queueStatus(){try{
  const data=await call('queue_status');queuePanel.replaceChildren();
  const jobs=data.jobs||[];lastJobs=jobs;applyHome();const waiting=jobs.filter(j=>['WAITING','WAITING_CAPACITY','WAITING_INSTANCE'].includes(j.status)),downloads=jobs.filter(j=>['CLOUD_SUCCEEDED','DOWNLOADING','DOWNLOAD_ERROR'].includes(j.status)),issues=jobs.filter(j=>['FAILED','REJECTED','NEEDS_REVIEW','REJECTED_OR_UNKNOWN','SUBMITTING_OUTCOME_UNKNOWN','DOWNLOAD_ERROR'].includes(j.status));
  const occupied=jobs.filter(j=>['RUNNING','QUEUED','UPLOADING','SUBMITTING_OUTCOME_UNKNOWN','REJECTED_OR_UNKNOWN','QUERY_RATE_LIMITED','RETRY_QUERY_OR_DOWNLOAD'].includes(j.status)).length;
  const heading=document.createElement('h2');heading.textContent=`账户队列：本地占用 ${occupied}/3 · 等待 ${waiting.length} · 下载 ${downloads.length} · 需处理 ${issues.length}`;queuePanel.append(heading);
  const info=document.createElement('p');info.textContent='先进先出；名额释放后自动补位。账户占用：'+(data.account?.occupied??'待查询')+'（'+(data.account?.checkedAt||'尚未查询')+'）。';queuePanel.append(info);
  const refresh=document.createElement('button');refresh.textContent='刷新队列显示';refresh.onclick=queueStatus;queuePanel.append(refresh);queuePanel.append(filters([['active','生成中 / 等待中'],['done','已生成'],['issues','需处理'],['all','全部']],queueMode,value=>{queueMode=value;sessionStorage.setItem('hub-queue-mode',value);queueStatus();}));
  const details=document.createElement('details');details.open=true;const summary=document.createElement('summary');summary.textContent='全局队列与最近记录';details.append(summary);
  const table=document.createElement('table');table.style.cssText='width:100%;font-size:13px;text-align:left;overflow-wrap:anywhere';
  const tr=document.createElement('tr');for(const v of ['排序序号','项目 / 片段','状态','机型 / 任务','执行时间','说明']){const th=document.createElement('th');th.textContent=v;tr.append(th);}table.append(tr);
  const visible=view.select(jobs,queueMode);if(!visible.length){const empty=document.createElement('p');empty.textContent='当前筛选没有任务，点击“全部”可查看历史记录。';details.append(empty);}
  for(const job of visible){const row=document.createElement('tr');for(const value of [job.order??'—',job.title+' / '+job.batch,labels[job.status]||job.status,(job.instanceType||'')+' / '+(job.taskId||'未提交'),job.submittedAt?new Date(job.submittedAt).toLocaleString():'尚未执行',job.blocked||job.reason||'']){const td=document.createElement('td');td.textContent=value;td.style.borderTop='1px solid #46606a';row.append(td);}table.append(row);}
  details.append(table);queuePanel.append(details);
  for(const j of issues){const key='queue-notified:'+j.id+':'+j.status+':'+(j.taskId||'');if(!localStorage.getItem(key)){localStorage.setItem(key,'1');if('Notification' in window&&Notification.permission==='granted')new Notification('视频队列需要处理',{body:j.batch+'：'+(j.reason||labels[j.status])});}}
 }catch(e){queuePanel.textContent='队列读取失败：'+e.message;}}
 queueStatus();setInterval(queueStatus,10000);
 const build=element('small','页面版本：20260923-projectpages3 · 已启用按最新版本获取');panel.append(build);
 function updateTiming(){
  const duration=n=>{n=Math.max(0,Math.floor(n));return Math.floor(n/60)+'分'+n%60+'秒';};
  document.querySelectorAll('[data-version-timing]').forEach(el=>{
   const v=JSON.parse(el.dataset.versionTiming),parts=[];
   if(v.platformGenerationSeconds!=null)parts.push('平台生成耗时：'+duration(Number(v.platformGenerationSeconds)));
   else if(v.submittedAt&&['RUNNING','QUEUED','QUERY_RATE_LIMITED','RETRY_QUERY_OR_DOWNLOAD'].includes(v.status))parts.push('提交后已等待：'+duration((Date.now()-Date.parse(v.submittedAt))/1000)+'（含排队）');
   if(v.lastCheckedAt)parts.push('最后查询：'+new Date(v.lastCheckedAt).toLocaleString());
   if(v.estimatedNextQueryAt){const left=(Date.parse(v.estimatedNextQueryAt)-Date.now())/1000;parts.push(left>0?'预计下次自动查询：'+new Date(v.estimatedNextQueryAt).toLocaleTimeString()+'（约'+duration(left)+'后）':'已到预计查询时间，等待调度；可手动获取');}
   else if(v.status==='ARCHIVED')parts.push('已归档，无需继续查询');
   else if(['FAILED','CANCELLED','REJECTED'].includes(v.status))parts.push('本版本已结束，不再自动查询');
   else if(['CLOUD_SUCCEEDED','DOWNLOADING','DOWNLOAD_ERROR'].includes(v.status))parts.push('云端已完成，正在安排下载');
   el.textContent=parts.join(' · ');
  });
 }
 setInterval(updateTiming,1000);
 const requests=new Map();
 function actionButton(text,fn){const b=document.createElement('button');b.className='hub-action';b.textContent=text;b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){message(e.message);let error=b.nextElementSibling;if(!error||!error.classList.contains('hub-action-error')){error=document.createElement('p');error.className='hub-action-error';error.setAttribute('role','alert');error.style.color='#ffb3a7';b.after(error);}error.textContent='操作未完成：'+e.message;}finally{b.disabled=false;}};return b;}
 for(const article of document.querySelectorAll('article')){
  const title=article.querySelector('h2');if(!title)continue;
  const batch=(cfg.batches||[]).find(n=>title.textContent===n||title.textContent.startsWith(n+' ·'));
  if(!batch)continue;article.dataset.batch=batch;
  const button=actionButton('重新生成片段',()=>generationMenu(batch));title.before(button);
  if(cfg.pipeline==='continuous_speaker'){article.querySelectorAll(':scope > p').forEach(p=>p.hidden=true);continue;}
  for(const link of article.querySelectorAll('a')){if(link.textContent==='打开原片'){link.textContent='打开所在文件夹';link.href='#';link.onclick=async event=>{event.preventDefault();try{await call('folder',{project:cfg.project,batch});message('已打开该任务的归档文件夹。');}catch(e){message(e.message);}};}}
  if(article.querySelector('video')&&![...article.querySelectorAll('a')].some(a=>a.textContent==='打开所在文件夹')){
   const b=actionButton('打开所在文件夹',async()=>{await call('folder',{project:cfg.project,batch});message('已打开该任务的归档文件夹。');});b.style.float='none';article.querySelector('video').after(b);
  }
 }
 if(cfg.project&&cfg.pipeline!=='continuous_speaker')for(const h of document.querySelectorAll('h2'))if(h.textContent==='最终合成'&&h.parentElement.querySelector('video')){const b=actionButton('打开合成文件夹',()=>call('folder',{project:cfg.project,batch:'__final__'}));h.after(b);}

 let versionState=null,versionSignature='',assemblyRequest=null;
 const digital=cfg.pipeline==='continuous_speaker';
 const articleMap=new Map([...document.querySelectorAll('article[data-batch]')].map(a=>[a.dataset.batch,a]));
 const firstArticle=articleMap.values().next().value;
 if(cfg.project&&!digital){const summary=document.querySelector('.summary > strong');if(summary)summary.prepend('首次生成记录：');for(const h of document.querySelectorAll('h2'))if(h.textContent==='异常与复核')h.textContent='首次生成的异常记录';}
 const timelineAnchor=document.createElement('div');if(firstArticle)firstArticle.before(timelineAnchor);
 const finalHeading=[...document.querySelectorAll('h2')].find(h=>h.textContent==='最终合成');
 let finalManager=null;
 function element(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
 function videoPlayer(path){const v=element('video');v.controls=true;v.preload='metadata';v.src=base+'/'+path;v.style.cssText='width:min(100%,340px);height:auto;aspect-ratio:9/16;object-fit:contain;display:block;margin:12px auto;max-height:560px;background:#05080d;border-radius:9px';return v;}
 function btn(text,fn){const b=actionButton(text,fn);b.style.float='none';return b;}
 async function openEditor(batch,sourceVersion){
  const data=await call('edit_load',{project:cfg.project,batch,source_version:sourceVersion});
  const dialog=element('dialog');dialog.className='hub-editor';dialog.style.cssText='width:min(1200px,95vw);max-height:92vh;background:#11232e;color:#edf6fb;border:1px solid #69baca;border-radius:12px;padding:20px;overflow:auto';
  const heading=element('h2','修改后生成 · '+batch);dialog.append(heading);
  const layout=element('div');layout.style.cssText='display:grid;grid-template-columns:minmax(180px,1fr) minmax(300px,2fr);gap:20px';dialog.append(layout);
  const left=element('div'),right=element('div');layout.append(left,right);
  const segment=versionState.segments.find(s=>s.batch===batch);const original=segment.versions.find(v=>v.id===sourceVersion);
  if(original?.video)left.append(videoPlayer(original.video));
  left.append(element('p','基于'+(original?.label||'原版')+'修改；结果保留在当前片段。'),element('p','首图、时长 '+data.duration+' 秒、分辨率与机型（'+data.instanceType+'）沿用来源版本。'));
  const sourceSelect=element('select');sourceSelect.setAttribute('aria-label','来源版本');for(const v of segment.versions){const o=element('option',v.label);o.value=v.id;sourceSelect.append(o);}sourceSelect.value=sourceVersion;left.append(sourceSelect);
  sourceSelect.onchange=async()=>{if(!await ask('切换来源版本？未保存内容会丢失。')){sourceSelect.value=sourceVersion;return;}dialog.close();dialog.remove();await openEditor(batch,sourceSelect.value);};
  const mode=element('select');mode.setAttribute('aria-label','编辑模式');for(const [value,label] of [['simple','普通模式：台词 / 动作 / 声音'],['advanced','高级模式：完整提示词']]){const o=element('option',label);o.value=value;o.disabled=value==='simple'&&!data.simple_supported;mode.append(o);}right.append(mode);
  function area(label,value){const box=element('div'),l=element('label',label),t=element('textarea');t.setAttribute('aria-label',label);t.value=value||'';t.style.cssText='display:block;width:100%;box-sizing:border-box;background:#213b49;color:white;border:1px solid #658798;border-radius:6px;padding:10px;min-height:95px;margin:7px 0 16px';l.append(t);box.append(l);right.append(box);return {box,t};}
  const speech=area('口播台词',data.fields.dialogue),action=area('动作与表情',data.fields.action),voice=area('声音表现',data.fields.voice),advanced=area('完整H3提示词',data.fields.prompt||data.original);advanced.t.style.minHeight='380px';
  const hint=element('p','动作和声音留空：仅替换台词，保留原提示词。填写任一项：重建本段表演描述；留空项使用自然解说默认值，请在差异中核对。多镜头或多角色使用高级模式。');right.append(hint);
  const count=element('p'),feedback=element('p');feedback.setAttribute('role','status');right.append(count,feedback);
  const previewBox=element('details');previewBox.append(element('summary','修改差异与实际提交提示词'));const diff=element('pre'),finalText=element('pre');for(const pre of [diff,finalText])pre.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;background:#0b1820;padding:12px;font-size:13px';previewBox.append(diff,finalText);right.append(previewBox);
  let preview=null,request=null,submitting=false,revision=0,attempted=false;
  const fields=()=>({mode:mode.value,dialogue:speech.t.value,action:action.t.value,voice:voice.t.value,prompt:advanced.t.value});
  function changed(){revision++;preview=null;request=null;confirm.disabled=true;diff.textContent='内容已变化，请重新预览。';finalText.textContent='';const n=(speech.t.value.match(/[\u4e00-\u9fff]/g)||[]).length;count.textContent=mode.value==='simple'?n+'个汉字 · '+data.duration+'秒 · 约'+(n/data.duration).toFixed(1)+'字/秒（估算）':'高级模式以完整提示词为准；普通字段已锁定。';}
  function setMode(){const simple=mode.value==='simple';for(const x of [speech,action,voice]){x.t.disabled=!simple;x.box.hidden=!simple;}advanced.box.hidden=simple;advanced.t.disabled=simple;changed();}
  async function requestPreview(){const rev=revision;const result=await call('edit_preview',{project:cfg.project,batch,source_version:sourceVersion,fields:fields(),fingerprint:data.fingerprint});if(rev!==revision)throw Error('编辑内容已变化，请重新预览。');preview=result;request=crypto.randomUUID().replaceAll('-','');diff.textContent=result.diff;finalText.textContent=result.prompt;previewBox.open=true;feedback.textContent=result.warnings.join(' ');confirm.disabled=false;return result;}
  const buttons=element('div');right.append(buttons);
  const close=btn('取消',()=>{if(submitting)return;dialog.close();dialog.remove();});
  const save=btn('保存草稿',async()=>{try{await call('edit_save',{project:cfg.project,batch,source_version:sourceVersion,fields:fields(),fingerprint:data.fingerprint});feedback.textContent='草稿已保存；未提交API，也未创建新版本。';}catch(e){feedback.textContent=e.message;}});
  const inspect=btn('预览修改',async()=>{try{await requestPreview();}catch(e){feedback.textContent=e.message;}});
  const confirm=btn('确认并生成新版本',async()=>{if(!preview||submitting)return;const frozen=preview,id=request;if(!await ask('确认将 '+batch+' 的本次预览生成一个新的付费版本？\n原版和定稿保留，结果仍在当前片段。'))return;if(preview!==frozen)return;submitting=true;attempted=true;for(const el of [mode,sourceSelect,speech.t,action.t,voice.t,advanced.t,save,inspect,confirm])el.disabled=true;try{await call('edit_generate',{project:cfg.project,batch,preview_id:frozen.preview_id,request_id:id,confirmed:true});dialog.close();dialog.remove();message('修改版已登记在原片段，由脚本执行。');await refreshVersions(true);}catch(e){feedback.textContent='登记结果：'+e.message+'。请保留此面板，重复确认使用同一请求ID。';}finally{submitting=false;confirm.disabled=false;}});
  buttons.append(close,save,inspect,confirm);for(const x of [speech,action,voice,advanced])x.t.oninput=changed;
  mode.value=data.fields.mode;let previousMode=mode.value;mode.onchange=async()=>{const target=mode.value;mode.value=previousMode;try{if(target==='advanced'){const compiled=await requestPreview();advanced.t.value=compiled.prompt;}else if(!await ask('返回普通模式将使用此前的普通字段，放弃高级提示词修改，是否继续？'))return;mode.value=target;previousMode=target;setMode();}catch(e){feedback.textContent=e.message;}};setMode();
    const responsive=element('style');responsive.textContent='@media(max-width:700px){.hub-editor>div{grid-template-columns:1fr!important}}';dialog.append(responsive);
  dialog.oncancel=e=>{e.preventDefault();if(!submitting){dialog.close();dialog.remove();}};document.body.append(dialog);dialog.showModal();
 }
 async function generationMenu(batch){
  if(!versionState)return message('版本仍在加载，请稍后重试。');const sourceVersion=previewVersions.get(batch);
  const menu=element('dialog');menu.style.cssText='background:#18303d;color:white;border:1px solid #67b8ca;border-radius:12px;padding:24px';menu.append(element('h3',batch+' · 重新生成'));
  const finish=()=>{menu.close();menu.remove();};
  menu.append(btn('原稿重抽',async()=>{finish();if(!await ask('沿用当前预览版本的素材和提示词，更换随机种子，新增一个付费版本？'))return;const key=batch+':'+sourceVersion;let id=requests.get(key);if(!id){id=crypto.randomUUID().replaceAll('-','');requests.set(key,id);}await call('reroll',{project:cfg.project,batch,source_version:sourceVersion,request_id:id,confirmed:true});requests.delete(key);message('重抽已登记在原片段。');await refreshVersions(true);}),btn('修改后生成',async()=>{finish();await openEditor(batch,sourceVersion);}),btn('取消',finish));menu.oncancel=e=>{e.preventDefault();finish();};document.body.append(menu);menu.showModal();
 }

 const previewVersions=new Map(),latestVersions=new Map();
 function renderVersions(state){
  versionState=state;let anchor=timelineAnchor;
  let summary=document.getElementById('version-progress');if(!summary){summary=element('p');summary.id='version-progress';panel.append(summary);}
  const latest=state.segments.map(s=>s.versions.at(-1));const success=latest.filter(v=>v?.ready).length;const failed=latest.filter(v=>['FAILED','CANCELLED'].includes(v?.status)).length;
  summary.textContent='各片段最新版本：'+(success+failed)+' / '+latest.length+' 已结束 · 成功 '+success+' · 失败 '+failed+' · 处理中 '+(latest.length-success-failed);

  for(const segment of state.segments){
   const article=articleMap.get(segment.batch);if(!article)continue;anchor.after(article);anchor=article;
   let manager=article.querySelector('.version-manager');
   if(!manager){
    article.querySelectorAll(':scope > video,:scope > p,:scope > section[role=alert]').forEach(v=>v.remove());
    const columns=article.querySelector(':scope > .columns');
    if(columns){const reference=columns.firstElementChild;const materials=element('details');materials.append(element('summary','参考素材与提示词'));if(reference)materials.append(reference);columns.replaceWith(materials);}
    manager=element('div');manager.className='version-manager';const details=article.querySelector('details');if(details)details.before(manager);else article.append(manager);
   }
   manager.replaceChildren();
   const newest=segment.versions.at(-1)?.id;
   if(latestVersions.get(segment.batch)!==newest){previewVersions.set(segment.batch,newest);latestVersions.set(segment.batch,newest);}
   const selected=segment.versions.find(v=>v.id===previewVersions.get(segment.batch))||segment.versions.at(-1);
   const finalized=segment.versions.find(v=>segment.finalized&&v.id===segment.selected);
   const versionName=v=>'版本'+v.label.replace(/^V/,'');

   const tabs=element('div');tabs.setAttribute('role','group');tabs.setAttribute('aria-label',segment.batch+' 版本选择');tabs.style.cssText='display:flex;flex-wrap:wrap;gap:8px;margin:12px 0';
   for(const version of segment.versions){
    const tab=btn(versionName(version)+(finalized?.id===version.id?' · 定稿':'')+(version.review?' · 未通过':''),()=>{previewVersions.set(segment.batch,version.id);renderVersions(versionState);});
    tab.setAttribute('aria-pressed',String(selected?.id===version.id));
    tab.style.cssText+=';margin:0;border:1px solid #62b9cd;border-radius:8px;padding:10px 16px;color:#eefaff;background:'+(selected?.id===version.id?'#29687a':'#18313e');tabs.append(tab);
   }
   manager.append(tabs);

   if(selected){

    if(selected.video)manager.append(videoPlayer(selected.video));
    else manager.append(element('p',['FAILED','CANCELLED'].includes(selected.status)?'本版本运行失败，已结束。':'本版本正在等待或生成中，完成后可预览与定稿。'));
    const statusNames={WAITING_CAPACITY:'等待并发名额',WAITING_INSTANCE:'等待可用实例',QUERY_RATE_LIMITED:'查询限频 · 等待重查',REJECTED_OR_UNKNOWN:'提交结果待核对',SUBMITTING_OUTCOME_UNKNOWN:'提交结果待核对',NEEDS_REVIEW:'需要人工核对',ARCHIVED:'已下载 · 待审稿',FAILED:'失败 · 已结束',CANCELLED:'已取消',RUNNING:'生成中',WAITING:'等待脚本',QUEUED:'排队中'};
    const latest=segment.versions.at(-1);const headerStatus=article.querySelector('header span');if(headerStatus)headerStatus.textContent='最新'+versionName(latest)+'：'+(statusNames[latest.status]||latest.status);
    manager.append(element('small',versionName(selected)+' · '+(statusNames[selected.status]||selected.status)+' · '+(selected.instanceType||'平台默认')+(selected.taskId?' · 任务 '+selected.taskId:'')));
    const timingLine=element('p');timingLine.dataset.versionTiming=JSON.stringify(selected);manager.append(timingLine);updateTiming();
    const fetchLatest=btn('获取最新'+versionName(latest)+'结果',async()=>{
     message('正在获取 '+segment.batch+' / '+versionName(latest)+' · 任务 '+(latest.taskId||'未提交'));
     if(!latest.taskId){message('该版本尚未提交，在队列中等待；不会重复创建任务。');return;}
     if(latest.ready){previewVersions.set(segment.batch,latest.id);await refreshVersions(true);message('最新'+versionName(latest)+'已下载，已切换到该版本。');return;}
     await call('fetch_results',{project:latest.id});
     for(let i=0;i<90;i++){
      await new Promise(r=>setTimeout(r,2000));const result=await call('fetch_results_status',{project:latest.id});
      if(result.state==='DONE'){previewVersions.set(segment.batch,latest.id);await refreshVersions(true);message('最新版本查询完成；已完成的视频在后台接收，页面自动更新。');return;}
      if(['ERROR','BUSY'].includes(result.state))throw Error(result.message||result.error||'中心正忙，请稍后再试');
     }
     message('查询仍在后台进行，页面会继续更新最新版本。');
    });manager.append(fetchLatest);
    if(selected.nextSubmitAt||selected.nextQueryAt)manager.append(element('p','下次尝试不早于：'+(selected.nextSubmitAt||selected.nextQueryAt)+'；脚本按调度执行，仍使用当前版本。'));
    if(selected.failure?.summary||['FAILED','CANCELLED'].includes(selected.status)){
     const failure=element('section');failure.setAttribute('role','alert');failure.style.cssText='border:1px solid #ef8c7c;padding:14px;border-radius:8px;margin:12px 0';
     failure.append(element('strong',selected.failure?.summary||selected.reason||'运行失败'),element('p',selected.failure?.advice||''));
     const detail=element('details');detail.append(element('summary','展开完整失败原因 / 错误码 / 节点'),element('pre',selected.failure?.detail||selected.reason||'平台未提供详情'));failure.append(detail);manager.append(failure);
     if(['FAILED','CANCELLED'].includes(selected.status))manager.append(btn('使用 Plus 重跑（48GB）',async()=>{
      if(!await ask('使用 Plus（48GB）重跑 '+segment.batch+' / '+versionName(selected)+'？\n保留本版本素材、提示词、种子和参数，新增版本保留在当前片段。产生一次平台生成费用；Plus 不保证成功。'))return;
      const key=segment.batch+':plus:'+selected.id;let id=requests.get(key);if(!id){id=crypto.randomUUID().replaceAll('-','');requests.set(key,id);}
      await call('retry_plus',{project:cfg.project,batch:segment.batch,source_version:selected.id,request_id:id,confirmed:true});
      message('Plus 新版本已登记在当前片段，由脚本执行。');await refreshVersions(true);
     }));
    }
    const finalize=btn(finalized?.id===selected.id?'此版本已定稿':'将'+versionName(selected)+'定稿',async()=>{
     if(!await ask('确认 '+segment.batch+' / '+versionName(selected)+' 审稿通过，并作为本段唯一定稿用于拼接？'))return;
     await call('choose_version',{project:cfg.project,batch:segment.batch,version:selected.id,confirmed:true});message('本段已定稿；拼接将使用'+versionName(selected)+'，其他片段及台词顺序保持不变。');await refreshVersions(true);
    });finalize.disabled=!selected.ready||finalized?.id===selected.id;manager.append(finalize);
    if(selected.ready){
     manager.append(btn('打开所在文件夹',()=>call('folder',{project:selected.id,batch:segment.batch})));
     manager.append(btn('审稿不通过',async()=>{if(!await ask('将 '+segment.batch+' / '+versionName(selected)+' 标记为审稿不通过？'))return;await call('reject_version',{project:cfg.project,batch:segment.batch,version:selected.id,confirmed:true});await refreshVersions(true);}));
    }
   }
   if(segment.finalized)manager.append(btn('撤回定稿',async()=>{if(!await ask('撤回本段定稿，重新进入审稿？'))return;await call('choose_version',{project:cfg.project,batch:segment.batch,version:'latest',confirmed:true});await refreshVersions(true);}));

  }
  if(digital&&finalHeading){
   if(!finalManager){const parent=finalHeading.parentElement;[...parent.children].filter(x=>x!==finalHeading).forEach(x=>x.remove());finalManager=element('div');parent.append(finalManager);}
   finalManager.replaceChildren();
   const composition=state.segments.map(x=>x.batch+' / '+((x.versions.find(v=>v.id===x.selected)?.label||'待完成')+(x.finalized?' 手动定稿':' 默认选用'))).join(' → ');
   finalManager.append(element('p','定稿拼接清单：'+composition));
   finalManager.append(element('p',!state.assembly_ready?'部分片段没有可用版本，暂不能拼接。':state.needs_assembly?'拼接素材已变化：使用手动定稿；未定稿的默认使用最新可用版本。':state.final_approved?'成片审稿已通过。':'现有成片与各段定稿一致（台词顺序固定），可以直接通过成片审稿，无需重新拼接。'));
   const assembleButton=btn(state.needs_assembly?'按选用版本重新拼接':'素材未变化，无需重新拼接',async()=>{
    if(!await ask('使用以下版本重新拼接？未手动定稿的使用默认版本。\n'+composition+'\n仅本地拼接，不产生生成费用；旧合成保留。\n重抽片段与相邻段可能有接缝差异，请观看检查。'))return;
    assemblyRequest=assemblyRequest||crypto.randomUUID().replaceAll('-','');
    const result=await call('assemble',{project:cfg.project,request_id:assemblyRequest,confirmed:true,expected:state.fingerprint});assemblyRequest=null;message(result.unchanged?'素材未变化，已跳过拼接。':result.duplicate?'相同素材已在拼接队列中。':'人工拼接已排队，由本地脚本执行。');await refreshVersions(true);
   });assembleButton.disabled=!state.assembly_ready||!state.needs_assembly;finalManager.append(assembleButton);
   if(state.current_final){const passButton=btn('成片审稿通过（不重新拼接）',async()=>{if(!await ask('确认当前成片审稿通过？不会重新拼接或生成。'))return;await call('approve_final',{project:cfg.project,assembly:state.current_final.id,confirmed:true});message('成片审稿已通过。');await refreshVersions(true);});passButton.disabled=!state.assembly_ready||state.needs_assembly||state.final_approved;finalManager.append(passButton);}
   for(const assembly of state.assemblies.filter(a=>!a.video))finalManager.append(element('p',assembly.label+'：'+assembly.state+(assembly.reason?' · '+assembly.reason:'')));
   if(state.current_final){finalManager.append(element('p','当前合成：'+state.current_final.label),videoPlayer(state.current_final.video));finalManager.append(btn('打开合成文件夹',()=>call('assembly_folder',{project:cfg.project,assembly:state.current_final.id})));}
   const old=element('details');old.append(element('summary','浏览历史合成'));
   for(const a of [...state.assemblies].reverse().filter(a=>a.video&&a.id!==state.current_final?.id)){old.append(element('p',a.label));const v=videoPlayer(a.video);v.preload='none';old.append(v);}
   finalManager.append(old);
  }
 }
 async function refreshVersions(force=false){if(!cfg.project)return;try{const state=await call('versions',{project:cfg.project});const signature=JSON.stringify(state);if(signature===versionSignature&&!force)return;if(!force&&[...document.querySelectorAll('video')].some(v=>!v.paused&&!v.ended)){message('版本或合成状态已更新；暂停播放后将刷新预览。');return;}versionSignature=signature;renderVersions(state);}catch(e){message('版本状态：'+e.message);}}
 if(cfg.project){refreshVersions();setInterval(()=>refreshVersions(),5000);}

 status();setInterval(status,5000);
})();
