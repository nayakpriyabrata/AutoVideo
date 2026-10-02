import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from engine.clipping import soft_music_filter
from engine.production import read,save,digest
from engine.publishing import export_cmd,export_delivery,approve_release,schedule_release,import_metrics


@pytest.mark.parametrize('volume',[float('nan'),float('inf'),-.1,.5])
def test_invalid_soft_music_gain_rejected(volume):
    with pytest.raises(ValueError):soft_music_filter(4,volume)


def test_explicit_music_off_ignores_saved_path_before_download(tmp_path,monkeypatch):
    import engine.clipping as module
    reached=[]
    def stop(*args,**kwargs):
        reached.append(True);raise RuntimeError('stop before media')
    monkeypatch.setattr(module,'resolve_input',stop)
    with pytest.raises(RuntimeError,match='stop before'):
        module.create_highlight_clips('owned.mp4',str(tmp_path),background_music='missing.wav',
                                      background_music_enabled=False,source_rights='own_content')
    assert reached
    with pytest.raises(ValueError,match='Choose'):
        module.create_highlight_clips('owned.mp4',str(tmp_path),background_music_enabled=True)


def test_soft_music_preserves_speech_level_and_stereo(ffmpeg_binary,ffmpeg_media,tmp_path):
    path=tmp_path/'mix.wav'
    cmd=[ffmpeg_binary,'-y','-v','error','-i',ffmpeg_media['voice'],'-stream_loop','-1','-i',ffmpeg_media['music'],
         '-filter_complex',soft_music_filter(4,.08),'-map','[aout]','-t','4','-c:a','pcm_s16le',str(path)]
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
    assert not result.returncode,result.stderr
    decoded=subprocess.run([ffmpeg_binary,'-v','error','-i',str(path),'-f','f32le','-'],capture_output=True,timeout=20)
    samples=np.frombuffer(decoded.stdout,dtype='<f4').reshape(-1,2)
    assert len(samples)==4*48000
    t=np.arange(48000)/48000
    window=samples[48000:96000,0]
    amplitude=2*abs(np.mean(window*np.exp(-2j*np.pi*440*t)))
    assert amplitude==pytest.approx(.2/np.sqrt(2),abs=.005) # Equal-energy mono→stereo, with no extra amix normalization.
    assert np.sqrt(np.mean((samples[:,0]-samples[:,1])**2))>.00001


def test_export_profiles_no_source_overwrite_and_conservative_duration():
    cmd=export_cmd('source.mp4','delivery.mp4','instagram_reel',duration=30)
    assert '30' not in cmd # fps is inside the filter rather than a loose unvalidated flag.
    assert '128k' in cmd and 'fps=30' in cmd[cmd.index('-vf')+1]
    with pytest.raises(ValueError):export_cmd('source','out','youtube_short',duration=181)
    assert '1920:1080' in export_cmd('source','out','youtube_long',duration=300)[9]


def test_real_delivery_export_keeps_source_and_sets_review_state(ffmpeg_media,tmp_path):
    source=Path(ffmpeg_media['video']);before=digest(source)
    record=export_delivery(source,tmp_path/'delivery','instagram_reel',language='or',duration=4,title='ଆମର ଭଲ କାହାଣୀ')
    assert record['state']=='REVIEW_REQUIRED' and record['language']=='or'
    assert record['profile']['fps']==30 and digest(source)==before
    assert Path(record['video']).is_file() and record['sha256']==digest(record['video'])


def test_release_needs_explicit_audience_rights_and_unchanged_file(tmp_path):
    video=tmp_path/'video.mp4';video.write_bytes(b'approved render')
    path=tmp_path/'release.json';save(path,{'video':str(video),'sha256':digest(video),'state':'REVIEW_REQUIRED'})
    with pytest.raises(ValueError):approve_release(path,account_id='my-channel')
    approved=approve_release(path,account_id='my-channel',rights_confirmed=True,facts_reviewed=True,
                             language_reviewed=True,made_for_kids=False,ai_disclosure_required=True)
    assert approved['state']=='APPROVED_FOR_MANUAL_UPLOAD'
    scheduled=schedule_release(path,'2099-01-01T18:00:00+05:30')
    assert scheduled['state']=='SCHEDULED_MANUAL_REMINDER'
    assert 'No social API upload' in scheduled['notice']
    video.write_bytes(b'changed render')
    with pytest.raises(ValueError):approve_release(path,account_id='my-channel')


def test_metrics_import_keeps_native_metric_names(tmp_path):
    rows=[{'account_id':'mine','destination':'youtube_short','language':'hi','post_id':'p1',
           'measured_at':'2026-10-01','metrics':{'engaged_views':10,'average_view_duration_seconds':22.5}}]
    assert import_metrics(tmp_path/'metrics.json',rows)['rows']==1
    assert read(tmp_path/'metrics.json')['rows'][0]['metrics']==rows[0]['metrics']
    rows[0]['metrics']['engaged_views']=float('nan')
    with pytest.raises(ValueError):import_metrics(tmp_path/'bad.json',rows)
