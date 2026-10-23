#!/usr/bin/env python3
"""Write the narration script and pronunciation guide (script/index.html) plus one audio clip per lexicon term.
Run with the venv python from this folder: ../../mvenv/bin/python build_script.py"""
import ast, html, re, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import soundfile as sf
from lexicon import LEXICON, PATTERN
import explainer2 as ex

OUT = HERE / 'script'; OUT.mkdir(exist_ok=True)
src = (HERE / 'explainer2.py').read_text()

# ---- the narration, in order: every caption(...) and speak(...) call in each scene, by line number
tree = ast.parse(src)
LINES = []
for cls in [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name[:1] == 'A' and n.name[1:2].isdigit()]:
    sect = next((st.value.value for st in cls.body if isinstance(st, ast.Assign) and getattr(st.targets[0], 'id', '') == 'act'), 'Opening' if cls.name == 'A1Hook' else 'Ending')
    calls = sorted((c for c in ast.walk(cls) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == 'say'
                    and c.args and isinstance(c.args[0], ast.Constant)), key=lambda c: c.lineno)
    for c in calls:
        text = c.args[0].value
        LINES.append((cls.name, sect, None, text))

eng = ex._engine()
def espeak(t): return eng.tokenizer.phonemize(t, ex.lang())

# ---- audio: each term inside a short carrier sentence, spoken with the pinned phonemes
rows = []
for i, (term, say, ipa, why) in enumerate(LEXICON):
    before = espeak(term)
    ph, _ = ex.phonemes(f'This is {term}.')
    a, sr = eng.create(ph, voice=ex.VOICE, speed=ex.SPEED, lang=ex.lang(), is_phonemes=True)
    wav = OUT / f't{i:02d}.wav'; sf.write(wav, a, sr)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(wav), '-af', 'loudnorm=I=-16:TP=-1.5', '-b:a', '96k', str(OUT / f't{i:02d}.mp3')], check=True)
    wav.unlink()
    rows.append((i, term, say, ipa, before, why))

def mark(t):
    return PATTERN.sub(lambda m: f'<mark>{html.escape(m.group(0))}</mark>', html.escape(t)).replace('&lt;mark&gt;', '<mark>')

lex_html = ''.join(
    f"<tr><td><b>{html.escape(t)}</b></td><td class='say'>{html.escape(s)}</td>"
    f"<td><audio controls preload='none' src='t{i:02d}.mp3'></audio></td>"
    + (f"<td class='ph'><span class='good'>{html.escape(p)}</span></td><td class='why'>The engine already says this right; pinned so it stays that way.</td></tr>" if b.strip() == p.strip() else
       f"<td class='ph'><span class='bad'>{html.escape(b)}</span><br><span class='good'>{html.escape(p)}</span></td><td class='why'><b>Fixed.</b> {html.escape(w)}</td></tr>")
    for i, t, s, p, b, w in rows)

cur, script_html, n = None, [], 0
for scene, sect, cap, said in LINES:
    if scene != cur:
        script_html.append(f"<h3>{html.escape(sect)}</h3>"); cur = scene
    n += 1
    ph, used = ex.phonemes(ex.spoken(said))
    script_html.append(f"<div class='line'><span class='n'>{n:02d}</span><div><p class='said'>{mark(said)}</p>"
                       + (f"<p class='cap'>On screen: {html.escape(cap)}</p>" if cap and cap != said else '')
                       + f"<details><summary>phonemes</summary><code>{html.escape(ph)}</code></details></div></div>")

page = f'''<title>Narration Script</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&family=JetBrains+Mono:wght@400;700&display=swap">
<style>
/* Layout: a working script; pronunciation table first, then every narrated line in order */
:root{{--bg:#f1f2ef;--surface:#fbfbf9;--ink:#141a2b;--mute:#646c7f;--hair:#d3d7d0;--acc:#3a2cf2;--good:#1b8a34;--bad:#c81d47;--hl:#3a2cf21c;
  --disp:"Bricolage Grotesque","Helvetica Neue",Arial,sans-serif;--mono:"JetBrains Mono",ui-monospace,Menlo,Consolas,monospace}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#11141b;--surface:#181c25;--ink:#e9ecf3;--mute:#9aa2b4;--hair:#2c3240;--acc:#8f86ff;--good:#5fd479;--bad:#ff6b8a;--hl:#8f86ff2a;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#11141b;--surface:#181c25;--ink:#e9ecf3;--mute:#9aa2b4;--hair:#2c3240;--acc:#8f86ff;--good:#5fd479;--bad:#ff6b8a;--hl:#8f86ff2a;color-scheme:dark}}
html,body{{background:var(--bg);color:var(--ink)}}
body{{font-family:var(--disp);line-height:1.5;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:28px}}
.wrap{{max-width:1040px;margin:0 auto;display:flex;flex-direction:column;gap:20px}}
.wrap>*{{min-width:0}}
h1{{font-size:clamp(32px,5vw,48px);line-height:1.05;margin:4px 0 8px;letter-spacing:-.02em;text-wrap:balance}}
h2{{font-size:24px;margin:0}}
h3{{font:700 11px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--mute);margin:22px 0 6px}}
.eyebrow{{font:700 12px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--mute)}}
.lede{{font-size:17px;max-width:66ch;margin:0}}
.card{{background:var(--surface);border:1.5px solid var(--ink);border-radius:14px;padding:20px}}
.sub{{color:var(--mute);margin:4px 0 12px;max-width:70ch}}
.tw{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;min-width:760px}}
th{{font:700 10.5px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--mute);text-align:left;padding:8px 10px;border-bottom:1.5px solid var(--ink)}}
td{{padding:10px;border-bottom:1px solid var(--hair);vertical-align:middle;font-size:15px}}
td.say{{font-weight:700;color:var(--acc)}}
td.ph{{font:400 12.5px var(--mono)}}
td.why{{color:var(--mute);font-size:14px}}
.bad{{color:var(--bad);text-decoration:line-through}} .good{{color:var(--good);font-weight:700}}
audio{{height:32px;max-width:200px}}
.line{{display:grid;grid-template-columns:2.4em minmax(0,1fr);gap:10px;padding:10px 0;border-top:1px solid var(--hair)}}
.line .n{{font:700 12px var(--mono);color:var(--mute);padding-top:4px}}
.said{{margin:0;font-size:17px;max-width:72ch}}
.cap{{margin:4px 0 0;color:var(--mute);font-size:14px}}
mark{{background:var(--hl);color:var(--acc);font-weight:700;border-radius:4px;padding:0 3px}}
details{{margin-top:4px}} summary{{cursor:pointer;font:700 11px var(--mono);color:var(--mute)}}
code{{font:400 12.5px var(--mono);overflow-wrap:anywhere}}
</style>
<div class="wrap">
  <header>
    <div class="eyebrow">Explainer video · voice {html.escape(ex.VOICE)}</div>
    <h1>Narration script and pronunciation guide</h1>
    <p class="lede">The voice is synthetic, so every technical term is pinned to exact phonemes before it is spoken. Play each term to check it. If one sounds wrong, change its phonemes in <code>lexicon.py</code> and only the lines that use it are re-spoken.</p>
  </header>
  <section class="card"><h2>Pronunciation lexicon</h2>
    <p class="sub">Where the engine got a term wrong, red shows what it would have said and green what the video uses.</p>
    <div class="tw"><table><tr><th>Term</th><th>Say it as</th><th>Listen</th><th>Phonemes, before → after</th><th>Why</th></tr>{lex_html}</table></div>
  </section>
  <section class="card"><h2>The script, line by line</h2>
    <p class="sub">{n} narrated lines in the order they play. Highlighted words use the lexicon. Where the caption on screen is shorter than the narration, it is shown underneath.</p>
    {''.join(script_html)}
  </section>
</div>
'''
(OUT / 'index.html').write_text(page)
print('script ok', len(rows), 'terms', n, 'lines')
