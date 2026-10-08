"""Validate existing local originals; never query, download or submit cloud work."""
import hashlib
import json
import math
import subprocess
from pathlib import Path

def sha256(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):result.update(block)
    return result.hexdigest()

def probe_media(path):
    import portable_runtime
    result=subprocess.run([portable_runtime.tool('ffprobe'),'-v','error','-show_streams',
                           '-show_format','-of','json',str(path)],capture_output=True,
                          timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('Media probe failed')
    return json.loads(result.stdout)

def verify_archive(batch, task_id, probe=probe_media):
    batch=Path(batch).resolve()
    result={'valid':False,'taskId':str(task_id),'files':[],'reason':'','issue':None}
    issue='MISSING_OR_CORRUPT'
    try:
        if not task_id or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for ch in str(task_id)):
            raise ValueError('Invalid task identity')
        target=batch/'results'/('task-'+str(task_id))
        manifest=json.loads((target/'manifest.json').read_text(encoding='utf-8-sig'))
        if str(manifest.get('taskId'))!=str(task_id) or not manifest.get('files'):
            raise ValueError('Archive identity or file list is invalid')
        for item in manifest['files']:
            rel=Path(item['name']);path=(target/rel).resolve()
            if rel.is_absolute() or not path.is_relative_to(target.resolve()) or not path.is_file():
                raise ValueError('Archive media is missing or outside task directory')
            size=path.stat().st_size
            if size<=0 or size!=item['bytes']:raise ValueError('Archive media length changed')
            if sha256(path)!=item['sha256']:raise ValueError('Archive media hash changed')
            issue='PROBE_UNAVAILABLE'
            info=probe(path)
            issue='INVALID_MEDIA'
            duration=float(info.get('format',{}).get('duration',0))
            kind='audio' if path.suffix.lower() in ('.mp3','.wav','.flac','.ogg','.m4a') else 'video'
            if not math.isfinite(duration) or duration<=0 or not any(x.get('codec_type')==kind for x in info.get('streams',[])):
                raise ValueError('Archive media has no valid expected stream')
            result['files'].append(dict(name=item['name'],bytes=size,sha256=item['sha256'],duration=duration))
            issue='MISSING_OR_CORRUPT'
        result['valid']=True
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):
        result['issue']=issue
        result['reason']='原件缺失、损坏、身份不符或媒体校验不可用；保留原任务，需恢复核对'
    return result
