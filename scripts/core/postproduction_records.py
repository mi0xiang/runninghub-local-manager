"""Frozen generic local postproduction plans and delivery evidence; no execution."""
import json
import math
from pathlib import Path
from archive_integrity import sha256
import durable_store as store

def local_file(folder, relative):
    folder=Path(folder).resolve();rel=Path(relative);path=(folder/rel).resolve()
    if rel.is_absolute() or not path.is_relative_to(folder) or not path.is_file():
        raise ValueError('Expected an existing project-local file')
    return path

def validate_plan(folder, spec):
    if spec.get('schema_version')!=1 or not spec.get('version') or not spec.get('segments'):
        raise ValueError('Versioned segment plan required')
    sources=[]
    for segment in spec['segments']:
        path=local_file(folder,segment['file'])
        if sha256(path)!=segment['sha256']:raise ValueError('Postproduction input changed')
        start=float(segment['start']);end=float(segment['end'])
        if not math.isfinite(start) or not math.isfinite(end) or start<0 or end<=start:
            raise ValueError('Invalid segment trim range')
        sources.append({'file':segment['file'],'sha256':segment['sha256'],'start':start,'end':end,
                        'taskId':segment.get('taskId'),'production_version':segment.get('production_version')})
    quality=spec.get('quality_review',{})
    if quality.get('status')!='ACCEPTED' or not quality.get('evidence'):
        return {'state':'AWAITING_QUALITY_REVIEW','segments':sources}
    audio=spec.get('audio',{})
    if audio.get('mode') not in ('none','generated','source','bgm'):raise ValueError('Explicit audio mode required')
    if audio['mode'] in ('source','bgm'):
        if audio.get('authorized') is not True or not audio.get('authorization_evidence'):
            return {'state':'AWAITING_AUDIO_APPROVAL','segments':sources}
        if sha256(local_file(folder,audio['file']))!=audio['sha256']:raise ValueError('Audio input changed')
    return {'state':'READY','segments':sources,'audio':audio,'version':spec['version']}

def register_plan(folder, spec, expected_revision):
    folder=Path(folder);result=validate_plan(folder,spec)
    path=folder/'postproduction.json';before=store.digest(path);old=store.read(path,{})
    if old.get('revision',0)!=expected_revision:raise RuntimeError('Postproduction revision changed')
    if old.get('plan')==spec:return old
    record={'schema_version':1,'revision':expected_revision+1,'plan':spec,'state':result['state']}
    store.save(path,record,expected_digest=before,compare=True)
    return record

def register_delivery(folder, record, expected_revision):
    folder=Path(folder)
    plan=store.read(folder/'postproduction.json',{})
    if validate_plan(folder,plan.get('plan',{}))['state']!='READY':raise ValueError('Postproduction prerequisites not accepted')
    video=local_file(folder,record['result_video'])
    if record.get('complete') is not True or sha256(video)!=record['sha256']:
        raise ValueError('Complete verified output required')
    technical=record.get('technical',{})
    if technical.get('media') is not True or technical.get('decode') is not True:
        raise ValueError('Media and full-decode evidence required')
    if not technical.get('evidence') or record.get('input_revision')!=plan['revision']:
        raise ValueError('Technical evidence and exact frozen input revision required')
    path=folder/'delivery.json';before=store.digest(path);old=store.read(path,{})
    if old.get('revision',0)!=expected_revision:raise RuntimeError('Delivery revision changed')
    value=dict(record,schema_version=1,revision=expected_revision+1,human_review={'status':'PENDING'})
    store.save(path,value,expected_digest=before,compare=True)
    return value
