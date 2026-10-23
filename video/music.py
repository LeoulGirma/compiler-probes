#!/usr/bin/env python3
"""Synthesise an original, royalty-free ambient bed for the explainer: soft detuned pads on a slow
i–VI–III–VII progression in A minor, a sub bass, and a quiet plucked arpeggio. Nothing is sampled.
python music.py <seconds> <out.wav>"""
import sys
import numpy as np
import soundfile as sf

SR = 44100
dur = float(sys.argv[1]); out = sys.argv[2]
n = int(dur * SR); t = np.arange(n) / SR
rng = np.random.default_rng(7)
BPM = 84; beat = 60 / BPM; bar = 4 * beat

def hz(m): return 440.0 * 2 ** ((m - 69) / 12)
# Am, Fmaj7, C, G(add6) - two bars each
CHORDS = [[45, 57, 60, 64, 67], [41, 57, 60, 64, 65], [48, 55, 60, 64, 67], [43, 55, 59, 62, 64]]

def saw(f, tt, phase=0.0):
    return 2 * ((f * tt + phase) % 1.0) - 1

pad = np.zeros(n); sub = np.zeros(n); arp = np.zeros(n)
seg = 2 * bar
k = 0; start = 0.0
while start < dur:
    ch = CHORDS[k % 4]; s0 = int(start * SR); s1 = min(n, int((start + seg + 1.5) * SR))
    tt = t[s0:s1] - start
    env = np.minimum(1, tt / 1.8) * np.clip((seg + 1.5 - tt) / 1.8, 0, 1)   # slow swell, overlapping crossfade
    voice = np.zeros_like(tt)
    for m in ch[1:]:
        for det in (-0.07, 0.0, 0.07):
            voice += saw(hz(m) * 2 ** (det / 12), tt, rng.random()) * 0.06
    pad[s0:s1] += voice * env
    sub[s0:s1] += np.sin(2 * np.pi * hz(ch[0]) * tt) * 0.22 * env
    # arpeggio: chord tones an octave up, eighth notes, soft pluck
    step = beat / 2
    for j in range(int(seg / step)):
        if j % 8 in (3, 7) and rng.random() < 0.5: continue
        m = ch[1:][[0, 2, 1, 3][j % 4]] + 12
        a0 = s0 + int(j * step * SR); a1 = min(n, a0 + int(1.2 * SR))
        if a0 >= n: break
        ta = (np.arange(a1 - a0)) / SR
        arp[a0:a1] += np.sin(2 * np.pi * hz(m) * ta) * np.exp(-ta * 5.5) * 0.07
    start += seg; k += 1

# filter the pad in chunks (the loop filter is slow on 15M samples, so filter at a quarter rate and upsample)
q = 4
pd = pad[::q]; a = np.exp(-2 * np.pi * 900 / (SR / q)); y = np.empty_like(pd); acc = 0.0
for i in range(len(pd)):
    acc = (1 - a) * pd[i] + a * acc; y[i] = acc
pad = np.interp(np.arange(n), np.arange(0, n, q)[:len(y)], y)

mix = pad + sub + arp
# gentle stereo: delay the arpeggio a little on the right, plus a simple feedback echo
d = int(0.32 * SR)
echo = np.zeros(n); echo[d:] = arp[:-d] * 0.35
L = mix + echo * 0.6; Rr = mix + np.roll(echo, int(0.011 * SR)) * 0.9
fade = np.minimum(1, t / 3.0) * np.clip((dur - t) / 5.0, 0, 1)
st = np.stack([L * fade, Rr * fade], axis=1)
st /= np.max(np.abs(st)) / 0.8
sf.write(out, st.astype(np.float32), SR)
print('music', out, round(dur, 1), 's')
