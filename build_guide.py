#!/usr/bin/env python3
"""Write the guide pages of the site: start.html (the landing page), concepts.html (a primer on the internals the
results depend on) and takeaways.html (what the results mean in practice). Numbers come from the result files."""
import json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = HERE / 'work4' / 'results'
tpl = (HERE / 'page' / 'template2.html').read_text()
STYLE = re.search(r'<style>.*?</style>', tpl, re.S).group(0)
FONTS = '\n'.join(l for l in tpl.splitlines() if 'fonts.g' in l)

# ---------- numbers ----------
def svc(f): return {s['id']: s for s in json.loads((R / f).read_text())['services']}
rounds = [svc(f) for f in ('r4_c_round3.json', 'r4_c_round4.json', 'r4_aot_round5.json', 'r4_aot_round6.json',
                           'r4_aotx_round7.json', 'r4_aotx_round8.json', 'r4_aotx_round9.json')]
soaks = [svc(f) for f in ('r4_c_soak.json', 'r4_c2_soak.json', 'r4_aot_soak.json')]
def med(xs):
    xs = sorted(xs); n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
def rm(k, f): return med([f(r[k]) for r in rounds if k in r])
def sm(k, f): return med([f(s[k]) for s in soaks if k in s])
ready = {k: rm(k, lambda x: x['startup']['ready_ms']) / 1000 for k in ('cs10', 'cs11', 'cs10aot', 'cs11aot', 'go', 'rust')}
idle = {k: rm(k, lambda x: x['idle']['mem_last_mb']) for k in ready}
early = {k: rm(k, lambda x: x['steady_stats']['cpu_median_pct']) for k in ready}
cpu = {k: sm(k, lambda x: x['stats']['cpu_median_pct']) for k in ready}
p99 = {k: sm(k, lambda x: x['soak']['ok_p99_ms']) for k in ready}
p50 = {k: sm(k, lambda x: x['soak']['ok_p50_ms']) for k in ready}
mx = {k: rm(k, lambda x: x['max']['good_rps']) for k in ready}
# .NET 10 vs 11 settled CPU: the two soaks where both ran in the same session (the AOT session's .NET 11 soak is not paired)
for k in ('cs10', 'cs11'): cpu[k] = (soaks[0][k]['stats']['cpu_median_pct'] + soaks[1][k]['stats']['cpu_median_pct']) / 2
net11_saving = (1 - round(cpu['cs11']) / round(cpu['cs10'])) * 100
aot_tp = (1 - mx['cs11aot'] / mx['cs11']) * 100

# CPU after a cold start, from the soaks (sampling starts 45 s after the container starts)
def cpu_series(src, k): return [(t + 45, c) for t, m, c in src[k]['stats']['series'] if t <= 120]
warm = [('cs11', 'C# .NET 11 · JIT', cpu_series(soaks[2], 'cs11'), 's2'),
        ('cs11aot', 'C# .NET 11 · NativeAOT', cpu_series(soaks[2], 'cs11aot'), 's1'),
        ('go', 'Go', cpu_series(soaks[0], 'go'), 's4')]

# ---------- diagrams ----------
ARROW = '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker></defs>'

def routes_svg():
    """four routes from source to machine code; the dashed line is where the program starts running"""
    W, rowh, top = 900, 64, 46
    split = 600
    rows = [('Rust', [('source', 0), ('rustc + LLVM', 1), ('native binary', 2)], [('runs at full speed', 3)]),
            ('Go', [('source', 0), ('go build', 1), ('native binary + GC', 2)], [('runs at full speed', 3)]),
            ('C# · JIT', [('source', 0), ('Roslyn', 1), ('IL in a .dll', 2)], [('Tier 0 → Tier 1', 3)]),
            ('C# · NativeAOT', [('source', 0), ('Roslyn → ILC', 1), ('native binary', 2)], [('runs at full speed', 3)])]
    xs = [120, 260, 410, 660]; bw = [110, 120, 160, 200]
    g = [ARROW,
         f'<line x1="{split}" y1="24" x2="{split}" y2="{top + rowh * 4 - 10}" stroke="currentColor" stroke-dasharray="4 4" opacity=".55"/>',
         f'<text x="{split - 10}" y="18" text-anchor="end" class="dl">BUILD TIME</text><text x="{split + 10}" y="18" class="dl">RUN TIME</text>']
    for i, (name, build, run) in enumerate(rows):
        y = top + i * rowh
        hot = name == 'C# · JIT'
        g.append(f'<text x="0" y="{y + 22}" class="dn">{name}</text>')
        boxes = build + run
        for j, (lab, col) in enumerate(boxes):
            x, w = xs[col], bw[col]
            fill = 'var(--hotbg)' if hot and col == 3 else 'var(--surface)'
            stroke = 'var(--blue)' if hot and col == 3 else 'currentColor'
            g.append(f'<rect x="{x}" y="{y}" width="{w}" height="34" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
                     f'<text x="{x + w / 2}" y="{y + 21}" text-anchor="middle" class="db">{lab}</text>')
            if j + 1 < len(boxes):
                nx = xs[boxes[j + 1][1]]
                g.append(f'<line x1="{x + w}" y1="{y + 17}" x2="{nx - 4}" y2="{y + 17}" stroke="currentColor" stroke-width="1.5" marker-end="url(#ah)"/>')
    y = top + 2 * rowh + 40
    g.append(f'<text x="{xs[3] + bw[3] / 2}" y="{y + 12}" text-anchor="middle" class="dl" fill="var(--blue)">COMPILES WHILE IT RUNS</text>')
    H = top + rowh * 4
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Rust, Go and NativeAOT C# finish compiling at build time; JIT C# ships IL and finishes compiling at run time, in two tiers.">'
            + ''.join(g) + '</svg>')

def warm_svg():
    W, H, L, B, T, Rm = 900, 320, 44, 34, 40, 12
    x0, x1, y1 = 45, 165, 110
    sx = lambda x: L + (x - x0) / (x1 - x0) * (W - L - Rm)
    sy = lambda y: T + (1 - min(y, y1) / y1) * (H - T - B)
    g = []
    for yt in (0, 25, 50, 75, 100):
        g.append(f'<line x1="{L}" x2="{W - Rm}" y1="{sy(yt):.1f}" y2="{sy(yt):.1f}" stroke="var(--grid2)"/>'
                 f'<text x="{L - 6}" y="{sy(yt) + 4:.1f}" text-anchor="end" class="tk">{yt}%</text>')
    for xt in (45, 75, 105, 135, 165):
        g.append(f'<text x="{sx(xt):.1f}" y="{H - 12}" text-anchor="middle" class="tk">{xt} s</text>')
    for k, lab, pts, slot in warm:
        path = ' '.join(f'{"M" if i == 0 else "L"}{sx(x):.1f},{sy(y):.1f}' for i, (x, y) in enumerate(pts))
        g.append(f'<path d="{path}" fill="none" stroke="var(--{slot})" stroke-width="2.2" stroke-linejoin="round"/>')
    lx = L
    for k, lab, pts, slot in warm:   # legend: the colour encoding repeats across three lines
        g.append(f'<rect x="{lx}" y="6" width="14" height="4" rx="1" fill="var(--{slot})"/><text x="{lx + 20}" y="13" class="dlab" fill="var(--{slot})">{lab}</text>')
        lx += 30 + len(lab) * 7.6
    jx = sx(89)
    g.append(f'<line x1="{jx:.1f}" x2="{jx:.1f}" y1="{T}" y2="{H - B}" stroke="currentColor" stroke-dasharray="3 4" opacity=".5"/>'
             f'<text x="{jx + 6:.1f}" y="{T + 12}" class="tk">≈ 90 s: JIT build settles</text>')
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="CPU after a cold start at 500 payments a second: the JIT build runs near 85 to 100 percent until about 90 seconds, then drops to about 52 percent; the NativeAOT build is near 51 percent from the start; Go stays near 42 percent.">'
            + ''.join(g) + '</svg>')

def load_svg():
    """closed loop: the next request waits for the answer; open loop: requests leave on schedule, so a stall is counted"""
    W, H = 900, 250
    stall = (330, 560)
    g = []
    def bar(x, end, y, late):
        g.append(f'<line x1="{x}" x2="{end}" y1="{y}" y2="{y}" stroke="{"var(--bad)" if late else "currentColor"}" stroke-width="{3 if late else 2}"/>'
                 f'<circle cx="{x}" cy="{y}" r="3.5" fill="currentColor"/>')
    def lane(y, h, title):
        g.append(f'<text x="0" y="{y - 10}" class="dn">{title}</text>')
        g.append(f'<rect x="{stall[0]}" y="{y}" width="{stall[1] - stall[0]}" height="{h}" fill="var(--hotbg)"/>'
                 f'<text x="{stall[1] - 8}" y="{y + 14}" text-anchor="end" class="tk">server stalls</text>')
    # closed loop: one request is caught in the stall and the client sends nothing else until it ends
    lane(26, 44, 'Closed loop: send, wait for the answer, send again')
    x, y = 20, 46
    while x < W - 40:
        late = stall[0] <= x < stall[1]
        d = stall[1] - x + 12 if late else 34
        bar(x, x + d, y, late)
        x += d + 21
    g.append(f'<text x="{stall[0] + 6}" y="{y + 15}" class="tk">1 slow request recorded</text>')
    # open loop: requests keep leaving on schedule; each one due during the stall waits for it to end
    lane(124, 104, 'Open loop: requests leave on a fixed schedule')
    y0, n = 150, 0
    for x in range(20, W - 20, 55):
        late = stall[0] <= x < stall[1]
        yy = y0 + (n * 14 if late else 0)
        if late: n += 1
        bar(x, stall[1] + 12 if late else x + 34, yy, late)
    g.append(f'<text x="{stall[1] + 18}" y="{y0 + 14 * (n - 1) + 4}" class="tk">{n} slow requests recorded</text>')
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="In a closed loop, one slow answer means fewer requests are sent, so the stall shows up as one slow request. In an open loop requests keep arriving on schedule, so every request due during the stall waits and is counted as slow.">'
            + ''.join(g) + '</svg>')

# ---------- shared page frame ----------
EXTRA = '''<style>
:root{--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--grid2:#e1e4de;--hotbg:#3a2cf214}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--grid2:#262b36;--hotbg:#8f86ff1f}}
:root[data-theme="dark"]{--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--grid2:#262b36;--hotbg:#8f86ff1f}
a{color:var(--blue)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chips a{font:700 10.5px var(--mono);letter-spacing:.04em;color:var(--ink);text-decoration:none;border:1.5px solid var(--hair);border-radius:999px;padding:3px 9px;background:var(--bg)}
.chips a:hover{border-color:var(--blue);color:var(--blue)}
.chips a.go{border-color:var(--blue);color:var(--blue)}
.watchcta{display:flex;gap:16px;align-items:center;padding:14px 18px;color:inherit;text-decoration:none;border-color:var(--blue)}
.watchcta:hover{box-shadow:4px 4px 0 var(--blue)}
.watchcta:focus-visible{outline:3px solid var(--blue);outline-offset:3px}
.watchcta .play{flex:none;width:44px;height:44px;border-radius:50%;background:var(--blue);clip-path:none;position:relative}
.watchcta .play::after{content:"";position:absolute;left:17px;top:13px;border-left:14px solid var(--surface);border-top:9px solid transparent;border-bottom:9px solid transparent}
.watchcta b{display:block;font-size:18px}
.watchcta small{display:block;color:var(--mute);font-size:14px}
/* start: stat tiles */
.tiles{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}
@media (max-width:1000px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:460px){.tiles{grid-template-columns:minmax(0,1fr)}}
.tile{padding:16px;display:flex;flex-direction:column;gap:6px;min-width:0}
.tile .n{font:800 clamp(30px,3.4vw,40px)/1 var(--disp);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.tile .n small{font-size:.5em;font-weight:700;color:var(--mute);margin-left:2px}
.tile .c{font-size:14.5px;line-height:1.35;flex:1}
.tile .vs{font:500 11px var(--mono);color:var(--mute)}
/* start: the gap chart */
.gap{padding:20px}
.gap svg{width:100%;height:auto;display:block;color:var(--ink);min-width:560px}
.gap .scroll{overflow-x:auto}
/* start: route */
.route{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;counter-reset:r}
@media (max-width:1000px){.route{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:560px){.route{grid-template-columns:minmax(0,1fr)}}
.stop{padding:16px;display:flex;flex-direction:column;gap:8px;color:inherit;text-decoration:none;min-width:0}
.stop:hover{box-shadow:4px 4px 0 var(--ink)}
.stop:focus-visible{outline:3px solid var(--blue);outline-offset:3px}
.stop h3{margin:0;font-size:20px;line-height:1.15}
.stop p{margin:0;font-size:14.5px;color:var(--mute);flex:1}
.stop .adds{font:700 10.5px var(--mono);letter-spacing:.04em;color:var(--ink)}
.stop .adds b{color:var(--blue)}
.realism{display:flex;gap:3px}
.realism i{height:5px;flex:1;border-radius:2px;background:var(--hair)}
.realism i.on{background:var(--blue)}
/* concepts */
.toc{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.cgroup{display:flex;flex-direction:column;gap:12px}
.cgroup>h2{font-size:clamp(20px,2.6vw,24px)}
.cgrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
@media (max-width:1000px){.cgrid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){.cgrid{grid-template-columns:minmax(0,1fr)}}
.concept{padding:18px;display:flex;flex-direction:column;gap:8px;scroll-margin-top:70px;min-width:0}
.concept.wide{grid-column:1/-1}
.concept h3{margin:0;font-size:19px;line-height:1.2}
.concept p{margin:0;font-size:15px;max-width:68ch}
.concept .why{border-left:3px solid var(--blue);padding-left:10px}
.concept .why b{font:700 10.5px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--blue);display:block;margin-bottom:2px}
figure.dg{margin:6px 0 0;min-width:0}
figure.dg .scroll{overflow-x:auto}
figure.dg svg{width:100%;min-width:620px;height:auto;display:block;color:var(--ink)}
figure.dg figcaption{color:var(--mute);font-size:13.5px;margin-top:6px;max-width:72ch}
.dn{font:700 13px var(--disp);fill:currentColor}
.db{font:500 12px var(--mono);fill:currentColor}
.dl{font:700 10.5px var(--mono);letter-spacing:.1em;fill:var(--mute)}
.dlab{font:700 12px var(--mono)}
.tk{font:500 11px var(--mono);fill:var(--mute)}
.big{font:800 26px var(--disp);fill:currentColor}
/* takeaways */
.dec{width:100%;border-collapse:collapse}
.dec td{padding:14px 16px;border-top:1px solid var(--hair);vertical-align:top;font-size:15px}
.dec tr:first-child td{border-top:0}
.dec td:first-child{font-weight:700;width:28%}
.dec td.pick{width:22%}
.dec .p{display:inline-block;font:700 11px var(--mono);letter-spacing:.04em;padding:4px 8px;border-radius:6px;background:var(--hotbg);color:var(--blue);white-space:nowrap}
.dec .ev{color:var(--mute)}
.decw{overflow-x:auto}
.decw table{min-width:640px}
.holds{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
@media (max-width:1000px){.holds{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:520px){.holds{grid-template-columns:minmax(0,1fr)}}
.holds div{border-top:3px solid var(--ink);padding-top:8px}
.holds b{display:block;font-size:16px;line-height:1.25}
.holds span{color:var(--mute);font-size:14px}
.next{margin:12px 0 0;padding:0;list-style:none;display:flex;flex-wrap:wrap;gap:8px}
.next li{border:1.5px solid var(--hair);border-radius:999px;padding:6px 12px;background:var(--bg);font-size:14px}
.next b{font-weight:700}
details.method summary{font:700 13px var(--mono);cursor:pointer}
details.method p{margin:8px 0 0;max-width:72ch;font-size:15px}
</style>'''

def page(title, body):
    return f'<title>{title}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n{FONTS}\n{STYLE}\n{EXTRA}\n<div class="wrap">\n{body}\n</div>\n'

SHORT = {'aot-vs-jit': 'AOT vs JIT', 'tiering': 'Tiered JIT', 'pgo': 'Dynamic PGO', 'r2r': 'ReadyToRun', 'nativeaot': 'NativeAOT',
         'simd': 'SIMD', 'bounds': 'Bounds checks', 'devirt': 'Devirtualisation', 'async': 'Runtime async', 'regalloc': 'Register spills',
         'gc': 'Garbage collection', 'footprint': 'Footprint', 'tail': 'Tail latency', 'openloop': 'Open-loop load', 'coldstart': 'Cold start', 'cpulimit': 'CPU limits'}
def chips(*ids):
    return '<div class="chips">' + ''.join(f'<a href="concepts.html#{i}">{SHORT[i]}</a>' for i in ids) + '</div>'
SETLINK = {1: ('probes.html', 'Set 1'), 2: ('net11.html', 'Set 2'), 3: ('load.html', 'Set 3'), 4: ('containers.html', 'Set 4')}

# ---------- concepts: one line on what it is, one on why it matters, links to where it shows up ----------
CONCEPTS = [
 ('Getting to machine code', [
  ('aot-vs-jit', 'Ahead-of-time vs just-in-time', 'Rust and Go compile to machine code at build time. C# ships IL and the runtime\'s JIT compiles it while the program runs.',
   'Run-time compiling costs CPU at start-up but can optimise for the traffic it actually sees.', (1, 4), 'routes'),
  ('tiering', 'Tiered compilation', 'The JIT first compiles each method quickly (Tier 0), then recompiles the hot ones with full optimisation (Tier 1).',
   'Until hot code reaches Tier 1, the service is slower and uses more CPU. Here that took about 90 s under load.', (1, 4), 'warm'),
  ('pgo', 'Dynamic PGO', 'Before Tier 1, the JIT records which types and branches really occur, then specialises the code for them. On by default since .NET 8.',
   'It is why warm JIT code can beat ahead-of-time code.', (1, 4), None),
  ('r2r', 'ReadyToRun', 'A publish option that ships precompiled code next to the IL, so less starts at Tier 0.',
   'Shorter start-up and warm-up, PGO kept, bigger binaries.', (1, 2), None),
  ('nativeaot', 'NativeAOT', 'Publishes the app as one native executable: no IL, no JIT, unused code removed.',
   'Go-like start-up and memory, no warm-up. No PGO, and reflection-heavy libraries need source generators.', (3, 4), None),
 ]),
 ('What optimisers do', [
  ('simd', 'SIMD vectorisation', 'Using CPU instructions that process 4–16 numbers at once.',
   'A loop can get 4–8× faster with no source change. LLVM does it automatically; in C# you ask for it with <span class="code-in">Vector&lt;T&gt;</span>.', (1,), None),
  ('bounds', 'Bounds-check elimination', 'Deleting an array index check when the compiler can prove it always passes.',
   'Leftover checks cost a branch each and block vectorisation.', (1, 2), None),
  ('devirt', 'Devirtualisation', 'Replacing an interface or virtual call with a direct, often inlined, call when the type is known.',
   'Abstractions become nearly free when the compiler can see through them.', (2,), None),
  ('async', 'Runtime async', 'In .NET 11 the runtime, not a compiler-generated class, tracks where an async method paused.',
   'Awaits that finish immediately get 4× cheaper and stop allocating. Off by default in RC2.', (2,), None),
  ('regalloc', 'Register spills', 'When values do not fit in CPU registers, the compiler parks them in memory and reloads them.',
   'Fewer instructions can still be slower. Only timing tells.', (2,), None),
 ]),
 ('Memory', [
  ('gc', 'Garbage collection', 'C# and Go free unused memory automatically by pausing or running a collector. Rust frees memory when its owner goes away.',
   'Collections show up as latency spikes and as memory headroom.', (3,), None),
  ('footprint', 'Footprint', 'Memory held before any traffic, and the size of the image a node must pull.',
   'It decides how many instances fit on a node and how fast a new one can start.', (4,), None),
 ]),
 ('Reading the numbers', [
  ('tail', 'Percentiles', 'p50 is the median. p99 means 1 request in 100 was slower than this.',
   'Users feel the tail: a page that makes 20 backend calls hits their p99 on about 1 load in 5.', (3, 4), None),
  ('openloop', 'Open-loop load', 'Requests are sent on a fixed schedule and timed from when they were due, as real traffic would be.',
   'Tests that wait for each answer hide stalls. See the drawing below.', (3, 4), 'load'),
  ('coldstart', 'Cold start', 'Time from launching the process to its first answered request.',
   'It sets how fast you recover from a crash and scale out.', (4,), None),
  ('cpulimit', 'CPU limits', 'A one-CPU container gets one core\'s worth of time per second. 100% means all of it.',
   'CPU per request is a large part of compute cost, alongside memory, instance size and how capacity is billed. At the limit, extra work turns into queueing and latency.', (4,), None),
 ]),
]

FIGS = {
 'routes': (routes_svg(), 'Only JIT C# is still compiling after the program starts.'),
 'warm': (warm_svg(), 'CPU of one container at 500 payments/s after a cold start (set 4 soaks).'),
 'load': (load_svg(), 'Same stall. The open-loop client counts every request that was waiting, as users would.'),
}

def concept_html(cid, title, what, why, sets, fig):
    f = ''
    if fig:
        svg, cap = FIGS[fig]
        f = f'<figure class="dg"><div class="scroll">{svg}</div><figcaption>{cap}</figcaption></figure>'
    links = '<div class="chips">' + ''.join(f'<a class="go" href="{SETLINK[n][0]}">{SETLINK[n][1]} →</a>' for n in sets) + '</div>'
    return (f'<section class="card concept{" wide" if fig else ""}" id="{cid}" aria-labelledby="{cid}-h"><h3 id="{cid}-h">{title}</h3>'
            f'<p>{what}</p><p class="why"><b>Why it matters</b>{why}</p>{f}{links}</section>')

concepts_body = f'''  <header>
    <div class="eyebrow">Concepts</div>
    <h1>What happens <em>under your code</em></h1>
    <p class="lede">Sixteen ideas the results depend on, two lines each. Jump to the one you need.</p>
    <nav class="toc chips" aria-label="Concepts">{''.join(f'<a href="#{cid}">{SHORT[cid]}</a>' for _, items in CONCEPTS for cid, *_ in items)}</nav>
  </header>
''' + ''.join(f'''  <div class="cgroup"><h2>{g}</h2><div class="cgrid">
{''.join(concept_html(*c) for c in items)}
  </div></div>
''' for g, items in CONCEPTS)

# ---------- start page: one finding, three supporting numbers, four experiments, two ways in ----------
captured = 3491292   # set 4 clean rounds and soaks, from build_page4's integrity totals
GAP = [('01 · Array sum', 'time per element · set 1', 0.763 / 0.104, 's1', 'probes.html'),
       ('03 · In-memory API', 'requests per second · set 3', 43420 / 34425, 's3', 'load.html'),
       ('04 · With a database', 'median latency · set 4', max(p50.values()) / min(p50.values()), 's4', 'containers.html')]
gap_rows = ''.join(f"""<a class="grow" href="{h}"><div class="gtop"><b>{n}</b><span class="gx">{(f"{v:.1f}" if v > 5 else f"{v:.2f}")}×</span></div>
      <div class="gbar" role="img" aria-label="{n}: {v:.2f} times apart"><i style="width:{(v - 1) / 7 * 100 + 1.5:.1f}%;background:var(--{c})"></i></div><small>{m}</small></a>""" for n, m, v, c, h in GAP)
STATS = [('Cold start', f"{ready['cs11aot']:.2f}", 's', 'Native AOT ready', f"Against {ready['cs11']:.2f} s for the JIT build, in a one-CPU container.", 'containers.html#ah', 'See start-up results', 's1'),
         ('Steady traffic', f"{net11_saving:.0f}", '% less', 'CPU on .NET 11 RC2', f"{cpu['cs10']:.0f}% → {cpu['cs11']:.0f}% of a CPU against .NET 10, same service and traffic. Measured in two paired soaks; individual runs ranged {(1 - soaks[0]['cs11']['stats']['cpu_median_pct'] / soaks[0]['cs10']['stats']['cpu_median_pct']) * 100:.0f}–{(1 - soaks[1]['cs11']['stats']['cpu_median_pct'] / soaks[1]['cs10']['stats']['cpu_median_pct']) * 100:.0f}%.", 'containers.html#sh', 'See CPU measurements', 's3'),
         ('Correctness under failure', f"{captured / 1e6:.2f}", 'M', 'payments accounted for', 'Every captured payment appeared exactly once in a merchant balance, in every run, including a provider outage.', 'containers.html#dh', 'See ledger checks', 's2')]
stats = ''.join(f"""<article class="card stat" style="border-top-color:var(--{c})"><span class="eyebrow">{e}</span><div class="sn">{n}<small>{u}</small></div><b>{t}</b><p>{d}</p><a href="{h}">{l} →</a></article>""" for e, n, u, t, d, h, l, c in STATS)
EXP = [('probes.html', 'Start with the instructions', 'What did the compiler actually produce?', 'Five small functions, the machine code behind each number, SIMD and bounds checks.', 'Explore machine code'),
       ('net11.html', "Test the runtime's claims", 'Did .NET 11 deliver its optimisations?', 'Six claims measured: two large wins, one opt-in, one regression, two no-shows.', 'Inspect .NET 11 results'),
       ('load.html', 'Add HTTP and JSON', 'What survives when an API gets busy?', 'Throughput, CPU per request, garbage collection, memory and tail latency.', 'Explore load tests'),
       ('containers.html', 'Add the system around it', 'What happens when the payment provider fails?', 'One CPU per container, Postgres, Redis and a simulated provider: timeouts, recovery and ledger consistency.', 'See the payment experiment')]
SURPRISE = [('Same runtime, opposite results', '.NET 11 RC2 used about 11% <b>more</b> CPU per request than .NET 10 in the plain in-memory API, and 26% <b>less</b> in the payment service. One workload does not predict another.', [('Set 3', 'load.html#th'), ('Set 4', 'containers.html#sh')], 's2'),
            ('Fewer instructions, slower code', '.NET 11 turns Math.BigMul into a single multiply instruction, cutting the loop from 25 to 20 instructions, and the loop runs 31% slower: the running total now spills to the stack.', [('Read the listing', 'net11.html#bigmul')], 's1'),
            ('One run that hung', 'In one of five rounds, .NET 10 Native AOT stopped answering during the provider outage: 14,812 requests timed out at low CPU. Three repeats with extra diagnostics were clean; the cause is still open.', [('See the run', 'containers.html#ah')], 's3')]
surprises = ''.join(f"""<article class="card sur" style="border-left-color:var(--{c})"><h3>{t}</h3><p>{d}</p><div class="sl">{''.join(f'<a href="{h}">{l} →</a>' for l, h in links)}</div></article>""" for t, d, links, c in SURPRISE)
exps = ''.join(f"""<a class="card exp" href="{h}"><span class="num">{i + 1:02d}</span><div><span class="eyebrow">{e}</span><h3>{q}</h3><p>{d}</p><span class="go">{l} →</span></div></a>""" for i, (h, e, q, d, l) in enumerate(EXP))

START_CSS = """<style>
:root{--find:#172039;--findink:#eef0f7;--findmute:#a7afc2;--findtrack:#2a3350;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#9fd36b}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--find:#1d2333;--findink:#e9ecf3;--findmute:#9aa2b4;--findtrack:#2c3446;--s4:#8fbf5f}}
:root[data-theme="dark"]{--find:#1d2333;--findink:#e9ecf3;--findmute:#9aa2b4;--findtrack:#2c3446;--s4:#8fbf5f}
.hero{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);gap:40px;align-items:center}
@media (max-width:920px){.hero{grid-template-columns:minmax(0,1fr);gap:24px}}
.hero h1{font-size:clamp(40px,5.6vw,66px);line-height:1;letter-spacing:-.035em;margin:10px 0 18px}
.hero h1 em{font-style:normal;color:var(--blue)}
.hero .q{font-size:18px;max-width:52ch;margin:0}
.hero .q b{font-weight:800}
.hero .note{color:var(--mute);font-size:14px;max-width:52ch;margin:12px 0 0}
.ctas{display:flex;flex-wrap:wrap;gap:10px;margin-top:22px}
.btn{display:inline-flex;align-items:center;gap:10px;font:700 15px var(--disp);text-decoration:none;border-radius:8px;padding:12px 18px;border:1.5px solid var(--ink);color:var(--ink);background:var(--surface)}
.btn.primary{background:var(--blue);border-color:var(--blue);color:var(--surface)}
.btn:hover{box-shadow:3px 3px 0 var(--ink)}
.btn:focus-visible{outline:3px solid var(--blue);outline-offset:3px}
.find{background:var(--find);color:var(--findink);border-radius:18px;padding:26px 28px;box-shadow:8px 8px 0 color-mix(in srgb,var(--ink) 14%,transparent)}
.find .head{display:flex;justify-content:space-between;align-items:center;gap:10px;border-bottom:1px solid var(--findtrack);padding-bottom:14px}
.find .head span{font:700 11px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--findmute)}
.find .head em{font:700 11px var(--mono);font-style:normal;border:1px solid var(--findtrack);border-radius:999px;padding:4px 10px;color:var(--findink)}
.find h2{color:var(--findink);font-size:26px;margin:18px 0 6px}
.grow{display:block;color:inherit;text-decoration:none;padding:12px 0}
.grow:hover .gtop b{text-decoration:underline}
.gtop{display:flex;justify-content:space-between;align-items:baseline}
.gtop b{font:700 12px var(--mono);letter-spacing:.06em;text-transform:uppercase}
.gx{font:800 24px var(--disp);font-variant-numeric:tabular-nums}
.gbar{height:10px;background:var(--findtrack);border-radius:5px;margin:8px 0 6px;overflow:hidden}
.gbar i{display:block;height:100%;border-radius:5px}
.grow small{font:500 12px var(--mono);color:var(--findmute)}
.find .scale{display:flex;justify-content:space-between;font:500 12px var(--mono);color:var(--findmute);margin-top:4px}
.find .careful{border-top:1px solid var(--findtrack);margin:16px 0 0;padding-top:14px;font-size:14px;color:var(--findmute)}
.find .careful b{color:var(--findink)}
.sechead{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,22rem);gap:24px;align-items:end}
@media (max-width:820px){.sechead{grid-template-columns:minmax(0,1fr);gap:6px}}
.sechead h2{font-size:clamp(26px,3.4vw,36px);margin:4px 0 0}
.sechead p{margin:0;color:var(--mute);font-size:15px}
.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
@media (max-width:900px){.stats{grid-template-columns:minmax(0,1fr)}}
.stat{padding:20px 22px;border-top:4px solid;display:flex;flex-direction:column;gap:6px;border-color:var(--hair)}
.sn{font:800 46px/1 var(--disp);letter-spacing:-.03em;font-variant-numeric:tabular-nums;margin-top:6px}
.sn small{font-size:22px;font-weight:700;margin-left:4px}
.stat b{font-size:18px}
.stat p{margin:0;color:var(--mute);font-size:14.5px;flex:1}
.stat a,.exp .go,.panel a{font:700 13px var(--mono);color:var(--blue);text-decoration:none}
.stat a:hover,.panel a:hover{text-decoration:underline}
.exps{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
@media (max-width:820px){.exps{grid-template-columns:minmax(0,1fr)}}
.exp{display:grid;grid-template-columns:auto minmax(0,1fr);gap:16px;padding:22px;color:inherit;text-decoration:none;border-color:var(--hair)}
.exp:hover{border-color:var(--ink);box-shadow:4px 4px 0 var(--ink)}
.exp:focus-visible{outline:3px solid var(--blue);outline-offset:3px}
.exp .num{font:700 12px var(--mono);color:var(--blue);background:var(--hotbg);border-radius:6px;padding:6px 8px;height:fit-content}
.exp h3{font-size:22px;line-height:1.2;margin:6px 0 6px}
.exp p{margin:0 0 14px;color:var(--mute);font-size:15px;max-width:48ch}
.ways{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr);gap:14px}
@media (max-width:820px){.ways{grid-template-columns:minmax(0,1fr)}}
.panel{padding:22px;display:flex;flex-direction:column;gap:6px;border-color:var(--hair)}
.panel.watch{display:grid;grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);gap:20px;padding:0;overflow:hidden}
@media (max-width:520px){.panel.watch{grid-template-columns:minmax(0,1fr)}}
.panel.watch .thumb{background:#10131a center/cover no-repeat;min-height:170px;display:grid;place-items:center;text-decoration:none}
.panel.watch .thumb span{width:58px;height:58px;border-radius:50%;background:var(--blue);display:grid;place-items:center;color:#fff;font-size:22px}
.panel.watch > div{padding:22px 22px 22px 0;display:flex;flex-direction:column;gap:6px}
@media (max-width:520px){.panel.watch > div{padding:0 22px 22px}}
.panel h3{margin:4px 0 0;font-size:22px;line-height:1.2}
.panel p{margin:0 0 8px;color:var(--mute);font-size:15px}
.surs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
@media (max-width:900px){.surs{grid-template-columns:minmax(0,1fr)}}
.sur{padding:20px 22px;border-left:5px solid;border-color:var(--hair);display:flex;flex-direction:column;gap:8px}
.sur h3{margin:0;font-size:20px;line-height:1.2}
.sur p{margin:0;color:var(--mute);font-size:15px;flex:1}
.sur p b{color:var(--ink)}
.sur .sl{display:flex;gap:16px;flex-wrap:wrap}
.sur a{font:700 13px var(--mono);color:var(--blue);text-decoration:none}
.sur a:hover{text-decoration:underline}
.foot{display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;border-top:1px solid var(--hair);padding-top:16px;font:500 12px var(--mono);color:var(--mute)}
.foot a{color:var(--ink);font-weight:700;text-decoration:none;margin-left:14px}
</style>"""

start_body = START_CSS + f"""  <section class="hero">
    <div>
      <div class="eyebrow">Rust · Go · C# · four sets of tests</div>
      <h1>A <em>{GAP[0][2]:.1f}×</em> gap in a loop. Just <em>{GAP[2][2]:.2f}×</em> with a database.</h1>
      <p class="q"><b>So when does faster code actually make a faster service?</b> We followed the question from the machine instructions a compiler emits to a payment API in containers, testing Rust, Go, .NET 10, .NET 11 RC2 and Native AOT.</p>
      <p class="note">The two ratios measure different things: time per array element, and median request latency with a database in the path. They show why context matters, not that every language performs the same.</p>
      <div class="ctas"><a class="btn primary" href="probes.html">Explore the experiments →</a><a class="btn" href="watch.html">▶ Watch the explainer</a></div>
    </div>
    <aside class="find" aria-labelledby="fh2">
      <div class="head"><span>The main finding</span><em>4 test sets</em></div>
      <h2 id="fh2">The gap changes with the workload.</h2>
      {gap_rows}
      <div class="scale"><span>1× = equal</span><span>8×</span></div>
      <p class="careful"><b>Read this carefully:</b> each ratio compares the fastest and slowest build in its own test. The metrics differ, so these are not interchangeable speed-ups.</p>
    </aside>
  </section>
  <section style="display:flex;flex-direction:column;gap:16px" aria-labelledby="nh2">
    <div class="sechead"><div><span class="eyebrow">Three supporting measurements</span><h2 id="nh2">The numbers behind the story</h2></div><p>Different workloads reveal different strengths. Each number links to the experiment that produced it.</p></div>
    <div class="stats">{stats}</div>
  </section>
  <section style="display:flex;flex-direction:column;gap:16px" aria-labelledby="uh2">
    <div class="sechead"><div><span class="eyebrow">Three results we did not expect</span><h2 id="uh2">Where the tests pushed back</h2></div><p>The findings that break a simple story. Each one is documented in full on its page.</p></div>
    <div class="surs">{surprises}</div>
  </section>
  <section style="display:flex;flex-direction:column;gap:16px" aria-labelledby="eh2">
    <div class="sechead"><div><span class="eyebrow">Go deeper · four experiments</span><h2 id="eh2">Follow the system as it gets more real</h2></div><p>Start wherever you are curious. Each page opens with its question and the concepts it uses.</p></div>
    <div class="exps">{exps}</div>
  </section>
  <section class="ways" aria-label="Two ways in">
    <div class="card panel watch"><a class="thumb" href="watch.html" style="background-image:url(explainer-poster.jpg)" aria-label="Play the explainer"><span>▶</span></a>
      <div><span class="eyebrow">Prefer to watch?</span><h3>See the investigation unfold.</h3><p>Under eight minutes, narrated, from a CPU graph that does not add up to a payment provider that fails on purpose.</p><a href="watch.html">Play the explainer →</a></div></div>
    <div class="card panel"><span class="eyebrow">Prefer to read?</span><h3>Start with the concepts, finish with the trade-offs.</h3><p>Two-line explanations of the internals, and a decision guide based on what the tests showed.</p><a href="concepts.html">Learn the concepts →</a><a href="takeaways.html">Read the takeaways →</a></div>
  </section>
  <footer class="foot"><span>One laptop. Four sets of tests. Results are specific to these workloads.</span><span><a href="takeaways.html#mh">Methods and limits</a><a href="takeaways.html">What it means</a></span></footer>
"""

# ---------- takeaways ----------
DECIDE = [
 ('Scale out often, scale to zero, short jobs', 'NativeAOT', f"Ready in {ready['cs11aot']:.2f} s and full speed from the first request. Check library support; build on Linux."),
 ('Long-lived service at high load', 'JIT (default)', f"Same CPU as AOT once warm and about {aot_tp:.0f}% more peak throughput (consistent across rounds). Hold readiness until warm, or add ReadyToRun."),
 ('Pack many instances per node', 'NativeAOT, or Go', f"Idle: Rust {idle['rust']:.1f} MB, Go {idle['go']:.0f} MB, C# AOT {idle['cs11aot']:.0f} MB, C# JIT {idle['cs11']:.0f} MB."),
 ('Planning the .NET 11 upgrade', 'Test on RC2 now', f"−{net11_saving:.0f}% CPU in the container service; slightly slower in a bare in-memory API. Recheck hot numeric loops."),
 ('Latency dominated by a database or another service', 'Keep your stack', f"Every build had a {min(p50.values()):.0f}–{max(p50.values()):.0f} ms median and failed the same way. Tune pools and timeouts instead."),
]
dec = ''.join(f'<tr><td>{a}</td><td class="pick"><span class="p">{b}</span></td><td class="ev">{c}</td></tr>' for a, b, c in DECIDE)

take_body = f'''  <header>
    <div class="eyebrow">Takeaways</div>
    <h1>What the numbers <em>mean for a service</em></h1>
    <p class="lede">Based on the container service in set 4: JSON over HTTP, a database, one downstream call to a simulated provider. Treat these as results for workloads shaped like it.</p>
  </header>
  <section class="card" aria-labelledby="dh">
    <div class="pad" style="padding-bottom:4px"><h2 id="dh">If this is your situation</h2></div>
    <div class="decw"><table class="dec">{dec}</table></div>
  </section>
  <section aria-labelledby="th" style="display:flex;flex-direction:column;gap:12px">
    <h2 id="th">What holds across all four sets</h2>
    <div class="holds">
      <div><b>Each compiler wins where its bet pays</b><span>LLVM: loops. RyuJIT: dynamic calls. Go: predictability.</span></div>
      <div><b>Realism compresses differences</b><span>Medians converge; start-up, memory and the tail do not.</span></div>
      <div><b>Defaults move results</b><span>Runtime async off, PGO on, server GC on.</span></div>
      <div><b>Read the machine code</b><span>It explained every claim that failed.</span></div>
    </div>
  </section>
  <section class="card pad" aria-labelledby="nh">
    <h2 id="nh">Not tested yet</h2>
    <ul class="next">
      <li><b>A real service</b>, its schema and hot endpoint</li>
      <li><b>Several replicas</b> behind a load balancer</li>
      <li><b>Bare-metal Linux</b> and a real network</li>
      <li><b>Runtime async + NativeAOT</b> together</li>
      <li><b>.NET 11 GA</b></li>
    </ul>
  </section>
  <section class="card pad" id="mh">
    <details class="method"><summary>How the numbers were made</summary>
      <p>One Intel i5-10300H laptop (4 cores, 8 threads), Windows 11, plugged in, nothing else running. Set 4 runs in Docker Desktop's Linux VM with 4 CPUs; each service gets 1 CPU and 512 MB.</p>
      <p>Out-of-the-box settings: cargo --release, go build, C# Release with server GC and tiered PGO. Opt-ins (runtime async, NativeAOT, Go PGO) are separate, labelled builds.</p>
      <p>Medians of repeated rounds. In sets 1–3 single runs varied by up to about 10%, so smaller gaps there are noise. Set 4 repeated each build in 2–5 rounds; a gap counts only when it is larger than the spread between those rounds (for example the 6% AOT vs JIT throughput gap, where rounds varied by 3% or less). Two one-off stalls did not recur and are reported as such.</p>
      <p>Set 4 is a realistic simulation, not a deployed system: the payment provider is a mock with injected delays and failures, and everything runs on one machine.</p>
      <p>.NET 10 (10.0.12 for the JIT builds), .NET 11.0.0-rc.2, Go 1.27.2, Rust 1.99.0, Postgres 17, Redis 7.</p>
    </details>
  </section>
'''


# ---------- watch page ----------
_starts = dict(l.split() for l in (HERE / 'video' / 'chapters2.txt').read_text().splitlines())   # written by video/remix2.sh
CHAPTERS = [(0, 'The CPU mystery', 'tiering', 'containers.html#kh')] + [(float(_starts[k]), t, c, e) for k, t, c, e in (
    ('A2Machine', 'Why the CPU dropped', 'tiering', 'containers.html#ah'), ('A3Loop', 'The same loop, two compilers', 'simd', 'probes.html'),
    ('A3Net11', 'What .NET 11 changes', 'devirt', 'net11.html#gvm'), ('A4Gap', 'Adding the real world', 'tail', 'load.html#qh'),
    ('A4Outage', 'Breaking the provider', 'cpulimit', 'containers.html#dh'), ('A4Load', 'How latency was measured', 'openloop', 'concepts.html#openloop'),
    ('A4Surprises', 'Results that pushed back', 'regalloc', 'start.html#uh2'),
    ('A5Deploy', 'Which one would you deploy?', 'nativeaot', 'containers.html#ah'), ('A5End', 'So which was fastest?', None, 'takeaways.html'))]
VIDEO_LEN = float(_starts['total'])
def mmss(t): return f"{int(t) // 60}:{int(t) % 60:02d}"
chap = ''.join(f'<li><button type="button" data-t="{c[0]}"><span class="ts">{mmss(c[0])}</span>{c[1]}</button>'
               + '<span class="cl">' + (f'<a href="concepts.html#{c[2]}">{SHORT[c[2]]}</a>' if c[2] else '') + f'<a class="ev" href="{c[3]}">Evidence →</a></span></li>' for c in CHAPTERS)
WATCH_CSS = """<style>
.player{padding:0;overflow:hidden}
.player video{display:block;width:100%;height:auto;aspect-ratio:16/9;background:#10131a}
.chap{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 24px}
@media (max-width:700px){.chap{grid-template-columns:minmax(0,1fr)}}
.chap li{display:flex;align-items:center;justify-content:space-between;gap:10px;border-top:1px solid var(--hair);padding:8px 0}
.chap button{all:unset;cursor:pointer;display:flex;gap:12px;align-items:baseline;font-size:15.5px;font-weight:700}
.chap button:hover{color:var(--blue)}
.chap button:focus-visible{outline:2px solid var(--blue);outline-offset:3px;border-radius:4px}
.chap button.on{color:var(--blue)}
.chap .ts{font:500 12px var(--mono);color:var(--mute);font-variant-numeric:tabular-nums;min-width:2.6em}
.chap a{font:700 10.5px var(--mono);letter-spacing:.04em;color:var(--mute);text-decoration:none;border:1.5px solid var(--hair);border-radius:999px;padding:2px 8px;white-space:nowrap}
.chap a:hover{color:var(--blue);border-color:var(--blue)}
.chap .cl{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.chap a.ev{color:var(--blue);border-color:var(--blue)}
.credit{color:var(--mute);font-size:14px;margin:0}
</style>"""
watch_body = f"""  <header>
    <div class="eyebrow">Watch · {int(VIDEO_LEN // 60)} min {int(VIDEO_LEN % 60)} s · narrated, with subtitles</div>
    <h1>C#, Rust and Go: <em>when does performance matter?</em></h1>
    <p class="lede">One investigation, told in four acts around a payment service, animated from the measured data and narrated. Turn on subtitles with the CC button.</p>
  </header>
  <section class="card player"><video id="vid" controls playsinline preload="metadata" poster="explainer-poster.jpg"><source src="explainer.mp4" type="video/mp4"><track id="subs" kind="subtitles" srclang="en" label="English">Your browser cannot play this video.</video></section>
  <section class="card pad" aria-labelledby="ch"><h2 id="ch">Chapters</h2><ol class="chap" style="margin-top:10px">{chap}</ol></section>
  <p class="credit">Animated with Manim Community (github.com/ManimCommunity/manim). Narration is synthesised with Kokoro-82M, an open-weight text-to-speech model. The music is an original ambient bed generated for this video. Every number is from the result files used on these pages.</p>
"""
WATCH_JS = f"""<script>
(() => {{
  const v = document.getElementById('vid'), bs = [...document.querySelectorAll('.chap button')];
  // subtitles ship as plain text; hand them to the track as a WebVTT blob
  fetch('explainer-vtt.txt').then(r => r.ok ? r.text() : Promise.reject()).then(t => {{
    document.getElementById('subs').src = URL.createObjectURL(new Blob([t], {{ type: 'text/vtt' }}));
  }}).catch(() => {{}});
  bs.forEach(b => b.addEventListener('click', () => {{ v.currentTime = +b.dataset.t + 0.05; v.play().catch(() => {{}}); }}));
  v.addEventListener('timeupdate', () => {{
    let cur = null; for (const b of bs) if (v.currentTime >= +b.dataset.t) cur = b;
    bs.forEach(b => b.classList.toggle('on', b === cur));
  }});
}})();
</script>"""
(HERE / 'watch.html').write_text(page('Compiler Probes Explainer', WATCH_CSS + '\n' + watch_body) + WATCH_JS + '\n')

(HERE / 'start.html').write_text(page('Compiler Probes', start_body))
(HERE / 'concepts.html').write_text(page('Compiler Probes Concepts', concepts_body))
(HERE / 'takeaways.html').write_text(page('Compiler Probes Takeaways', take_body))
print('guide ok', {k: round(v, 2) for k, v in ready.items()}, 'net11 saving', round(net11_saving), 'aot tp', round(aot_tp, 1))
