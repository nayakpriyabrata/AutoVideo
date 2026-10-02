"""Approved external scripts/scene plans and chapter templates, without provider lock-in."""
from pathlib import Path
import hashlib
import json
import math

from .languages import language_pack, text_tokens
from .production import save


SAFE_RIGHTS = {'own_content', 'written_permission', 'licensed_content', 'creative_commons', 'public_domain'}


def validate_plan(value):
    if not isinstance(value, dict) or value.get('schema_version', 1) != 1:
        raise ValueError('Content plan must be a schema_version 1 JSON object')
    if value.get('approved') is not True:
        raise ValueError('Review and explicitly approve the imported script/storyboard first')
    if value.get('rights', {}).get('declaration') not in SAFE_RIGHTS:
        raise ValueError('An authorized script adaptation/ownership declaration is required')
    if value.get('rights', {}).get('adaptation_confirmed') is not True:
        raise ValueError('Confirm that adapting the transcript/script is authorized')
    topic = str(value.get('topic', '')).strip()
    narration = str(value.get('narration', '')).strip()
    if not topic or not narration or len(narration) > 200000:
        raise ValueError('The approved plan needs a topic and bounded nonempty narration/story text')
    lang = language_pack(value.get('language', 'en')).code
    scenes = value.get('scenes') or []
    if not isinstance(scenes, list) or len(scenes) > 1000:
        raise ValueError('Use at most 1000 scenes')
    for scene in scenes:
        if not isinstance(scene, dict) or not str(scene.get('text', '')).strip():
            raise ValueError('Each scene needs transcript/story text')
        if not str(scene.get('visual_intent') or scene.get('image_prompt') or '').strip():
            raise ValueError('Each scene needs an observable visual intent or image prompt')
        duration = scene.get('duration', 6)
        if type(duration) not in (int,float) or not math.isfinite(duration) or not .5 <= duration <= 30:
            raise ValueError('Scene durations must be finite 0.5–30 seconds')
    if scenes and ' '.join(s['text'].strip() for s in scenes).split() != narration.split():
        raise ValueError('Scene transcript text must cover the approved narration exactly and in order')
    chapters = value.get('chapters') or []
    if not isinstance(chapters, list) or len(chapters) > 100:
        raise ValueError('Use at most 100 chapters')
    for chapter in chapters:
        if not isinstance(chapter, dict) or not chapter.get('title') or not chapter.get('text'):
            raise ValueError('Each chapter requires a title and approved text')
    return {**value, 'schema_version':1, 'topic':topic, 'narration':narration,
            'language':lang, 'scenes':scenes, 'chapters':chapters}


def load_plan(path):
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size > 1024*1024:
        raise ValueError('Approved plan must be a local JSON file below 1 MB')
    return validate_plan(json.loads(source.read_text(encoding='utf-8')))


def script_from_plan(plan):
    scenes = plan['scenes']
    beats = [{'name':str(s.get('name') or f'Scene {i+1}'), 'text':s['text'],
              'visual_intent':s.get('visual_intent') or s['image_prompt'],
              'image_prompt':s.get('image_prompt', ''), 'motion_prompt':s.get('motion_prompt', '')}
             for i,s in enumerate(scenes)]
    if not beats:
        beats = [{'name':c['title'], 'text':c['text'], 'visual_intent':c.get('visual_intent') or c['title']}
                 for c in plan['chapters']]
    if not beats:
        beats = [{'name':plan['topic'], 'text':plan['narration'], 'visual_intent':plan['topic']}]
    return {'topic':plan['topic'], 'angle':plan.get('angle', 'Approved original adaptation'),
            'audience':plan.get('audience', 'General audience'), 'narration':plan['narration'],
            'beats':beats, 'words':len(text_tokens(plan['narration'])), 'source':'approved-import',
            'editorial_qc':{'passed':True, 'flags':[], 'scope':'Human-approved import, not automated fact/legal certification'},
            'chapters':plan['chapters'], 'claims':plan.get('claims', []),
            'provenance':plan.get('provenance', {}), 'rights':plan['rights']}


def plan_fingerprint(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def longform_template(topic, language='en'):
    return {'schema_version':1, 'topic':topic, 'language':language_pack(language).code,
            'approved':False, 'narration':'', 'audience':'', 'scenes':[],
            'chapters':[{'title':name, 'text':'', 'visual_intent':'', 'evidence':[]}
                        for name in ('Opening promise', 'Problem and context', 'Worked example', 'Demonstration', 'Limitations', 'Useful conclusion')],
            'claims':[], 'provenance':{}, 'rights':{'declaration':'own_content', 'adaptation_confirmed':False}}
