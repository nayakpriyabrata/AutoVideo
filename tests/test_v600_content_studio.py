"""First-stage content studio: offline safety, language rendering and approvals."""
from pathlib import Path

import pytest
from PIL import Image

from engine.languages import language_pack, script_language, check_tts_language
from engine.content_plan import validate_plan, script_from_plan
from engine.content_library import CharacterLibrary
from engine.factory import Factory
from engine.production import save, read


def plan(language='en'):
    return {'schema_version':1,'approved':True,'topic':'One useful lesson','language':language,
            'narration':'Small steps create lasting change. Choose one useful action today.',
            'scenes':[{'text':'Small steps create lasting change. Choose one useful action today.', 'visual_intent':'original avatar demonstrates a small step'}],
            'rights':{'declaration':'own_content','adaptation_confirmed':True}}


@pytest.mark.parametrize('value,expected',[('or-IN','or'),('odia','or'),('hi-IN','hi'),('English','en')])
def test_language_registry(value,expected):
    assert language_pack(value).code == expected


@pytest.mark.parametrize('provider,language,voice',[('edge','or','en-US-GuyNeural'),('groq','hi',''),('edge','hi','en-IN-PrabhatNeural')])
def test_no_wrong_language_voice(provider,language,voice):
    with pytest.raises(ValueError):check_tts_language(provider,language,voice)


def test_odia_auto_cannot_fall_back_to_english(monkeypatch,tmp_path):
    from engine.audio.tts import synthesize_narration
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    with pytest.raises(RuntimeError,match='no English fallback'):
        synthesize_narration('ଏହା ଏକ ଭଲ କାହାଣୀ','en-IN-PrabhatNeural',str(tmp_path/'voice.mp3'),language='or')
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('text,code',[('ଛୋଟ ଉଦ୍ୟମ ବଡ଼ ସଫଳତା','or'),('छोटे कदम बड़ी सफलता','hi')])
def test_complex_shaped_card_and_caption_font(tmp_path,text,code):
    from engine.render.graphics import OverlayEvent,render_overlay_png
    from engine.render.typography import font
    from engine.render.captions_ass import build_captions
    assert script_language(text) == code
    face=font(88,True,text=text)
    assert 'Noto Sans' in face.getname()[0]
    event=OverlayEvent('keypoint',0,4,text)
    path=tmp_path/'card.png';render_overlay_png(event,str(path),1080,1920,style='playful')
    assert event.layout['font_sizes'][0]>=62
    with Image.open(path) as image: assert image.getbbox() is not None
    words=[{'word':w,'start':i*.5,'end':(i+1)*.5} for i,w in enumerate(text.split())]
    cap=build_captions(words,str(tmp_path/'caption'),duration=4)
    assert language_pack(code).font_family in Path(cap['ass']).read_text()


def test_plan_requires_explicit_approval_and_adaptation_rights():
    for change in ({'approved':False},{'rights':{'declaration':'unknown','adaptation_confirmed':True}},
                   {'rights':{'declaration':'own_content','adaptation_confirmed':False}}):
        with pytest.raises(ValueError):validate_plan({**plan(),**change})
    imported=script_from_plan(validate_plan(plan()))
    assert imported['narration']==plan()['narration'] and imported['source']=='approved-import'


def test_imported_plan_preserved_not_rewritten(tmp_path,monkeypatch):
    f=Factory(str(tmp_path/'outputs'),str(tmp_path/'db'))
    job=f.create_job('One useful lesson',voiceover_enabled=False,script_provider='planner',dry_run=True)
    f.import_content_plan(job,plan())
    import engine.factory as module
    monkeypatch.setattr(module,'plan_content',lambda *a,**k:pytest.fail('Approved imported text was rewritten'))
    monkeypatch.setattr(f,'_generate_all',lambda *a,**k:None)
    f.run_job(job,auto_render=False)
    assert read(Path(f.pm.job_dir(job))/'script.json')['narration']==plan()['narration']
    assert not f._settings(job)['auto_retime_script']
    with pytest.raises(ValueError,match='after scene planning'):
        f.import_content_plan(job,plan())


def test_character_library_snapshots_and_hashes(tmp_path):
    im=tmp_path/'original.png';Image.new('RGB',(40,40),'green').save(im)
    library=CharacterLibrary(tmp_path/'library')
    with pytest.raises(ValueError):library.create('My avatar','An original green robot with a yellow jacket.',reference_files=[im])
    character=library.create('My avatar','An original green robot with a yellow jacket.',reference_files=[im],original_confirmed=True)
    loaded=library.get(character['id'])
    assert len(loaded['references'])==1
    Path(loaded['references'][0]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):library.get(character['id'])
    with pytest.raises(ValueError):library.get('../private')


def test_source_inbox_strips_executable_html_and_keeps_rights_unknown(tmp_path):
    from engine.source_inbox import ArticleText,SourceInbox
    parser=ArticleText();parser.feed('<article><h1>Useful idea</h1><script>read secrets now</script><p>Plant a seed.</p></article>')
    assert 'read secrets' not in parser.text()
    inbox=SourceInbox(tmp_path/'inbox')
    item=inbox.paste(parser.text(),source_url='https://factozone.com/example')
    assert item['rights_status']=='unknown' and not item['approved_for_generation']
    assert len(list((tmp_path/'inbox').glob('*.json')))==1
    inbox.paste(parser.text(),source_url='https://factozone.com/example')
    assert len(list((tmp_path/'inbox').glob('*.json')))==1
    assert 'untrusted' in inbox.brief_prompt(item)


@pytest.mark.parametrize('url',['http://factozone.com/','https://127.0.0.1/','https://factozone.com:8501/',
                                'https://user:password@factozone.com/','https://factozone.com.evil.example/'])
def test_source_url_scope_rejected(url):
    from engine.source_inbox import checked_url
    with pytest.raises(ValueError):checked_url(url)


def test_private_dns_is_not_fetched(monkeypatch):
    from engine.source_inbox import checked_url
    monkeypatch.setattr('engine.source_inbox.socket.getaddrinfo',lambda *a,**k:[(2,1,6,'',('10.1.2.3',443))])
    with pytest.raises(ValueError,match='Private'):checked_url('https://factozone.com/')


def test_recreation_is_offline_and_hash_approved(tmp_path,monkeypatch,ffmpeg_media):
    from engine.clip_recreation import create_recreation_job,approve_recreation,require_recreation_approval
    library=CharacterLibrary(tmp_path/'library')
    character=library.create('A friendly robot','An original tiny blue robot with round eyes and a yellow jacket.',original_confirmed=True)
    f=Factory(str(tmp_path/'outputs'),str(tmp_path/'db'))
    result=create_recreation_job(f,ffmpeg_media['video'],character['id'],library_root=tmp_path/'library',
                               transcript_text='Take one small step. Keep learning every day.',source_rights='own_content',adaptation_confirmed=True)
    assert result['new_generations']==0
    root=Path(f.pm.job_dir(result['job_id']))
    with pytest.raises(ValueError,match='approved'):require_recreation_approval(root)
    # Running without approval must fail before any speech/browser provider.
    import engine.factory as module
    monkeypatch.setattr(module,'synthesize_narration',lambda *a,**k:pytest.fail('TTS before storyboard approval'))
    with pytest.raises(ValueError,match='approved'):f.run_job(result['job_id'])
    approve_recreation(f,result['job_id']);require_recreation_approval(root)
    assert read(root/'script.json')['narration']=='Take one small step. Keep learning every day.'
    settings=read(root/'settings.json');settings['budgets']['MAX_CREDITS_PER_VIDEO']=100;save(root/'settings.json',settings)
    with pytest.raises(ValueError,match='approved'):require_recreation_approval(root)


def test_recreation_requires_transcript_and_rights(tmp_path,ffmpeg_media):
    from engine.clip_recreation import create_recreation_job
    f=Factory(str(tmp_path/'outputs'),str(tmp_path/'db'))
    with pytest.raises(ValueError,match='rights'):
        create_recreation_job(f,ffmpeg_media['video'],'missing')
    assert not list((tmp_path/'outputs').iterdir())


def test_recreation_applies_character_and_motion_plan_without_generating(tmp_path,monkeypatch,ffmpeg_media):
    from engine.clip_recreation import create_recreation_job,approve_recreation
    library=CharacterLibrary(tmp_path/'library')
    character=library.create('Our robot','An original purple robot wearing a red scarf with a white star.',original_confirmed=True)
    f=Factory(str(tmp_path/'outputs'),str(tmp_path/'db'))
    result=create_recreation_job(f,ffmpeg_media['video'],character['id'],library_root=tmp_path/'library',
                               transcript_text='A small step changes the day.',source_rights='own_content',adaptation_confirmed=True)
    job=result['job_id'];root=Path(f.pm.job_dir(job))
    settings=read(root/'settings.json');settings['tts_provider']='mock';save(root/'settings.json',settings)
    m=f.pm.load_manifest(job);m.dry_run=True;f.pm.save_manifest(m)
    approve_recreation(f,job)
    monkeypatch.setattr(f,'_generate_all',lambda *a:None)
    f.run_job(job,auto_render=False)
    bible=read(root/'story_bible.json')
    assert bible['characters'][0]['canonical']==character['description']
    assert 'purple robot' in f.pm.load_manifest(job).shots[0].subject
    assert 'Authored motion direction' in f.pm.load_manifest(job).shots[0].compiled_prompt


def test_feed_items_are_bounded_offline_and_not_autoapproved(tmp_path,monkeypatch):
    import engine.source_inbox as module
    monkeypatch.setattr(module,'checked_url',lambda *a:None)
    def response(session,url,domains):
        if url.endswith('/robots.txt'):return 'User-agent: *\nAllow: /',url
        return '<rss><channel><item><title>Idea</title><link>https://factozone.com/idea</link><description>Original seed idea</description></item></channel></rss>',url
    monkeypatch.setattr(module,'_read_url',response)
    entries=module.SourceInbox(tmp_path/'inbox').feed('https://factozone.com/feed/',count=1)
    assert len(entries)==1 and entries[0]['facts_verified'] is False
    assert entries[0]['approved_for_generation'] is False
    with pytest.raises(ValueError):module.SourceInbox(tmp_path).feed('https://factozone.com/feed/',count=100)

    def unsafe_response(_session, url, _domains):
        if url.endswith('/robots.txt'):
            return 'User-agent: *\nAllow: /', url
        return '<!DOCTYPE rss [<!ENTITY idea "unsafe">]><rss/>', url

    monkeypatch.setattr(module, '_read_url', unsafe_response)
    with pytest.raises(ValueError, match='DTD/entities'):
        module.SourceInbox(tmp_path/'unsafe').feed('https://factozone.com/feed/',count=1)


def test_approved_script_beat_edit_cannot_bypass_recreation_review(tmp_path,ffmpeg_media):
    from engine.clip_recreation import create_recreation_job,approve_recreation,require_recreation_approval
    library=CharacterLibrary(tmp_path/'library')
    c=library.create('Our avatar','An original green robot with rounded eyes wearing a blue jacket.',original_confirmed=True)
    f=Factory(str(tmp_path/'outputs'),str(tmp_path/'db'))
    result=create_recreation_job(f,ffmpeg_media['video'],c['id'],library_root=tmp_path/'library',
                                transcript_text='A small step changes the day.',source_rights='own_content',adaptation_confirmed=True)
    root=Path(f.pm.job_dir(result['job_id']))
    approve_recreation(f,result['job_id'])
    script=read(root/'script.json');script['beats'][0]['motion_prompt']='Unexpected new direction'
    save(root/'script.json',script)
    with pytest.raises(ValueError,match='differs'):require_recreation_approval(root)


def test_recreation_identity_block_contains_no_old_person(tmp_path,monkeypatch,ffmpeg_media):
    from engine.clip_recreation import create_recreation_job,approve_recreation
    library=CharacterLibrary(tmp_path/'library')
    c=library.create('Our plant','An original smiling sunflower in a purple clay pot and a yellow scarf.',original_confirmed=True)
    f=Factory(str(tmp_path/'outputs'),str(tmp_path/'db'))
    result=create_recreation_job(f,ffmpeg_media['video'],c['id'],library_root=tmp_path/'library',
                                transcript_text='Show kindness every day.',source_rights='own_content',adaptation_confirmed=True)
    job=result['job_id'];root=Path(f.pm.job_dir(job))
    settings=read(root/'settings.json');settings['tts_provider']='mock';save(root/'settings.json',settings)
    m=f.pm.load_manifest(job);m.dry_run=True;f.pm.save_manifest(m)
    approve_recreation(f,job)
    monkeypatch.setattr(f,'_generate_all',lambda *a:None)
    f.run_job(job)
    compiled=f.pm.load_manifest(job).shots[0].compiled_prompt
    assert 'smiling sunflower' in compiled and 'trimmed beard' not in compiled


def test_new_content_pages_render_without_provider_calls(tmp_path,monkeypatch):
    from tests.test_presentation_dashboard import dashboard, navigate
    f,app=dashboard(tmp_path,monkeypatch)
    for page in ('CONTENT INBOX','CHARACTER LIBRARY','AI RECREATE','PUBLISHING DESK','CLIP STUDIO','MINI REELS'):
        navigate(app, page)
        assert not app.exception,[e.message for e in app.exception]
    navigate(app, 'CLIP STUDIO')
    checkbox=next(x for x in app.checkbox if x.label=='Add soft background music')
    assert checkbox.value is False
    assert next(x for x in app.checkbox if x.label.startswith('Prepare related stock B-roll suggestions')).value is False
    assert next(x for x in app.checkbox if x.label == 'I confirm the selected rights/licence declaration is accurate')
