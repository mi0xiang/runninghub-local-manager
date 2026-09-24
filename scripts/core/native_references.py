"""Prepare native reference switches BEFORE approval, never mutate approved graphs."""
import copy
AUDIO=['48','14','15'];VIDEO=['27','25','26']
def video_field(node):
 field={'VHS_LoadVideo':'video','LoadVideo':'file'}.get(node.get('class_type'))
 if not field or field not in node.get('inputs',{}):raise ValueError('Unsupported video loader/field')
 return field
def configure(template,audio_files,video_files):
 for files in (audio_files,video_files):
  if len(files)>3 or any(not isinstance(x,str) or x.strip().lower() in ('','none','null') for x in files):raise ValueError('Supply 0-3 real asset paths per reference type')
 for node in AUDIO:
  if template.get(node,{}).get('class_type')!='LoadAudio':raise ValueError('Full native audio template required')
 for node in VIDEO:
  if template.get(node,{}).get('class_type')!='VHS_LoadVideo':raise ValueError('Full native VHS template required')
 g=copy.deepcopy(template);inputs=g['265']['inputs']
 for key in list(inputs):
  if key.startswith(('ref_audios.','ref_videos.')):del inputs[key]
 for ids,files,prefix,field in [(AUDIO,audio_files,'ref_audios.ref_audio_','audio'),(VIDEO,video_files,'ref_videos.ref_video_','video')]:
  for i,node in enumerate(ids):
   if i<len(files):g[node]['inputs'][field]=files[i];inputs[prefix+str(i)]=[node,0]
   else:del g[node]
 return g,{'reference_audio':list(audio_files),'audio_node_ids':AUDIO[:len(audio_files)],'reference_videos':list(video_files),'video_node_ids':VIDEO[:len(video_files)],'reference_switch_schema':'native_20260924'}
def verify(graph,meta):
 if meta.get('reference_switch_schema')!='native_20260924':return
 inputs=graph['265']['inputs']
 for ids,field,prefix in [(AUDIO,'audio','ref_audios.ref_audio_'),(VIDEO,'videos','ref_videos.ref_video_')]:
  files=meta.get('reference_'+field,[]);mapped=meta.get('audio_node_ids' if field=='audio' else 'video_node_ids',[])
  if len(files)>3 or mapped!=ids[:len(files)]:raise ValueError('Native reference slot mapping mismatch')
  expected={prefix+str(i):[node,0] for i,node in enumerate(mapped)}
  actual={k:v for k,v in inputs.items() if k.startswith(prefix)}
  if expected!=actual or any(node in graph for node in ids[len(files):]):raise ValueError('Unused reference branch must be disabled before approval')
