import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from engine import production as p
from engine.render.structured_graphics import validate_events, render_card
from engine.clipping import framing_filter


def good_verdict():
    return dict(relevance=True, text_accuracy=True, face_unobstructed=True,
                watermark_free=True, artifacts_ok=True, score=90, reason='Visible subject matches narration')


@pytest.mark.parametrize('change', [{'score': float('nan')}, {'score': True}, {'score': 101},
                                   {'relevance': 'true'}, {'reason': ''}])
def test_semantic_response_fails_closed(change):
    with pytest.raises(ValueError):
        p.validate_verdict({**good_verdict(), **change})


def job(tmp_path):
    p.save(tmp_path/'production_manifest.json', {'job_id': 'job', 'shots': [
        {'shot_id': 's1', 'narration': 'Practice speaking', 'visual_goal': 'Office meeting'}]})
    final = tmp_path/'render/job-final.mp4'
    final.parent.mkdir(exist_ok=True)
    final.write_bytes(b'original-render')
    p.save(tmp_path/'render/timeline.json', {'total': 6, 'segments': [
        {'shot_id': 's1', 'src': str(final), 'dur': 6, 'freeze': 0, 'timeline_start': 0}]})
    return final


def test_init_preserves_evidence(tmp_path):
    job(tmp_path)
    p.init_review(tmp_path)
    p.save(tmp_path/'production/facts.json', {'research_complete': True})
    p.init_review(tmp_path)
    assert p.read(tmp_path/'production/facts.json')['research_complete']


def test_rights_evidence_changes_invalidate_gate(tmp_path):
    media = tmp_path/'media.mp4'; media.write_bytes(b'media')
    evidence = tmp_path/'permission.txt'; evidence.write_text('Permission for listed uses')
    record = dict(sha256=p.digest(media), creator='Creator', source_url='https://example.org/original',
                  license='Written permission', verified_at='2026-09-29',
                  commercial_use_allowed=True, adaptation_allowed=True, third_party_audio_cleared=True,
                  evidence_file='permission.txt', evidence_sha256=p.digest(evidence), attribution_required=False)
    assert p.rights_check([media], {'assets': [record]}, tmp_path)['passed']
    evidence.write_text('Changed evidence')
    assert not p.rights_check([media], {'assets': [record]}, tmp_path)['passed']


def fake_review_tools(monkeypatch):
    from engine.render import ffmpeg_renderer as ff
    monkeypatch.setattr(p, 'probe', lambda *a: {})
    monkeypatch.setattr(p, 'run', lambda *a, **k: SimpleNamespace(stderr='{"input_i":"-14","input_tp":"-1"}'))
    monkeypatch.setattr(ff, '_probe_av_durations', lambda *a: {'video': 6, 'audio': 6})
    monkeypatch.setattr(ff, '_black_duration_ratio', lambda *a, **k: 0)
    monkeypatch.setattr(ff, '_freeze_metrics', lambda *a: {'ratio': 0, 'longest': 0})
    monkeypatch.setattr(p, 'frame', lambda src, at, dest: Image.new('RGB', (32, 32), 'blue').save(dest))


def test_budget_cache_and_render_change(monkeypatch, tmp_path):
    final = job(tmp_path)
    fake_review_tools(monkeypatch)
    calls = []
    monkeypatch.setattr(p, 'semantic_review', lambda *a: calls.append(1) or good_verdict())
    result = p.check_job(tmp_path, 'test-model', 0)
    assert result['status'] == 'NEEDS_REVIEW' and not calls
    result = p.check_job(tmp_path, 'test-model', 1)
    assert result['gates']['semantic_sample_review'] and len(calls) == 1
    assert not result['gates']['rights_evidence']
    p.check_job(tmp_path, 'test-model', 0)
    assert len(calls) == 1
    final.write_bytes(b'new-render')
    assert not p.check_job(tmp_path, 'test-model', 0)['gates']['semantic_sample_review']
    assert p.read(tmp_path/'production/review-progress.json')['complete']


def test_sampling_failure_does_not_pass(monkeypatch, tmp_path):
    job(tmp_path); fake_review_tools(monkeypatch)
    monkeypatch.setattr(p, 'frame', lambda *a: (_ for _ in ()).throw(RuntimeError('decode problem')))
    result = p.check_job(tmp_path)
    assert result['shots'][0]['failures'] == ['frame_sampling_failed']
    assert result['status'] == 'NEEDS_REVIEW'


def test_repairs_are_validated_before_commit(monkeypatch, tmp_path):
    final = job(tmp_path)
    source = tmp_path/'replacement.mp4'; source.write_bytes(b'replacement')
    plan = tmp_path/'plan.json'
    p.save(plan, {'video_sha256': p.digest(final), 'repairs': [
        {'shot_id': 's1', 'replacement_path': str(source)},
        {'shot_id': 'unknown', 'replacement_path': str(source)}]})
    monkeypatch.setattr(p, 'probe', lambda *a: {'streams': [{'codec_type': 'video'}], 'format': {'duration': 7}})
    monkeypatch.setattr(p, 'run', lambda *a, **k: SimpleNamespace(stderr=''))
    with pytest.raises(ValueError, match='unknown'):
        p.stage_repairs(tmp_path, plan)
    assert not (tmp_path/'production/media_overrides.json').exists()
    data = p.read(plan); data['repairs'].pop(); p.save(plan, data)
    assert p.stage_repairs(tmp_path, plan)['paid_generations'] == 0
    timeline = p.apply_overrides(tmp_path, p.read(tmp_path/'render/timeline.json'))
    assert timeline['segments'][0]['local_repair'] and timeline['segments'][0]['freeze'] == 0
    Path(timeline['segments'][0]['src']).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='changed'):
        p.apply_overrides(tmp_path, timeline)


def test_stale_repair_rejected(tmp_path):
    job(tmp_path)
    p.save(tmp_path/'plan.json', {'video_sha256': 'different', 'repairs': []})
    with pytest.raises(ValueError, match='stale'):
        p.stage_repairs(tmp_path, tmp_path/'plan.json')


def card():
    return dict(kind='list', start=0, end=5, title='Three useful habits', active=0,
                rows=[{'label': 'Listen carefully'}, {'label': 'Organise your thoughts'}, {'label': 'Practise daily'}])


@pytest.mark.parametrize('change', [{'start': -1}, {'end': 99}, {'kind': 'unknown'},
                                   {'rows': []}, {'active': 3}, {'end': float('nan')}])
def test_bad_graphics_rejected(change):
    with pytest.raises(ValueError):
        validate_events([{**card(), **change}], 6)


def test_overlapping_cards_rejected():
    with pytest.raises(ValueError, match='overlap'):
        validate_events([card(), card()], 6)


@pytest.mark.parametrize('dimensions', [(1920, 1080), (1080, 1920)])
def test_transparent_list_card(tmp_path, dimensions):
    path = tmp_path/'card.png'
    render_card(card(), path, *dimensions)
    with Image.open(path) as im:
        assert im.getpixel((0, 0))[3] == 0
        assert im.getextrema()[3] == (0, 255)


def test_chart_requires_evidence_and_finite_values():
    chart = {**card(), 'kind': 'bar_chart', 'rows': [{'label': 'A', 'value': 3}]}
    with pytest.raises(ValueError, match='source'):
        validate_events([chart], 6)
    chart.update(source='Internal experiment', unit='seconds')
    assert validate_events([chart], 6)
    chart['rows'][0]['value'] = float('inf')
    with pytest.raises(ValueError):
        validate_events([chart], 6)


def test_fit_preserves_full_source():
    assert 'crop=' not in framing_filter('fit')
    assert 'pad=1080:1920' in framing_filter('fit')
    assert 'crop=' in framing_filter('face-crop')
    with pytest.raises(ValueError):
        framing_filter('unsupported')


def test_clipping_does_not_guess_a_model(monkeypatch):
    from engine import clipping
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.delenv('GEMINI_CLIP_MODEL', raising=False)
    monkeypatch.delenv('GEMINI_SCRIPT_MODEL', raising=False)
    monkeypatch.setattr(clipping.requests, 'post', lambda *a, **k: pytest.fail('unexpected API request'))
    with pytest.raises(RuntimeError, match='no model ID is assumed'):
        clipping._gemini_youtube_candidates('https://youtube.com/watch?v=example', 120, 3, 25, 55)
