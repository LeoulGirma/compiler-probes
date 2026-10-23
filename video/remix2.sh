#!/bin/bash
# v2 pipeline: render the five-act explainer with narration, build music to length, mix to -14 LUFS,
# write chapters + WebVTT subtitles from the narration cues, and a captioned copy for muted feeds.
set -e
cd "$(dirname "$0")"
SC="A1Hook A2Machine A3Loop A3Net11 A4Gap A4Outage A4Load A4Surprises A5Deploy A5End"
VOICE=${VOICE:-am_michael} ../../mvenv/bin/manim -r 1920,1080 --fps 30 --disable_caching explainer2.py ${ONLY:-$SC} > render2.log 2>&1
D=media/videos/explainer2/1080p30
: > $D/list.txt; for s in $SC; do echo "file '$s.mp4'" >> $D/list.txt; done
python3 - "$D" $SC <<'PY'
import json, subprocess, sys
D, scenes = sys.argv[1], sys.argv[2:]
t, chap, cues = 0.0, [], []
def ts(x): h = int(x // 3600); m = int(x % 3600 // 60); return f'{h:02d}:{m:02d}:{x % 60:06.3f}'
for s in scenes:
    d = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f'{D}/{s}.mp4']))
    chap.append(f'{s} {t:.1f}')
    for a, b, text in json.load(open(f'cues/{s}.json'))['cues']:
        # split long lines into caption-sized pieces, timed by word share
        words = text.split(); n = max(1, round(len(words) / 14)); per = (b - a) / len(words); i = 0
        for k in range(n):
            chunk = words[i:i + -(-len(words) // n)]; st = t + a + i * per; i += len(chunk); cues.append((st, t + a + i * per, ' '.join(chunk)))
    t += d
chap.append(f'total {t:.1f}')
open('chapters2.txt', 'w').write('\n'.join(chap) + '\n')
open('../site/explainer.vtt', 'w').write('WEBVTT\n\n' + '\n'.join(f'{i + 1}\n{ts(a)} --> {ts(b)}\n{x}\n' for i, (a, b, x) in enumerate(cues)))
srt = lambda x: ts(x).replace('.', ',')
open('captions.srt', 'w').write('\n'.join(f'{i + 1}\n{srt(a)} --> {srt(b)}\n{x}\n' for i, (a, b, x) in enumerate(cues)))
print('cues', len(cues), 'length', round(t, 1))
PY
T=$(tail -1 chapters2.txt | awk '{print $2}')
../../mvenv/bin/python music.py $(python3 -c "print($T+2)") music.wav
ffmpeg -v error -y -f concat -safe 0 -i $D/list.txt -i music.wav -filter_complex "\
[0:a]aresample=48000,highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=120:makeup=2,loudnorm=I=-16:TP=-2:LRA=7,aresample=48000[vo];\
[vo]asplit=2[vo1][vosc];[1:a]aresample=48000,equalizer=f=2800:t=q:w=1.2:g=-5,volume=-26dB[m];\
[m][vosc]sidechaincompress=threshold=0.03:ratio=4:attack=30:release=500[md];\
[vo1][md]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]" \
 -map 0:v -map "[a]" -c:v libx264 -preset slow -crf 29 -pix_fmt yuv420p -tune animation -movflags +faststart -c:a aac -b:a 160k ../site/explainer.mp4
ffmpeg -v error -y -i ../site/explainer.mp4 -vf "subtitles=captions.srt:force_style='FontName=Bricolage Grotesque,FontSize=15,PrimaryColour=&H00F3ECE9,OutlineColour=&H00101310,BorderStyle=3,Outline=6,Shadow=0,MarginV=28'" \
 -c:v libx264 -preset slow -crf 28 -pix_fmt yuv420p -tune animation -movflags +faststart -c:a copy explainer-captioned.mp4
ffmpeg -v error -y -ss 20 -i ../site/explainer.mp4 -frames:v 1 -vf scale=1280:-1 -q:v 4 ../site/explainer-poster.jpg
ls -la ../site/explainer.mp4 explainer-captioned.mp4; cat chapters2.txt
ffmpeg -hide_banner -i ../site/explainer.mp4 -af ebur128=peak=true -f null - 2>&1 | grep -A12 Summary | grep -E "I:|Peak:"
echo PIPELINE DONE
