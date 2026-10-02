"""Destination exports and a local release desk. No silent social-account posting."""
from pathlib import Path
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import uuid

from .languages import language_pack
from .production import save, read, digest

PROFILES = {
    'instagram_reel': {'width':1080, 'height':1920, 'fps':30, 'audio_kbps':128, 'max_seconds':180, 'max_bytes':300*1024*1024},
    'facebook_reel': {'width':1080, 'height':1920, 'fps':30, 'audio_kbps':192, 'max_seconds':180, 'max_bytes':1024*1024*1024},
    'youtube_short': {'width':1080, 'height':1920, 'fps':30, 'audio_kbps':384, 'max_seconds':180, 'max_bytes':2*1024**3},
    'youtube_long': {'width':1920, 'height':1080, 'fps':30, 'audio_kbps':384, 'max_seconds':7200, 'max_bytes':8*1024**3},
}
# Conservative tested application recipes, not universal platform maximum limits.


def destination_profile(name):
    if name not in PROFILES:
        raise ValueError('Unknown destination profile')
    return dict(PROFILES[name])


def export_cmd(source, target, destination, *, framing='fit', duration=None):
    from .render.ffmpeg_renderer import ffmpeg_exe
    profile = destination_profile(destination)
    if framing not in ('fit', 'crop'):
        raise ValueError('Export framing must be fit or crop')
    if duration is not None and (not math.isfinite(float(duration)) or not 0 < float(duration) <= profile['max_seconds']):
        raise ValueError('Duration exceeds this conservative destination recipe; choose another export')
    w,h = profile['width'],profile['height']
    if framing == 'fit':
        vf = f'scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x18202b'
    else:
        vf = f'scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}'
    return [ffmpeg_exe(), '-y', '-i', str(source), '-map','0:v:0','-map','0:a?', '-vf',
            vf+f",setsar=1,fps={profile['fps']},format=yuv420p", '-c:v','libx264','-preset','medium',
            '-crf','18','-maxrate','20M','-bufsize','40M','-g',str(profile['fps']*2),
            '-c:a','aac','-b:a',f"{profile['audio_kbps']}k",'-ar','48000',
            '-movflags','+faststart',str(target)]


def export_delivery(source, folder, destination, *, language='en', title='', framing='fit', duration=None):
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise ValueError('Render a local source video first')
    profile = destination_profile(destination)
    if duration is None:
        from .render.ffmpeg_renderer import _probe_av_durations
        measured = _probe_av_durations(str(source))
        duration = measured.get('video') or measured.get('format')
        if not duration:
            raise ValueError('Cannot determine source duration; install ffprobe before export')
    code = language_pack(language).code
    folder = Path(folder).resolve()
    if folder == source.parent:
        raise ValueError('Export into a separate delivery folder to preserve the source')
    folder.mkdir(parents=True, exist_ok=True)
    filename = f'{destination}-{code}-{uuid.uuid4().hex[:8]}.mp4'
    output = folder/filename
    result = subprocess.run(export_cmd(source, output, destination, framing=framing, duration=duration),
                            capture_output=True, text=True, timeout=max(300, int(float(duration)*20)))
    if result.returncode:
        raise RuntimeError('Destination export failed: '+result.stderr[-700:])
    if output.stat().st_size > profile['max_bytes']:
        raise ValueError('Export exceeds this destination recipe file-size ceiling')
    from .render.ffmpeg_renderer import _probe_av_durations
    measured = _probe_av_durations(str(output))
    if measured.get('video') and abs(float(measured['video'])-float(duration)) > max(.5,float(duration)*.02):
        raise RuntimeError('Delivery video duration changed; review before release')
    record = {'schema_version':1, 'id':output.stem, 'video':str(output), 'sha256':digest(output),
              'source_sha256':digest(source), 'destination':destination, 'language':code,
              'title':title, 'profile':profile, 'duration':duration, 'state':'REVIEW_REQUIRED',
              'account_id':'', 'made_for_kids':None, 'ai_disclosure_required':None,
              'rights_confirmed':False, 'facts_reviewed':False, 'language_reviewed':False,
              'publishing_adapter':'manual-export', 'remote_id':None}
    save(folder/(output.stem+'.release.json'),record)
    return record


def approve_release(path, *, account_id, rights_confirmed=False, facts_reviewed=False,
                    language_reviewed=False, made_for_kids=None, ai_disclosure_required=None):
    record = read(path)
    if not record or digest(record['video']) != record['sha256']:
        raise ValueError('Delivery file is missing or changed; review the current render')
    if not str(account_id).strip() or not all(x is True for x in (rights_confirmed,facts_reviewed,language_reviewed)):
        raise ValueError('Select the exact account and approve rights, factual/story and language review')
    if type(made_for_kids) is not bool or type(ai_disclosure_required) is not bool:
        raise ValueError('Set intended kids audience and AI disclosure choices explicitly')
    record.update(account_id=str(account_id).strip(), rights_confirmed=True,facts_reviewed=True,
                  language_reviewed=True,made_for_kids=made_for_kids,
                  ai_disclosure_required=ai_disclosure_required,state='APPROVED_FOR_MANUAL_UPLOAD')
    save(path,record)
    return record


def schedule_release(path, publish_at):
    from datetime import datetime, timezone
    record = read(path)
    if not record or record.get('state') != 'APPROVED_FOR_MANUAL_UPLOAD' or digest(record['video']) != record['sha256']:
        raise ValueError('Approve this exact delivery before adding it to the local schedule')
    when = datetime.fromisoformat(str(publish_at))
    if when.tzinfo is None or when <= datetime.now(timezone.utc):
        raise ValueError('Use a future timezone-aware ISO timestamp')
    record.update(state='SCHEDULED_MANUAL_REMINDER',publish_at=when.isoformat(),
                  notice='Local reminder only. No social API upload is configured or submitted.')
    save(path,record)
    return record


def import_metrics(path, rows):
    """User-exported owned-account metrics; preserve platform definitions/denominators."""
    if not isinstance(rows,list) or len(rows)>10000:
        raise ValueError('Import at most 10000 metric rows')
    for row in rows:
        if not isinstance(row,dict) or not all(row.get(k) for k in ('account_id','destination','language','post_id','measured_at')):
            raise ValueError('Each metric row needs its account, platform, language, post ID and measurement date')
        destination_profile(row['destination']);language_pack(row['language'])
        metrics=row.get('metrics')
        if not isinstance(metrics,dict) or not metrics:
            raise ValueError('Use named native metrics; do not infer competitor retention from view counts')
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in metrics.values()):
            raise ValueError('Metric values must be finite nonnegative numbers')
    save(path,{'schema_version':1,'source':'user-exported-owned-account-metrics','rows':rows})
    return {'rows':len(rows),'source':'manual-owned-account-export'}
