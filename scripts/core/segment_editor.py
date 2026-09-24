"""Version-scoped drafts, deterministic prompt compilation and immutable preview snapshots."""
import re,hashlib,json,difflib,secrets
import local_control as lc
FIELDS=['subject_definitions','summary','retention_analysis','detailed_description','overall_soundscape','non_diegetic_music']
def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def source(root,pid,batch,version):
 from control_server import batch_path
 entry,p,_=batch_path(root,pid,batch);e,_,d=batch_path(root,version or pid,batch)
 if e['id']!=pid and (e.get('source_project')!=pid or e.get('source_batch')!=batch):raise ValueError('来源版本不属于当前片段')
 m=lc.read(d/'manifest.json');text=(d/m['prompt']).read_text(encoding='utf-8-sig');g=lc.read(d/m['workflow'])
 asset_hashes=[]
 for rel in m.get('reference_images',[])+m.get('reference_audio',[]):
  asset=(d/rel).resolve()
  if not asset.is_relative_to(d) or not asset.is_file():raise ValueError('参考素材缺失或路径无效')
  asset_hashes.append(hashlib.sha256(asset.read_bytes()).hexdigest())
 fingerprint=digest(json.dumps(asset_hashes)+text+json.dumps(g,sort_keys=True,ensure_ascii=False)+json.dumps(m,sort_keys=True,ensure_ascii=False))
 return p,d,m,text,g,fingerprint

def split(text):
 matches=list(re.finditer(r'(?m)^('+'|'.join(FIELDS)+r'):\s*',text))
 if [x[1] for x in matches]!=FIELDS:raise ValueError('提示词必须保留六个H3字段及顺序；此来源请先整理格式')
 return {m[1]:text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)].strip() for i,m in enumerate(matches)}
def dialogue(text):return re.findall(r'<d>\s*\[([^\]]+)\]\s*(.*?)</d>',text,re.S)
def load(root,pid,batch,version):
 p,d,m,text,g,fp=source(root,pid,batch,version);lines=dialogue(text);simple=len(lines)<=1 and len(set(re.findall(r'\[Shot (\d+)\]',split(text)['detailed_description'])))<=1
 fields={'mode':'simple' if simple else 'advanced','dialogue':lines[0][1] if lines else '', 'action':'','voice':'','prompt':text}
 if m.get('edit_fields',{}).get('mode')=='simple':fields.update({k:m['edit_fields'].get(k,'') for k in ['action','voice']})
 saved=lc.read(p/batch/'edit_drafts'/((version or pid)+'.json'),{})
 return {'source_version':version or pid,'fingerprint':fp,'duration':m.get('duration',15),'fields':saved.get('fields',fields) if saved.get('fingerprint')==fp else fields,'original':text,'simple_supported':simple,'draft_saved':saved.get('fingerprint')==fp,'references':m.get('reference_images',[]),'instanceType':m.get('instanceType') or '平台默认'}
def compile_edit(original,m,fields):
 mode=fields.get('mode');parts=split(original);lines=dialogue(original)
 if mode=='advanced':text=fields.get('prompt','').strip();split(text)
 elif mode=='simple':
  if len(lines)>1 or len(set(re.findall(r'\[Shot (\d+)\]',parts['detailed_description'])))>1:raise ValueError('多角色/多镜头请使用高级模式')
  line=fields.get('dialogue','').strip();action=fields.get('action','').strip();voice=fields.get('voice','').strip()
  if any(x in line+action+voice for x in ['<d>','</d>','[Shot','subject_definitions:']):raise ValueError('普通字段不能包含结构标签')
  text=original
  if lines:
   text=re.sub(r'<d>.*?</d>',lambda _:f'<d>[{lines[0][0]}] {line}</d>' if line else '',text,flags=re.S)
  elif line:raise ValueError('原片段没有发声者绑定，请用高级模式添加角色与台词')
  if action or voice:
   if not lines:raise ValueError('无台词片段的动作修改请用高级模式')
   subjects=re.findall(r'<Subject \d+>\s*\(S\d+\)',parts['detailed_description']);speaker=subjects[0] if subjects else '<Subject 1> (S1)'
   parts['summary']='[keyframe completion + reference generation] Create one '+str(m.get('duration',15))+'-second segment following the supplied visual references and the revised performance below.'
   parts['detailed_description']='[Shot 1] Begin from <Picture 1>. Preserve the referenced identity, costume, room, framing, light direction, skin hue and white balance. Static camera, no new props or scene changes.\n'+(action or 'Maintain a restrained direct-to-camera presentation, natural blinking and minimal gestures.')
   if line:
    parts['detailed_description']+='\n'+(voice or 'Use a clear warm adult Mandarin voice, natural emphasis and steady vocal identity.')+'\n'+speaker+' says: <d>['+lines[0][0]+'] '+line+'</d>\nComplete the exact line within '+str(m.get('duration',15))+' seconds, without additional words. Synchronize lips with speech.'
   else:parts['detailed_description']+=' No spoken words.'
   parts['detailed_description']+=' No subtitles. Preserve stable skin color and lighting throughout.'
   text='\n\n'.join(k+':\n'+parts[k] for k in FIELDS)+'\n'
  count=len(re.findall(r'[\u4e00-\u9fff]',line));text=re.sub(r'\b(?:\d+|seventy|eighty|ninety)(?:-Chinese)?-character',str(count)+'-character',text)
 else:raise ValueError('未知编辑模式')
 if not text or len(text)>40000:raise ValueError('提示词为空或过长')
 for kind in ['Picture','Audio','Video']:
  if set(re.findall('<'+kind+r' \d+>',text))!=set(re.findall('<'+kind+r' \d+>',original)):raise ValueError('素材标签必须与原版相同；新增素材需要单独适配')
 if text.count('<d>')!=text.count('</d>') or text.count('<d>')!=len(dialogue(text)):raise ValueError('台词标签不完整')
 words=dialogue(text);count=sum(len(re.findall(r'[\u4e00-\u9fff]',x[1])) for x in words)
 warnings=['请复核最终提示词是否存在动作、声音或时间冲突；此检查不能代替人工审稿。']
 if count/float(m.get('duration',15))>6:warnings.append('超过每秒6个汉字，请检查是否能在设定时长内说完整。')
 return text,'\n'.join(x[1] for x in words),warnings,count

def prepare(root,pid,batch,version,fields,fingerprint,preview=False):
 p,d,m,original,g,fp=source(root,pid,batch,version)
 if fp!=fingerprint:raise ValueError('来源已变化，请重新打开编辑器')
 text,line,warnings,count=compile_edit(original,m,fields)
 snap={'source_version':version or pid,'fingerprint':fp,'fields':fields,'prompt':text,'dialogue':line,'warnings':warnings,'count':count,'duration':m.get('duration',15),'createdAt':lc.now()}
 if preview:
  token=secrets.token_hex(16);snap['preview_id']=token;lc.save(p/batch/'edit_previews'/(token+'.json'),snap)
  snap['diff']=''.join(difflib.unified_diff(original.splitlines(True),text.splitlines(True),fromfile='来源版本',tofile='拟生成版本')) or '内容未变化（仅重新抽取随机种子）'
 else:lc.save(p/batch/'edit_drafts'/((version or pid)+'.json'),snap)
 return snap

def snapshot(root,pid,batch,token):
 from control_server import batch_path
 if not re.fullmatch('[a-f0-9]{32}',token or ''):raise ValueError('请先预览修改')
 _,p,_=batch_path(root,pid,batch);snap=lc.read(p/batch/'edit_previews'/(token+'.json'),{})
 if not snap:raise ValueError('修改预览不存在')
 _,_,m,original,g,fp=source(root,pid,batch,snap['source_version'])
 if fp!=snap['fingerprint']:raise ValueError('来源已变化，必须重新预览')
 text,line,_,_=compile_edit(original,m,snap['fields'])
 if text!=snap['prompt']:raise ValueError('预览内容校验失败')
 return snap
