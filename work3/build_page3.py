#!/usr/bin/env python3
"""Bake data3.json into page/payments-under-load.html (static HTML; bars are sized server-side)."""
import json, re
from html import escape as esc
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = json.loads((HERE / 'data3.json').read_text())
tpl = (HERE.parent / 'page' / 'template2.html').read_text()
STYLE = re.search(r'<style>.*?</style>', tpl, re.S).group(0)
FONTS = '\n'.join(l for l in tpl.splitlines() if 'fonts.g' in l)

S = {s['id']: s for s in D['servers']}
G = {g['id']: g for g in D['gc']}
ORDER = ['cs10', 'cs11', 'cs11ra', 'cs10aot', 'cs11aot', 'go', 'rust']
LAB = {'cs10': ('C# .NET 10', 'JIT'), 'cs11': ('C# .NET 11', 'RC2 · JIT'), 'cs11ra': ('C# .NET 11', 'JIT + runtime async'),
       'cs10aot': ('C# .NET 10', 'NativeAOT'), 'cs11aot': ('C# .NET 11', 'RC2 · NativeAOT'), 'go': ('Go', D['versions']['go'].split()[2]),
       'rust': ('Rust', 'axum · ' + D['versions']['rust'].split()[1])}
COLOR = {'cs10': 'cs10', 'cs11': 'cs11', 'cs11ra': 'csra', 'cs10aot': 'aot10', 'cs11aot': 'aot11', 'go': 'go', 'rust': 'rust'}
GLAB = {'cs10': ('C# .NET 10', 'workstation GC'), 'cs10srv': ('C# .NET 10', 'server GC'), 'cs11': ('C# .NET 11', 'workstation GC'),
        'cs11srv': ('C# .NET 11', 'server GC'), 'go': ('Go', 'concurrent GC'), 'rust': ('Rust', 'no GC')}
GCOL = {'cs10': 'cs10', 'cs10srv': 'aot10', 'cs11': 'cs11', 'cs11srv': 'aot11', 'go': 'go', 'rust': 'rust'}
med = lambda d: d['med']

def fmt(v, d=None):
    if v is None: return '—'
    if d is not None: return f'{v:,.{d}f}'
    return f'{v:,.0f}' if v >= 100 else f'{v:.1f}' if v >= 10 else f'{v:.2f}'

def bars(rows, title, unit, lower_better=False, per=1, d=None, log=False):
    """rows: [(key, label tuple, color token, stat dict)]"""
    vals = [(k, lab, col, st['med'] / per, st['min'] / per, st['max'] / per) for k, lab, col, st in rows]
    top = max(v[5] for v in vals) * 1.04
    best = (min if lower_better else max)(v[3] for v in vals)
    out = [f'<div class="unitline">{esc(title)}</div><div class="bars" role="img" aria-label="{esc(title)}: ' +
           '; '.join(f'{l[0]} {l[1]} {fmt(m, d)} {unit}' for _, l, _, m, _, _ in vals) + '">']
    for k, lab, col, m, lo, hi in vals:
        err = f'<div class="berr" style="left:{lo / top * 100:.2f}%;width:{(hi - lo) / top * 100:.2f}%"></div>' if hi > lo * 1.02 else ''
        star = ' <b class="best">best</b>' if m == best else ''
        out.append(f'<div class="brow"><div class="blab">{esc(lab[0])}<small>{esc(lab[1])}</small></div><div class="btrack" aria-hidden="true">'
                   f'<div class="bfill" style="width:{m / top * 100:.2f}%;background:var(--{col})"></div>{err}</div>'
                   f'<div class="bval">{fmt(m, d)}<small>{esc(unit)}{star}</small></div></div>')
    return ''.join(out) + '</div>'

srows = lambda f: [(k, LAB[k], COLOR[k], f(S[k])) for k in ORDER]
grows = lambda f: [(k, GLAB[k], GCOL[k], f(G[k])) for k in ['cs10', 'cs10srv', 'cs11', 'cs11srv', 'go', 'rust']]
cpu = lambda k: med(S[k]['closed']['server_cpu_ms_per_1k'])
rps = lambda k: med(S[k]['closed']['rps'])
o = lambda k, f: med(S[k]['open'][f])

# ---------------- copy ----------------
pct = lambda a, b: (a / b - 1) * 100
fastest = max(ORDER, key=rps); leanest = min(ORDER, key=cpu)
lede = (f"The same small payment API, written in C#, Go and Rust, built seven ways and load-tested on one laptop. "
        f"It parses a JSON payment, validates it, signs it with HMAC-SHA256, records it in an in-memory ledger and replies in JSON. "
        f"Throughput is closer than the language arguments suggest: the slowest build reaches {min(rps(k) for k in ORDER)/rps(fastest)*100:.0f}% of the fastest. "
        f"The bigger differences are memory, CPU per request, tail latency and how each runtime copes with a heap under pressure.")

board = [
 ('Most requests per second', f"{LAB[fastest][0]} at {rps(fastest):,.0f}/s, with .NET 10 NativeAOT ({rps('cs10aot'):,.0f}) and Go ({rps('go'):,.0f}) close enough "
   f"to call a tie, since runs varied by up to 15%. The C# JIT builds trail by {pct(rps(fastest), rps('cs10')):.0f}–{pct(rps(fastest), rps('cs11')):.0f}%."),
 ('Least CPU per request', f"{LAB[leanest][0]}: {cpu(leanest):.0f} µs. NativeAOT C# {cpu('cs10aot'):.0f}–{cpu('cs11aot'):.0f} µs, Go {cpu('go'):.0f} µs, "
   f"C# JIT {cpu('cs10'):.0f}–{cpu('cs11'):.0f} µs."),
 ('.NET 11 RC2 vs .NET 10', f"Slightly slower in this service: {pct(cpu('cs11'), cpu('cs10')):.0f}% more CPU per request with the JIT and "
   f"{pct(cpu('cs11aot'), cpu('cs10aot')):.0f}% with NativeAOT. Turning on runtime async brings the JIT build back to "
   f"{cpu('cs11ra'):.0f} µs, level with .NET 10."),
 ('Fastest typical response', f"Rust {o('rust','p50_us'):.0f} µs, Go {o('go','p50_us'):.0f} µs, NativeAOT C# about {o('cs11aot','p50_us'):.0f} µs, .NET 10 JIT {o('cs10','p50_us'):.0f} µs, "
   f".NET 11 JIT {o('cs11','p50_us'):.0f} µs, at a steady {D['rate']:,} requests a second. The C# JIT builds had the shortest tails, Go the longest."),
 ('Smallest memory', f"Rust peaks at {med(S['rust']['peak_mb']):.0f} MB under load, Go {med(S['go']['peak_mb']):.0f} MB, NativeAOT C# "
   f"{med(S['cs10aot']['peak_mb']):.0f}–{med(S['cs11aot']['peak_mb']):.0f} MB, JIT C# {med(S['cs10']['peak_mb']):.0f}–{med(S['cs11']['peak_mb']):.0f} MB."),
 ('Smallest thing to ship', f"Rust {med(S['rust']['exe_mb']):.1f} MB. Go and NativeAOT C# are both about 10 MB. "
   "JIT C# is a 0.1 MB app plus a .NET and ASP.NET runtime installed on the machine."),
 ('Heap under pressure', f"Go keeps typical stalls short but still stalls up to {med(G['go']['max_us'])/1000:.0f} ms. .NET server GC has the best throughput "
   f"and the best p99.9, but each collection freezes the program for about {med(G['cs10srv']['gc_pause_ms'])/med(G['cs10srv']['gc_gen0']):.0f} ms on average "
   f"(up to {med(G['cs10srv']['max_us'])/1000:.0f} ms). Workstation GC pauses for about {med(G['cs10']['gc_pause_ms'])/med(G['cs10']['gc_gen0']):.0f} ms at a time, but far more often. Rust never collects but its allocator makes it the slowest at this churn."),
]

rng = lambda st: f"{fmt(st['med'])} <small>{fmt(st['min'])}–{fmt(st['max'])}</small>"
open_rows = ''.join(
    f"<tr><td><span class='sw' style='background:var(--{COLOR[k]})'></span>{esc(LAB[k][0])} <small>{esc(LAB[k][1])}</small></td>"
    f"<td>{rng(S[k]['open']['p50_us'])}</td><td>{rng(S[k]['open']['p99_us'])}</td><td>{rng(S[k]['open']['p999_us'])}</td>"
    f"<td class='mute'>{fmt(o(k, 'send_lag_p99_us'))}</td></tr>" for k in ORDER)

foot_rows = ''.join(
    f"<tr><td><span class='sw' style='background:var(--{COLOR[k]})'></span>{esc(LAB[k][0])} <small>{esc(LAB[k][1])}</small></td>"
    f"<td>{fmt(med(S[k]['idle_mb']), 0)} MB</td><td>{fmt(med(S[k]['peak_mb']), 0)} MB</td><td>{fmt(med(S[k]['exe_mb']), 1)} MB</td>"
    f"<td class='mute'>{'needs the shared .NET + ASP.NET runtime' if k in ('cs10', 'cs11', 'cs11ra') else 'single file, nothing else to install'}</td></tr>" for k in ORDER)

gc_rows = ''.join(
    f"<tr><td><span class='sw' style='background:var(--{GCOL[k]})'></span>{esc(GLAB[k][0])} <small>{esc(GLAB[k][1])}</small></td>"
    f"<td>{fmt(med(G[k]['iter_per_s']), 0)}</td><td>{fmt(med(G[k]['p99_us']), 0)} µs</td><td>{fmt(med(G[k]['p999_us']), 0)} µs</td>"
    f"<td>{med(G[k]['max_us'])/1000:.0f} ms</td><td>{fmt(med(G[k]['over_10ms']), 0)}</td><td>{fmt(med(G[k]['peak_mb']), 0)} MB</td></tr>"
    for k in ['cs10', 'cs10srv', 'cs11', 'cs11srv', 'go', 'rust'])

rate = D['rate']
html = f'''<title>Payments Under Load</title>
<meta name="claude:viewport-fit-sides" content="cover">
{FONTS}
{STYLE}
<style>
:root{{--aot10:#b7791f;--aot11:#8a5a00}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--aot10:#e0a84a;--aot11:#f3c85a}}}}
:root[data-theme="dark"]{{--aot10:#e0a84a;--aot11:#f3c85a}}
.best{{font:700 9.5px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--good)}}
.two2{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:0}}
.two2>div{{padding:20px;min-width:0}}
.two2>div+div{{border-left:1.5px solid var(--hair)}}
@media (max-width:860px){{.two2{{grid-template-columns:minmax(0,1fr)}}.two2>div+div{{border-left:0;border-top:1.5px solid var(--hair)}}}}
.st td small{{font:500 11px var(--mono);color:var(--mute);margin-left:4px}}
.st td.mute{{color:var(--mute);font-size:12px}}
.qa td:first-child{{width:24%}}
.prose p{{margin:10px 0 0;max-width:68ch}}
</style>
<div class="wrap">
  <header>
    <div class="eyebrow">Compiler probes · set 3 · workload</div>
    <h1>One payment API, <em>seven builds</em>, one laptop</h1>
    <p class="lede">{esc(lede)}</p>
    <div class="meta"><span class="chip">Intel i5-10300H · Windows 11 · turbo on</span><span class="chip">server pinned to 2 cores · load generator on 1 core</span>
      <span class="chip">.NET {esc(D['versions']['dotnet10'])} · .NET {esc(D['versions']['dotnet11'])}</span><span class="chip">{esc(D['versions']['go'].split()[2])}</span>
      <span class="chip">rustc {esc(D['versions']['rust'].split()[1])}</span><span class="chip">medians of {D['rounds']} rounds</span></div>
  </header>

  <section class="card board" aria-labelledby="qh">
    <div class="pad" style="padding-bottom:6px"><h2 id="qh">The short version</h2></div>
    <table class="qa">{''.join(f'<tr><td><b>{esc(q)}</b></td><td>{esc(a)}</td></tr>' for q, a in board)}</table>
  </section>

  <section class="card" aria-labelledby="th">
    <div class="pad" style="padding-bottom:0"><h2 id="th">Throughput and CPU cost</h2>
      <p class="sub">64 keep-alive connections sending as fast as the server answers, for 10 seconds after a warm-up. 2% of requests fail validation and get a 422, as in real traffic. The thin line is the range across rounds.</p></div>
    <div class="two2">
      <div>{bars(srows(lambda s: s['closed']['rps']), 'Requests per second at saturation', 'req/s', d=0)}</div>
      <div>{bars(srows(lambda s: s['closed']['server_cpu_ms_per_1k']), 'Server CPU time per request', 'µs CPU', lower_better=True, d=0)}</div>
    </div>
  </section>

  <section class="card" aria-labelledby="lh">
    <div class="pad"><h2 id="lh">Latency at a steady {rate:,} requests per second</h2>
      <p class="sub">About a fifth of capacity, the load a well-sized production service runs at. Requests are sent on a fixed schedule and timed from when they were due, so a stalled server cannot hide the requests that queued behind it. The last column is how long the slowest 1% of requests waited for a free connection before they could even be sent.</p></div>
    <div class="two2" style="border-top:1.5px solid var(--hair)"><div>{bars(srows(lambda s: s['open']['p50_us']), 'Median response time', 'µs', lower_better=True, d=0)}</div>
      <div class="prose"><p style="margin-top:0">The median is rock steady: each build landed within a few microseconds of itself in all three rounds. Rust answers in {o('rust','p50_us'):.0f} µs and Go in {o('go','p50_us'):.0f} µs. NativeAOT C# and .NET 10's JIT sit together around {o('cs10','p50_us'):.0f} µs. .NET 11's JIT is the outlier at {o('cs11','p50_us'):.0f} µs, {pct(o('cs11','p50_us'), o('cs10','p50_us')):.0f}% slower than .NET 10, with or without runtime async.</p>
      <p>The tail is noisier: p99 moved by 2–3× between rounds for most builds, mostly as moments when all 64 connections were busy at once. Two patterns held in every round: the C# JIT builds had the shortest tails and Go the longest.</p></div></div>
    <div class="st"><table><tr><th>Build</th><th>p50 µs <small>range</small></th><th>p99 µs <small>range</small></th><th>p99.9 µs <small>range</small></th><th>Queueing p99 µs</th></tr>{open_rows}</table></div>
  </section>

  <section class="card" aria-labelledby="fh">
    <div class="pad"><h2 id="fh">Memory and what you ship</h2>
      <p class="sub">Working set measured by Windows: one second after start-up, and the peak during the load test.</p></div>
    <div class="st"><table><tr><th>Build</th><th>Idle</th><th>Peak under load</th><th>Executable</th><th>Deploy</th></tr>{foot_rows}</table></div>
  </section>

  <section class="card" aria-labelledby="gh">
    <div class="pad" style="padding-bottom:0"><h2 id="gh">A heap under pressure</h2>
      <p class="sub">A separate program keeps one million small orders alive (about 150 MB), then for 10 seconds allocates 200 short-lived orders and replaces 20 random long-lived ones per loop. Every loop is timed, so a pause shows up the way a request handler would feel it. Writing new objects into an old, large array is the hardest case for a generational collector, so treat this as a stress test, not a typical service.</p></div>
    <div class="two2">
      <div>{bars(grows(lambda g: g['max_us']), 'Longest single stall', 'ms', lower_better=True, per=1000, d=0)}</div>
      <div>{bars(grows(lambda g: g['iter_per_s']), 'Loops completed per second', 'loops/s', d=0)}</div>
    </div>
    <div class="st"><table><tr><th>Runtime</th><th>Loops/s</th><th>p99</th><th>p99.9</th><th>Worst</th><th>Stalls over 10 ms</th><th>Peak memory</th></tr>{gc_rows}</table></div>
    <div class="pad prose">
      <p>.NET's server GC finishes the most work and has the best p99.9, but every collection stops the program: {med(G['cs10srv']['gc_gen0']):.0f} collections in 10 seconds, about {med(G['cs10srv']['gc_pause_ms'])/med(G['cs10srv']['gc_gen0']):.0f} ms each on average and up to {med(G['cs10srv']['max_us'])/1000:.0f} ms. Workstation GC collects {med(G['cs10']['gc_gen0'])/med(G['cs10srv']['gc_gen0']):.0f}× more often in smaller pieces: shorter worst case, but a slow p99.9 and half the throughput. .NET 11 behaves the same as .NET 10 here.</p>
      <p>Go reports only {med(G['go']['gc_pause_ms']):.0f} ms of stop-the-world time over the run, yet the loop still stalled for up to {med(G['go']['max_us'])/1000:.0f} ms: Go makes allocating code help with marking while a collection runs, and that work lands on the request path. Rust has nothing to pause, but freeing and allocating through the Windows heap makes it the slowest at this particular churn.</p>
    </div>
  </section>

  <section class="card pad" aria-labelledby="mh">
    <h2 id="mh">How this was measured</h2>
    <div class="notes" style="margin-top:12px">
      <div><h3>The service</h3><p>ASP.NET Core minimal API with source-generated JSON (so the same code builds for NativeAOT), Go's net/http with encoding/json, Rust's axum with serde. Each awaits an in-memory ledger call that completes immediately, as a cache hit would. All three return byte-identical signatures for the same request.</p></div>
      <div><h3>Isolation</h3><p>Each server starts suspended, is pinned to logical CPUs 0–3 (two physical cores), then resumed, so every runtime sizes its thread pool for two cores. The load generator, a raw-socket Go client, runs on CPUs 4–5; 6–7 stay free for Windows. On 2 CPUs it pushed as many requests as on 4, so it is not the bottleneck.</p></div>
      <div><h3>Rounds</h3><p>Three rounds in a rotating order, 30 s rest between servers, CPU clock logged throughout (it never dropped below {min(s['mhz_min'] for s in D['servers'])/1000:.1f} GHz). Medians across rounds; run-to-run spread on throughput was up to 15%.</p></div>
      <div><h3>Limits</h3><p>One Windows laptop over loopback, so no network latency and no Linux: production containers can rank differently, especially for GC and threading. Start-up time is not reported, because Windows waits about half a second before retrying a refused local connection, which hides the differences.</p></div>
    </div>
  </section>
  <footer>Service, load generator, GC stress and driver: work3/ (cs, go, rust, loadgen, gc, workload3.py). .NET 11 is a release candidate.</footer>
</div>
'''
(HERE.parent / 'page' / 'payments-under-load.html').write_text(html)
print('ok', len(html))
for q, a in board: print('-', q, ':', a)
