"""Recreate an authorized clip as an ORIGINAL AI character story, not a face swap.

Planning/approval are offline. Running the saved Factory job is a separate,
explicit generation action with the existing Flow credit/request protections.
"""
from pathlib import Path
import hashlib
import json
import math
import re

from .content_library import CharacterLibrary, character_snapshot
from .content_plan import SAFE_RIGHTS, validate_plan, plan_fingerprint
from .languages import language_pack, script_language
from .production import save, read, digest


def _transcript_record(clip, transcript_text=''):
    sidecar = clip.with_suffix('.transcript.json')
    if transcript_text:
        return str(transcript_text).strip(), 'user-reviewed-transcript'
    record = read(sidecar, {})
    if not record or record.get('clip_sha256') != digest(clip):
        raise ValueError('A matching clip transcript sidecar or explicitly reviewed transcript is required')
    text = str(record.get('text') or '').strip()
    if not text:
        raise ValueError('This clip has no approved usable transcript')
    return text, str(sidecar)


def create_recreation_job(factory, clip_path, character_id, *, library_root='data/content/characters',
                          transcript_text='', language='en', source_rights='unknown',
                          adaptation_confirmed=False, max_credits=50, background_music='',
                          text_cards_enabled=False, tts_provider='auto', content_type='education'):
    if source_rights not in SAFE_RIGHTS or adaptation_confirmed is not True:
        raise ValueError('Confirm rights to adapt the transcript AND footage; changing the person does not clear copyright')
    if type(max_credits) is not int or not 0 <= max_credits <= 5000:
        raise ValueError('Set a finite integer Flow credit ceiling 0–5000')
    clip = Path(clip_path).expanduser().resolve()
    if not clip.is_file() or clip.suffix.lower() not in ('.mp4','.mov','.webm','.mkv'):
        raise ValueError('Select an existing local clip; source remains unchanged')
    character = CharacterLibrary(library_root).get(character_id)
    text, origin = _transcript_record(clip, transcript_text)
    code = language_pack(language).code
    detected = script_language(text)
    if detected != 'en' and code != detected:
        raise ValueError('Transcript script does not match the selected language; review/localize it explicitly')
    from .reference_manager import ReferenceManager
    duration = ReferenceManager.probe_duration(str(clip))
    if duration is None or not math.isfinite(duration) or not 3 <= duration <= 180:
        raise ValueError('AI clip recreation is limited to verified 3–180 second clips')
    chunks = [x.strip() for x in re.split(r'(?<=[.!?।॥])\s+', text) if x.strip()]
    # Split long narration into bounded semantic notes, never change narration.
    if len(chunks) == 1:
        words = text.split()
        chunks = [' '.join(words[i:i+15]) for i in range(0,len(words),15)]
    scenes = []
    for index, chunk in enumerate(chunks):
        scenes.append({'name':f'Scene {index+1}', 'text':chunk, 'duration':min(8, max(3,duration/max(1,len(chunks)))),
                       'visual_intent':f"{character['name']} visually demonstrates this approved idea: {chunk}",
                       'image_prompt':f"Original character {character['description']}. Illustrate: {chunk}. Clear vertical 9:16 scene, no text or logos.",
                       'motion_prompt':f"Keep this original character reference unchanged. Show one clear action illustrating: {chunk}. Smooth coherent motion, no dialogue or captions; authored voice added in edit."})
    plan = validate_plan({'schema_version':1,'topic':f"{character['name']}: AI recreation",'language':code,
                          'narration':text,'scenes':scenes,'approved':True,
                          'rights':{'declaration':source_rights,'adaptation_confirmed':True},
                          'provenance':{'source_clip':str(clip),'clip_sha256':digest(clip),
                                        'transcript_origin':origin,'transcript_sha256':hashlib.sha256(text.encode()).hexdigest(),
                                        'notice':'Transcript adaptation is declared authorized; not legal certification. No real-person identity is cloned.'}})
    job = factory.create_job(plan['topic'], video_type='shorts', target_seconds=max(10, int(math.ceil(duration))),
                             aspect='9:16', language=code, content_type=content_type, profile='STORYBOARD_ECONOMY',
                             frame_source='flow', images_per_shot=0, flow_scenes=len(scenes),
                             budgets={'MAX_CREDITS_PER_VIDEO':max_credits}, script_quality='standard',
                             auto_retime_script=False, tts_provider=tts_provider, voiceover_enabled=True,
                             text_cards_enabled=text_cards_enabled,
                             background_music='local' if background_music else 'off', background_music_path=background_music)
    factory.import_content_plan(job, plan)
    root = Path(factory.pm.job_dir(job))
    save(root/'character_snapshot.json',character_snapshot(character))
    save(root/'recreation.json',{'schema_version':1,'state':'STORYBOARD_REVIEW_REQUIRED',
                               'plan_sha256':plan_fingerprint(plan),'source_sha256':digest(clip),
                               'source_clip':str(clip),'character_id':character_id,'max_credits':max_credits,
                               'notice':'Planning used no TTS/image/video generation. Approve then Resume to generate; exact timing, acting and lip-sync require review.'})
    return {'job_id':job,'state':'STORYBOARD_REVIEW_REQUIRED','plan':str(root/'approved_content_plan.json'),
            'new_generations':0,'max_credits':max_credits}


def approval_fingerprint(root):
    root=Path(root)
    plan = read(root/'approved_content_plan.json')
    snapshot = read(root/'character_snapshot.json')
    settings = read(root/'settings.json')
    if not plan or not snapshot:
        raise ValueError('Recreation plan or character snapshot missing')
    from .content_plan import script_from_plan
    script=read(root/'script.json')
    # Only immutable authored fields, not derived QC or runtime metadata.
    expected = script_from_plan(plan)
    if not script or any(script.get(key) != expected.get(key) for key in ('narration','beats','chapters','rights')):
        raise ValueError('Saved narration differs from the reviewed storyboard; import/reapprove before generation')
    value={'plan':plan,'character':snapshot,'budget':settings.get('budgets',{}),
           'script_narration':script['narration'],
           'language':plan.get('language'),'tts_provider':settings.get('tts_provider'),
           'voiceover_enabled':settings.get('voiceover_enabled'),
           'frame_source':settings.get('frame_source'),'profile':read(root/'production_manifest.json',{}).get('profile'),
           'speech_settings':{key:settings.get(key) for key in ('tts_model','tts_voice','tts_style','narration_input_path','auto_retime_script')},
           'source_sha256':read(root/'recreation.json',{}).get('source_sha256')}
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def approve_recreation(factory, job):
    root=Path(factory.pm.job_dir(job));record=read(root/'recreation.json')
    if not record or digest(record['source_clip']) != record['source_sha256']:
        raise ValueError('Original clip is missing or changed; create a reviewed plan')
    snapshot=read(root/'character_snapshot.json')
    for reference in snapshot.get('references',[]):
        if digest(reference['path']) != reference['sha256']:
            raise ValueError('Character reference changed; review a fresh snapshot')
    from .content_plan import validate_plan
    reviewed = validate_plan(read(root/'approved_content_plan.json'))
    if not factory.pm.load_manifest(job).shots:
        factory.import_content_plan(job,reviewed)
    record.update(state='APPROVED_FOR_GENERATION',approval_sha256=approval_fingerprint(root))
    save(root/'recreation.json',record)
    return {'job_id':job,'state':record['state'],'new_generations':0,
            'next_action':'Resume this saved job explicitly to run TTS and Flow generation'}


def require_recreation_approval(root):
    root=Path(root);record=read(root/'recreation.json')
    if record is None:
        return
    if record.get('state') != 'APPROVED_FOR_GENERATION' or record.get('approval_sha256') != approval_fingerprint(root):
        raise ValueError('Recreation storyboard/character/budget must be approved before TTS or Flow generation')
    if digest(record['source_clip']) != record['source_sha256']:
        raise ValueError('Recreation source changed since approval')
    for reference in read(root/'character_snapshot.json',{}).get('references',[]):
        if digest(reference['path']) != reference['sha256']:
            raise ValueError('Approved character reference changed; no generation submitted')
