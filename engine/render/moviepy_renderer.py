"""Bounded compatibility renderer that honours the exact presentation recipe.

No unsolicited title, transcript, progress bar or source-clip dialogue. Accepted
visuals retain their saved slots. This path does not claim loudness certification.
"""
from __future__ import annotations
from contextlib import ExitStack
from pathlib import Path


def render_moviepy(segments, narration, out_path, *, total, W=1080, H=1920,
                   music=None, ambience=None, sfx=None, overlays=None, words=None,
                   captions=False, music_volume=.1, quality="high"):
    from moviepy.editor import (VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip,
                                CompositeAudioClip, concatenate_videoclips, vfx, afx)
    from ..video_builder import _wordpop_events, _wordpop_png
    import tempfile

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as cleanup, tempfile.TemporaryDirectory(prefix='cards-', dir=Path(out_path).parent) as scratch:
        def own(clip):
            cleanup.callback(clip.close)
            return clip
        visuals = []
        for seg in segments:
            source = own(VideoFileClip(seg['src'], audio=False))
            start = float(seg.get('in', 0))
            duration = float(seg['dur'])+float(seg.get('freeze', 0))
            part = source.subclip(start, min(source.duration, start+duration))
            if part.duration + .01 < duration:
                part = part.fx(vfx.loop, duration=duration)
            part = part.set_duration(duration).without_audio()
            part = part.resize(max(W/part.w, H/part.h))
            part = part.crop(x_center=part.w/2, y_center=part.h/2, width=W, height=H)
            visuals.append(part)
        base = own(concatenate_videoclips(visuals, method='chain').set_duration(total))
        layers = [base]
        for event in overlays or []:
            if not event.get('path'):
                continue
            start, end = max(0, float(event['start'])), min(total, float(event['end']))
            if end <= start:
                continue
            layer = own(ImageClip(event['path']).set_start(start).set_duration(end-start))
            if event.get('fade_in'):
                layer = layer.crossfadein(min(float(event['fade_in']), (end-start)/2))
            if event.get('fade_out'):
                layer = layer.crossfadeout(min(float(event['fade_out']), (end-start)/2))
            layers.append(layer)
        if captions and narration and words:
            for index, ev in enumerate(_wordpop_events(words, total)):
                path = str(Path(scratch)/f'caption-{index}.png')
                _wordpop_png(ev['labels'], ev['active'], path, W)
                layers.append(own(ImageClip(path).set_start(ev['start']).set_duration(ev['end']-ev['start'])
                                  .set_position(('center', H*.64 if H > W else H*.74))))
        tracks = []
        if narration:
            track = own(AudioFileClip(narration))
            tracks.append(track.subclip(0, min(total, track.duration)))
        for path, volume in ((music, music_volume), (ambience, .06)):
            if path:
                track = own(AudioFileClip(path)).fx(afx.audio_loop, duration=total).volumex(volume)
                tracks.append(track)
        for event in sfx or []:
            if event.get('path'):
                track = own(AudioFileClip(event['path'])).volumex(float(event.get('vol', .5)))
                tracks.append(track.set_start(float(event.get('at', 0))))
        final = own(CompositeVideoClip(layers, size=(W, H)).set_duration(total))
        if tracks:
            audio = own(CompositeAudioClip(tracks).set_duration(total))
            final = final.set_audio(audio)
        else:
            final = final.without_audio()
        final.write_videofile(str(out_path), fps=24, codec='libx264', audio=bool(tracks),
                              audio_codec='aac', audio_bitrate='192k', preset='medium', threads=2, logger=None,
                              ffmpeg_params=['-crf', '18' if quality == 'high' else '23', '-pix_fmt', 'yuv420p'])
    return {'video': str(out_path), 'audio_present': bool(tracks), 'voiceover_enabled': bool(narration),
            'captions_requested': bool(captions and narration), 'overlays': len(overlays or []),
            'total': total, 'loudness_verified': False}
