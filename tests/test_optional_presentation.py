"""Presentation switches must change the recipe, not resubmit paid visuals."""
import hashlib
import json
from pathlib import Path

import pytest

from engine.factory import Factory, load_preset
from engine.presentation import resolve_presentation, visual_duration
from engine.project.manifest import ProductionManifest, Shot
from engine.planning.director import create_production_plan


@pytest.mark.parametrize('mode', ['legacy', 'youtube_pro', 'reels_pro'])
@pytest.mark.parametrize('voice', [True, False])
@pytest.mark.parametrize('cards', [True, False])
def test_independent_switches_override_mode(mode, voice, cards):
    p = resolve_presentation(dict(production_mode=mode, voiceover_enabled=voice,
                                  text_cards_enabled=cards, caption_display='full'))
    assert p.voiceover is voice and p.text_cards is cards
    assert p.captions == ('full' if voice else 'none')
    assert p.sound_effects is voice and p.ambience is voice
    assert p.music_volume == (.55 if not voice else (.16 if mode == 'legacy' else .10))


@pytest.mark.parametrize('change', [dict(voiceover_enabled='false'), dict(text_cards_enabled=0),
                                    dict(music_volume=float('nan')), dict(music_volume=2),
                                    dict(text_card_style='unknown'), dict(sound_effects_enabled='no')])
def test_invalid_presentation_fails_before_work(change):
    with pytest.raises(ValueError):
        resolve_presentation(change)


def test_old_jobs_keep_existing_recipe():
    assert resolve_presentation({'production_mode': 'youtube_pro'}).text_cards
    assert not resolve_presentation({}).text_cards
    assert resolve_presentation({}).voiceover


def test_yaml_music_only_roundtrip(tmp_path):
    from engine.studio_config import load_video_config, config_to_factory_kwargs
    path = tmp_path/'reel.yaml'
    path.write_text('topic: A rabbit shares a carrot\nproduction_mode: reels_pro\ntheme: kids_cartoon\nvoiceover_enabled: false\ntext_cards_enabled: false\nbackground_music: local\nbackground_music_path: music.wav\n')
    cfg = load_video_config(str(path))
    assert cfg['caption_display'] == 'none'
    assert cfg['background_music_path'] == str(tmp_path/'music.wav')
    kwargs = config_to_factory_kwargs(cfg)
    assert kwargs['voiceover_enabled'] is False and kwargs['text_cards_enabled'] is False


def factory(tmp_path):
    return Factory(str(tmp_path/'outputs'), str(tmp_path/'jobs.db'))


def test_creation_pins_explicit_off(tmp_path):
    f = factory(tmp_path)
    job = f.create_job('A playful rabbit', production_mode='youtube_pro', voiceover_enabled=False,
                       text_cards_enabled=False, text_card_style='playful')
    assert not f._settings(job)['voiceover_enabled'] and not f._settings(job)['text_cards_enabled']
    assert f.pm.load_manifest(job).timing_source == 'visual_storyboard'


def test_invalid_create_has_no_partial_job(tmp_path):
    f = factory(tmp_path)
    with pytest.raises(ValueError):
        f.create_job('Test', music_volume=float('inf'))
    assert not list((tmp_path/'outputs').iterdir())


def test_edit_options_preserves_shots_projects_and_pending_journals(tmp_path):
    f = factory(tmp_path)
    job = f.create_job('Saved cartoon', flow_project_url='https://flow.google.com/project/11111111-1111-4111-8111-111111111111')
    m = f.pm.load_manifest(job)
    m.shots = [Shot(shot_id='s1', voice_end=13, status='accepted', accepted_take='original.mp4', compiled_prompt='original prompt')]
    f.pm.save_manifest(m)
    root = Path(f.pm.job_dir(job))
    journal = root/'storyboard/s1.jpg.flow-request.json'
    journal.write_text('{"status":"submitted","request_hash":"keep-this-record"}')
    before = hashlib.sha256(journal.read_bytes()).hexdigest()
    original_shots = m.model_dump()['shots']
    f.set_presentation_options(job, voiceover_enabled=False, text_cards_enabled=False,
                               background_music='local', background_music_path='licensed.wav')
    assert f.pm.load_manifest(job).model_dump()['shots'] == original_shots
    assert visual_duration(f.pm.load_manifest(job)) == 13  # Not a new 45s plan.
    assert hashlib.sha256(journal.read_bytes()).hexdigest() == before
    assert f._settings(job)['flow_project_url'].endswith('111111111111')
    assert json.loads((root/'production/review.json').read_text())['status'] == 'STALE_AFTER_PRESENTATION_CHANGE'
    with pytest.raises(ValueError):
        f.set_presentation_options(job, text_cards_enabled='false')
    assert f._settings(job)['text_cards_enabled'] is False


def test_new_music_only_job_never_calls_tts_asr_or_speech_retiming(tmp_path, monkeypatch):
    import engine.factory as module
    from engine import captions
    from engine.audio import tts
    from engine.planning import script_engine
    def forbidden(*args, **kwargs):
        pytest.fail('Music-only planning called a speech provider')
    monkeypatch.setattr(module, 'synthesize_narration', forbidden)
    monkeypatch.setattr(module, 'fit_narration_to_target', forbidden)
    monkeypatch.setattr(captions, 'get_word_timestamps', forbidden)
    monkeypatch.setattr(script_engine, 'retime_script_plan', forbidden)
    monkeypatch.setattr(tts, '_mp3_len', forbidden)
    f = factory(tmp_path)
    monkeypatch.setattr(f, '_generate_all', lambda *args: None)
    job = f.create_job('A rabbit shares a carrot', target_seconds=45, content_type='kids_story',
                       profile='LOCAL_FREE', preset='cartoon_story', voiceover_enabled=False,
                       text_cards_enabled=False, script_provider='planner', script_quality='standard', dry_run=True)
    assert f.run_job(job)['status'] == 'dry_complete'
    m = f.pm.load_manifest(job)
    assert m.timing_source == 'visual_storyboard' and len(m.shots) >= 5
    assert m.shots[-1].voice_end == 45
    assert max(s.duration_target for s in m.shots) <= 6.01
    assert not (Path(f.pm.job_dir(job))/'narration/voice.mp3').exists()
    assert not (Path(f.pm.job_dir(job))/'narration/voice.mp3.words.json').exists()


def test_visual_director_uses_action_windows_not_one_long_shot():
    from engine.routing.credit_router import CreditRouter
    from engine.planning.story_bible import build_bible
    preset = load_preset('cartoon_story')
    bible = build_bible('A rabbit shares', 'kids_story', preset, 'children', 'funny')
    beats = [{'name': 'Setup', 'text': 'A rabbit finds a carrot.', 'visual_intent': 'rabbit discovers a carrot'},
             {'name': 'Payoff', 'text': 'The rabbit shares it with a hungry friend.', 'visual_intent': 'two rabbits share and smile'}]
    m = create_production_plan(ProductionManifest(job_id='j', topic='A rabbit shares'), 'Story notes', [], beats,
                               bible, preset, CreditRouter('LOCAL_FREE'), 45, timing_source='visual_storyboard')
    assert len(m.shots) >= 8
    assert m.shots[0].voice_start == 0 and m.shots[-1].voice_end == 45
    assert all(a.voice_end == b.voice_start for a, b in zip(m.shots, m.shots[1:]))
    assert any('Setup' in s.visual_goal for s in m.shots) and any('Payoff' in s.visual_goal for s in m.shots)


def test_kids_theme_alias_does_not_fall_back_to_realism():
    assert load_preset('cartoon_3d')['name'] == 'CARTOON_STORY'


def test_private_unused_voice_not_required_for_music_only_rights(tmp_path):
    from engine.production import save, asset_inventory
    (tmp_path/'narration').mkdir()
    (tmp_path/'narration/voice.mp3').write_bytes(b'unused-private-voice')
    music = tmp_path/'music.wav'; music.write_bytes(b'licensed-music')
    save(tmp_path/'audio/sound_plan.json', {'voiceover_enabled':False, 'music':str(music), 'audio_expected':True})
    assert asset_inventory(tmp_path, {'segments':[]}) == [str(music)]


def test_intentionally_silent_production_check_skips_loudness(tmp_path, monkeypatch):
    from engine import production as p
    from tests.test_v580_production import job, fake_review_tools
    from engine.render import ffmpeg_renderer as ff
    job(tmp_path)
    p.save(tmp_path/'audio/sound_plan.json', {'audio_expected':False, 'voiceover_enabled':False})
    fake_review_tools(monkeypatch)
    monkeypatch.setattr(ff, '_probe_av_durations', lambda *a: {'video':6, 'audio':None})
    def run(cmd, *a, **k):
        from types import SimpleNamespace
        assert '-af' not in cmd, 'Silent video should not be sent to loudness measurement'
        return SimpleNamespace(stderr='')
    monkeypatch.setattr(p, 'run', run)
    result = p.check_job(tmp_path)
    assert not result['technical_issues']
    assert result['loudness']['status'] == 'not_applicable_intentionally_silent'


def test_cli_render_switches_edit_only_not_run_job(tmp_path, monkeypatch, capsys):
    import cli
    calls = []
    class FakeFactory:
        def set_presentation_options(self, job, **options):
            calls.append((job, options))
        def render_job(self, job, **kwargs):
            return {'job_id':job, 'video':'edited.mp4'}
        def run_job(self, *a, **k):
            pytest.fail('Render-only edits must not execute generation')
    import engine.factory as factory_module
    monkeypatch.setattr(factory_module, 'Factory', FakeFactory)
    cli.main_v3(['render', 'existing', '--no-voiceover', '--no-text-cards',
                 '--background-music','local','--background-music-path','licensed.wav',
                 '--text-card-style','playful'])
    assert calls == [('existing', {'voiceover_enabled':False, 'text_cards_enabled':False,
                                  'background_music':'local', 'background_music_path':'licensed.wav',
                                  'text_card_style':'playful'})]
