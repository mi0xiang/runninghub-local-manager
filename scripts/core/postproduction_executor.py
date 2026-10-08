"""Deterministic assembly of an explicit frozen READY local postproduction plan.

Preserves original files. Writes assembly evidence only, never content acceptance,
human confirmation, upload, generation or a guessed presentation/result binding.
"""
import datetime, hashlib, json, math, os, re, subprocess
from pathlib import Path
import durable_store as store
import portable_runtime
from archive_integrity import probe_media, sha256
from postproduction_records import local_file, validate_plan

def _command(args,timeout=900):
    try:
        result=subprocess.run([str(a) for a in args],capture_output=True,timeout=timeout,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired:raise TimeoutError('Local assembly command exceeded finite limit') from None
    if result.returncode:raise ValueError('Local media command failed; inspect frozen inputs, no automatic creative repair')
    return result.stdout
def _timestamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def assemble(folder):
    folder=Path(folder).resolve()
    with store.process_lock(folder/'project-runner.process.lock'):
        path=folder/'postproduction.json';before=store.digest(path);record=store.read(path,{})
        spec=record.get('plan',{})
        checked=validate_plan(folder,spec)
        if checked['state']!='READY':raise ValueError('Frozen postproduction/content/audio prerequisites are not READY')
        version=spec['version']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}',version):raise ValueError('Safe explicit output version required')
        for evidence in spec.get('quality_review',{}).get('evidence',[]):
            if isinstance(evidence,str):local_file(folder,evidence)
            else:raise ValueError('Project-local quality evidence paths required')
        plan=store.read(folder/'execution-plan.json',{})
        if plan:
            expected=[s['segment_id'] for s in plan['segments']]
            actual=[s.get('segment_id') for s in spec['segments']]
            if actual!=expected:raise ValueError('Assembly order/coverage differs from whole-film timeline')
        infos=[];duration=0
        for segment in spec['segments']:
            media=local_file(folder,segment['file']);info=probe_media(media)
            if not any(s.get('codec_type')=='video' for s in info.get('streams',[])):raise ValueError('Video input required')
            start=float(segment['start']);end=float(segment['end'])
            if end>float(info['format']['duration'])+0.03:raise ValueError('Trim exceeds actual input duration')
            # Explicit task binding is verified when this project has an execution plan.
            if plan:
                task=segment.get('taskId')
                seg=next(s for s in plan['segments'] if s['segment_id']==segment['segment_id'])
                if seg.get('kind','generation')=='generation':
                    original=store.read(folder/segment['segment_id']/'task_state.json',{})
                    if not task or task!=original.get('taskId') or original.get('status') not in ('ARCHIVED','DOWNLOADED'):
                        raise ValueError('Assembly requires the exact archived original task')
                    archive=folder/segment['segment_id']/'results'/('task-'+task)
                    if not media.is_relative_to(archive):raise ValueError('Input is outside original task archive')
                elif segment['file']!=seg['file'] or segment['sha256']!=seg['sha256']:
                    raise ValueError('Reused local media differs from whole-film plan')
                bounds=seg.get('global_range')
                if bounds and abs((end-start)-(bounds[1]-bounds[0]))>0.15:
                    raise ValueError('Trim duration differs from frozen whole-film timeline')
            infos.append(info);duration+=end-start
        signatures=[]
        for info in infos:
            video=next(s for s in info['streams'] if s['codec_type']=='video')
            signatures.append((video['width'],video['height'],video.get('r_frame_rate')))
        if len(set(signatures))!=1:raise ValueError('Different formats require an explicit approved normalization plan')
        audio=spec['audio'];mode=audio['mode']
        if mode=='generated' and not all(any(s.get('codec_type')=='audio' for s in i['streams']) for i in infos):
            raise ValueError('Generated audio missing; select approved separate audio nodes explicitly')
        external=None
        if mode in ('source','bgm'):
            for evidence in audio['authorization_evidence']:local_file(folder,evidence)
            external=local_file(folder,audio['file']);external_info=probe_media(external)
            if not any(s.get('codec_type')=='audio' for s in external_info.get('streams',[])):raise ValueError('Approved audio stream missing')
            audio_start=float(audio.get('start',0))
            if not math.isfinite(audio_start) or audio_start<0:raise ValueError('Explicit valid audio start required')
            if audio.get('loop') is not True and float(external_info['format']['duration'])-audio_start<duration-0.03:
                raise ValueError('Approved audio is too short from selected offset; no automatic looping')
        fingerprint=hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        state_path=folder/'assembly.json';state_before=store.digest(state_path);previous=store.read(state_path,{})
        output=folder/'review'/version/'assembled.mp4'
        if previous.get('fingerprint')==fingerprint and previous.get('state')=='ASSEMBLED' and output.is_file() and sha256(output)==previous.get('sha256'):
            # Already-verified identical output; no re-encoding or revision churn.
            return previous
        if output.exists():raise ValueError('Existing output version differs; retain it and use a new frozen version')
        output.parent.mkdir(parents=True,exist_ok=True);temporary=output.with_name('assembled.part.mp4')
        store.save(state_path,{'schema_version':1,'state':'ASSEMBLING','fingerprint':fingerprint,
                              'input_revision':record['revision'],'version':version,'started_at':_timestamp()},
                   expected_digest=state_before,compare=True)
        assembly_digest=store.digest(state_path)
        args=[portable_runtime.tool('ffmpeg'),'-hide_banner','-v','error','-y']
        for segment in spec['segments']:args+=['-i',str(local_file(folder,segment['file']))]
        if mode in ('source','bgm'):
            if audio.get('loop') is True:args+=['-stream_loop','-1']
            args+=['-i',str(external)]
        filters=[];labels=[]
        for n,segment in enumerate(spec['segments']):
            start,end=float(segment['start']),float(segment['end'])
            filters.append(f'[{n}:v:0]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{n}]')
            labels.append(f'[v{n}]')
            if mode=='generated':
                filters.append(f'[{n}:a:0]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{n}]')
                labels.append(f'[a{n}]')
        joined=''.join(labels)+f'concat=n={len(spec["segments"])}:v=1:a={1 if mode=="generated" else 0}[v]'
        if mode=='generated':joined+='[a]'
        filters.append(joined)
        if mode in ('source','bgm'):
            filters.append(f'[{len(spec["segments"])}:a:0]atrim=start={float(audio.get("start",0))}:duration={duration},asetpts=PTS-STARTPTS[a]')
        args+=['-filter_complex',';'.join(filters),'-map','[v]']
        if mode!='none':args+=['-map','[a]','-c:a','aac','-b:a','192k']
        args+=['-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-t',str(duration),'-movflags','+faststart',str(temporary)]
        try:
            _command(args)
            info=probe_media(temporary);actual=float(info['format']['duration'])
            if not math.isfinite(actual) or abs(actual-duration)>0.15:raise ValueError('Assembled duration differs from frozen trims')
            has_audio=any(s.get('codec_type')=='audio' for s in info['streams'])
            if has_audio!=(mode!='none'):raise ValueError('Assembled audio differs from explicit audio mode')
            _command([portable_runtime.tool('ffmpeg'),'-v','error','-xerror','-i',str(temporary),'-map','0:v?','-map','0:a?','-f','null','NUL'],timeout=300)
            if store.digest(path)!=before:raise RuntimeError('Frozen postproduction revision changed during assembly')
            validate_plan(folder,spec)  # Recheck actual hashes after media processing.
            digest=sha256(temporary);size=temporary.stat().st_size
            os.replace(temporary,output)
            value={'schema_version':1,'state':'ASSEMBLED','version':version,'input_revision':record['revision'],
                   'fingerprint':fingerprint,'result_video':output.relative_to(folder).as_posix(),
                   'sha256':digest,'bytes':size,'duration_seconds':actual,'expected_duration_seconds':duration,
                   'technical':{'media':True,'decode':True,'evidence':['assembly.json']},
                   'content_accepted':False,'human_confirmation':False,'updated_at':_timestamp()}
            store.save(state_path,value,expected_digest=assembly_digest,compare=True)
            return value
        except Exception as exc:
            store.save(state_path,{'schema_version':1,'state':'BLOCKED','fingerprint':fingerprint,
                                  'reason':type(exc).__name__,'next_action':'Owning branch reviews frozen inputs; no automatic regeneration',
                                  'input_revision':record['revision'],'updated_at':_timestamp()},
                       expected_digest=assembly_digest,compare=True)
            raise
