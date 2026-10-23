#!/usr/bin/env python3
"""Bake the clean rerun (results/r4_c_round3.json, r4_c_round4.json, r4_c_soak.json, r4_c2_soak.json) into page/payments-in-production.html."""
import json, re
from html import escape as esc
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = HERE / 'results'
r1, r2, soak, soak2 = (json.loads((R / f).read_text()) for f in ('r4_c_round3.json', 'r4_c_round4.json', 'r4_c_soak.json', 'r4_c2_soak.json'))
tpl = (HERE.parent / 'page' / 'template2.html').read_text()
STYLE = re.search(r'<style>.*?</style>', tpl, re.S).group(0)
FONTS = '\n'.join(l for l in tpl.splitlines() if 'fonts.g' in l)

ORDER = ['cs10', 'cs11', 'cs11ra', 'go', 'rust']           # fixed categorical order -> slots 1..5
LAB = {'cs10': ('C# .NET 10', 'ASP.NET Core'), 'cs11': ('C# .NET 11', 'RC2'), 'cs11ra': ('C# .NET 11', 'RC2 + runtime async'),
       'go': ('Go', '1.27 · net/http'), 'rust': ('Rust', '1.99 · axum')}
SLOT = {k: f's{i + 1}' for i, k in enumerate(ORDER)}
IMAGE_MB = {'cs10': 125, 'cs11': 126, 'cs11ra': 126, 'go': 27.8, 'rust': 15.6}   # docker images, from the build
A = {s['id']: s for s in r1['services']}      # first clean round
B = {s['id']: s for s in r2['services']}      # repeat round, services in reverse order
SK = {s['id']: s for s in soak['services']}
SK2 = {s['id']: s for s in soak2['services']}  # second soak, .NET builds only
rate = r1['rate']
CS = ('cs10', 'cs11', 'cs11ra')

def fmt(v, d=None):
    if v is None: return '—'
    if d is not None: return f'{v:,.{d}f}'
    return f'{v:,.0f}' if abs(v) >= 100 else f'{v:.1f}' if abs(v) >= 10 else f'{v:.2f}'

def bars(title, unit, get, lower_better=False, d=0, src=None):
    vals = [(k, get((src or A)[k])) for k in ORDER]
    top = max(v for _, v in vals) * 1.08
    best = (min if lower_better else max)(v for _, v in vals)
    rows = ''.join(
        f'<div class="brow"><div class="blab">{esc(LAB[k][0])}<small>{esc(LAB[k][1])}</small></div>'
        f'<div class="btrack" aria-hidden="true"><div class="bfill" style="width:{v / top * 100:.2f}%;background:var(--{SLOT[k]})"></div></div>'
        f'<div class="bval">{fmt(v, d)}<small>{esc(unit)}{" <b class=best>best</b>" if v == best else ""}</small></div></div>' for k, v in vals)
    label = '; '.join(f'{LAB[k][0]} {LAB[k][1]} {fmt(v, d)} {unit}' for k, v in vals)
    return f'<div class="unitline">{esc(title)}</div><div class="bars" role="img" aria-label="{esc(title)}: {esc(label)}">{rows}</div>'

def spark(k, pts, xmax, ymax, ylab, shade=None, yticks=(), xlabel='s'):
    """one small-multiple panel: a 2px line on a recessive grid, optional shaded window, hover titles per point"""
    W, H, L, Bm, T = 300, 128, 34, 22, 10
    sx = lambda x: L + x / xmax * (W - L - 6)
    sy = lambda y: T + (1 - min(y, ymax) / ymax) * (H - T - Bm)
    g = []
    if shade:
        g.append(f'<rect x="{sx(shade[0]):.1f}" y="{T}" width="{sx(shade[1]) - sx(shade[0]):.1f}" height="{H - T - Bm}" fill="var(--shade)"/>')
    for yt in yticks:
        g.append(f'<line x1="{L}" x2="{W - 6}" y1="{sy(yt):.1f}" y2="{sy(yt):.1f}" stroke="var(--grid2)" stroke-width="1"/>'
                 f'<text x="{L - 4}" y="{sy(yt) + 3.5:.1f}" text-anchor="end" class="tk">{fmt(yt, 0)}</text>')
    for xt in (0, xmax // 2, xmax):
        g.append(f'<text x="{sx(xt):.1f}" y="{H - 6}" text-anchor="middle" class="tk">{xt}{xlabel}</text>')
    path = ' '.join(f'{"M" if i == 0 else "L"}{sx(x):.1f},{sy(y):.1f}' for i, (x, y) in enumerate(pts))
    g.append(f'<path d="{path}" fill="none" stroke="var(--{SLOT[k]})" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
    hits = ''.join(f'<rect x="{sx(x) - 2:.1f}" y="{T}" width="5" height="{H - T - Bm}" fill="transparent"><title>{x}{xlabel}: {fmt(y)} {ylab}</title></rect>'
                   for x, y in pts[::max(1, len(pts) // 90)])
    return (f'<figure class="sm"><figcaption><span class="sw" style="background:var(--{SLOT[k]})"></span>{esc(LAB[k][0])} <small>{esc(LAB[k][1])}</small></figcaption>'
            f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(LAB[k][0] + " " + LAB[k][1])}: {esc(ylab)} over time">{"".join(g)}{hits}</svg></figure>')

# ---------- numbers used in the copy ----------
cpu = lambda k: A[k]['steady_stats']['cpu_median_pct']
p50 = lambda k: A[k]['steady']['ok_p50_ms']
p99 = lambda k: A[k]['steady']['ok_p99_ms']
mx = lambda k: (A[k]['max']['good_rps'] + B[k]['max']['good_rps']) / 2
sk99 = lambda k: SK[k]['soak']['ok_p99_ms']
sk50 = lambda k: SK[k]['soak']['ok_p50_ms']
cs_cpu = sum(cpu(k) for k in ('cs10', 'cs11', 'cs11ra')) / 3
native_cpu = (cpu('go') + cpu('rust')) / 2
scpu = lambda k: sum(x[k]['stats']['cpu_median_pct'] for x in (SK, SK2) if k in x) / sum(1 for x in (SK, SK2) if k in x)   # 8-minute soaks, after a 45 s warm-up
deg = {k: A[k]['degrade'] for k in ORDER}
def window(k, a, b):
    s = [p for p in deg[k]['series'] if a <= p['t'] < b]
    n = sum(p['n'] for p in s); e = sum(p['errors'] for p in s)
    return e / n * 100 if n else 0, max(p['p50_ms'] for p in s)
# integrity is checked after the steady run and again after the degradation run; the second count covers the whole service run
total_payments = sum(A[k]['degrade_integrity']['captured'] + B[k]['degrade_integrity']['captured'] + SK[k]['integrity']['captured'] for k in ORDER) + sum(SK2[k]['integrity']['captured'] for k in SK2)
all_consistent = all(x[k][f]['consistent'] for x in (A, B) for k in ORDER for f in ('steady_integrity', 'degrade_integrity')) and all(x[k]['integrity']['consistent'] for x in (SK, SK2) for k in x)

board = [
 ('CPU for the same traffic', f"Settled, at {rate} payments/s: Rust {scpu('rust'):.0f}%, Go {scpu('go'):.0f}%, C# {min(scpu(k) for k in CS):.0f}–{max(scpu(k) for k in CS):.0f}% of one CPU. "
   f"C# needs about 90 seconds under load to get there: between 45 and 105 seconds after a cold start it still runs at about {cs_cpu:.0f}% while the JIT recompiles the hot code. Go and Rust sit at about {native_cpu:.0f}% from the first second."),
 ('.NET 11 against .NET 10', f"Once warm, .NET 11 RC2 used {scpu('cs11'):.0f}% of a CPU and .NET 10 {scpu('cs10'):.0f}% for the same traffic, and the gap held in both soaks. Runtime async ({scpu('cs11ra'):.0f}%) made no further difference here. Peak throughput is the same within 4%."),
 ('Most payments per second', f"Go reached {mx('go'):,.0f}/s and C# {min(mx(k) for k in CS):,.0f}–{max(mx(k) for k in CS):,.0f}/s, both at their CPU limit (averages of two rounds). "
   f"Rust stopped at {mx('rust'):,.0f}/s with CPU to spare ({A['rust']['max_stats']['cpu_median_pct']:.0f}%), so something outside it, most likely the database, set its ceiling."),
 ('Typical response', f"Once warm, {min(sk50(k) for k in ORDER):.0f}–{max(sk50(k) for k in ORDER):.0f} ms median for all five. The provider call and the database round trips dominate, as they do in production."),
 ('Slow requests', f"p99 over eight minutes: Rust {sk99('rust'):.0f} ms, Go {sk99('go'):.0f} ms, C# {min(sk99(k) for k in CS):.0f}–{max(sk99(k) for k in CS):.0f} ms. In the first two minutes after a cold start the C# tail is longer and noisier (p99 {min(x[k]['steady']['ok_p99_ms'] for x in (A, B) for k in CS):.0f}–{max(x[k]['steady']['ok_p99_ms'] for x in (A, B) for k in CS):.0f} ms across both rounds)."),
 ('Provider outage', "When the provider turned slow and flaky, every service failed fast at its 1-second timeout, kept memory bounded and recovered as soon as the provider did. No queue built up and nothing crashed."),
 ('8 minutes at steady load', "No memory growth and no stalls in any of them, in two soaks of each .NET build and one each of Go and Rust."),
 ('Correctness', f"{total_payments:,} payments captured across all runs. After every run the merchant balances added up to exactly the number of captured payments" + (", with nothing left pending. No lost or double-counted updates in any language." if all_consistent else ", except where marked below.")),
 ('Footprint', f"Idle memory: Rust {A['rust']['idle']['mem_last_mb']:.1f} MB, Go {A['go']['idle']['mem_last_mb']:.0f} MB, C# {A['cs11']['idle']['mem_last_mb']:.0f}–{A['cs10']['idle']['mem_last_mb']:.0f} MB. "
   f"Image: Rust {IMAGE_MB['rust']:.0f} MB, Go {IMAGE_MB['go']:.0f} MB, C# about {IMAGE_MB['cs10']} MB."),
]

deg_panels = ''.join(spark(k, [(p['t'], p['p50_ms']) for p in deg[k]['series']], 90, 450, 'ms median', shade=(30, 60), yticks=(0, 200, 400)) for k in ORDER)
deg_rows = ''.join(
    f"<tr><td><span class='sw' style='background:var(--{SLOT[k]})'></span>{esc(LAB[k][0])} <small>{esc(LAB[k][1])}</small></td>"
    f"<td>{window(k, 0, 30)[0]:.1f}%</td><td>{window(k, 30, 60)[0]:.1f}%</td><td>{window(k, 60, 90)[0]:.1f}%</td>"
    f"<td>{fmt(window(k, 30, 60)[1], 0)} ms</td><td>{fmt(A[k]['degrade_stats']['mem_peak_mb'], 0)} MB</td>"
    f"<td>{'yes' if A[k]['degrade_integrity']['consistent'] else 'NO'}</td></tr>" for k in ORDER)

mem_ymax = 90
soak_panels = ''.join(spark(k, [(round(t), m) for t, m, _ in SK[k]['stats']['series'] if m], 480, mem_ymax, 'MB', yticks=(0, 40, 80)) for k in ORDER)
soak_rows = ''.join(
    f"<tr><td><span class='sw' style='background:var(--{SLOT[k]})'></span>{esc(LAB[k][0])} <small>{esc(LAB[k][1])}</small></td>"
    f"<td>{SK[k]['integrity']['captured']:,}</td><td>{fmt(SK[k]['soak']['ok_p50_ms'], 0)} ms</td><td>{fmt(sk99(k), 0)} ms</td>"
    f"<td>{fmt([m for _, m, _ in SK[k]['stats']['series'] if m][5], 0)} → {fmt(SK[k]['stats']['series'][-1][1], 0)} MB</td><td>{fmt(SK[k]['stats']['cpu_median_pct'], 0)}%</td>"
    + (f"<td class='mute'>{fmt(SK2[k]['soak']['ok_p99_ms'], 0)} ms · {fmt(SK2[k]['stats']['cpu_median_pct'], 0)}%</td>" if k in SK2 else "<td class='mute'>—</td>") + "</tr>" for k in ORDER)

steady_rows = ''.join(
    f"<tr><td><span class='sw' style='background:var(--{SLOT[k]})'></span>{esc(LAB[k][0])} <small>{esc(LAB[k][1])}</small></td>"
    f"<td>{fmt(cpu(k), 0)}%</td><td>{fmt(scpu(k), 0)}%</td><td>{fmt(p50(k), 0)}</td><td>{fmt(p99(k), 0)}</td><td>{fmt(A[k]['steady']['ok_p999_ms'], 0)}</td>"
    f"<td>{fmt(A[k]['steady_stats']['mem_peak_mb'], 0)} MB</td><td>{fmt(A[k]['max']['good_rps'], 0)}/s</td>"
    f"<td class='mute'>{fmt(B[k]['steady']['ok_p99_ms'], 0)} ms · {fmt(B[k]['max']['good_rps'], 0)}/s</td></tr>" for k in ORDER)


# ---------- NativeAOT: five rounds (5-9) and one soak, same harness ----------
AR = [{x['id']: x for x in json.loads((R / f).read_text())['services']} for f in
      ('r4_aot_round5.json', 'r4_aot_round6.json', 'r4_aotx_round7.json', 'r4_aotx_round8.json', 'r4_aotx_round9.json')]
ASK = {x['id']: x for x in json.loads((R / 'r4_aot_soak.json').read_text())['services']}
def med(xs):
    xs = sorted(xs); n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
def rounds_of(k):   # every clean round that ran this build
    return [x[k] for x in (A, B, *AR) if k in x]
def rmed(k, f): return med([f(x) for x in rounds_of(k)])
def soak_cpu(k): return med([x[k]['stats']['cpu_median_pct'] for x in (SK, SK2, ASK) if k in x])
def soak_p99(k): return med([x[k]['soak']['ok_p99_ms'] for x in (SK, SK2, ASK) if k in x])
IMAGE_MB.update({'cs10aot': 36.0, 'cs11aot': 36.2})
AOT_ROWS = [('cs10', 'cs10', 'C# .NET 10', 'JIT'), ('cs10aot', 'cs10', 'C# .NET 10', 'NativeAOT'),
            ('cs11', 'cs11', 'C# .NET 11', 'JIT'), ('cs11aot', 'cs11', 'C# .NET 11', 'NativeAOT'),
            ('go', 'go', 'Go', 'reference'), ('rust', 'rust', 'Rust', 'reference')]
aot_rows = ''.join(
    f"<tr{' class=aot' if 'aot' in k else ''}><td><span class='sw' style='background:var(--{SLOT[c]})'></span>{esc(n)} <small>{esc(m)}</small></td>"
    f"<td>{rmed(k, lambda x: x['startup']['ready_ms']) / 1000:.2f} s</td>"
    f"<td>{rmed(k, lambda x: x['idle']['mem_last_mb']):.1f} MB</td>"
    f"<td>{rmed(k, lambda x: x['steady_stats']['cpu_median_pct']):.0f}%</td>"
    + (lambda v: f"<td>{min(v):.0f}–{max(v):.0f} ms</td>" if len(v) == 2 else f"<td>{med(v):.0f} ms</td>")([x['steady']['ok_p99_ms'] for x in rounds_of(k)]) +
    f"<td>{soak_cpu(k):.0f}%</td><td>{soak_p99(k):.0f} ms</td>"
    f"<td>{rmed(k, lambda x: x['max']['good_rps']):,.0f}/s</td><td>{IMAGE_MB[k]:.0f} MB</td>"
    f"<td class='mute'>{len(rounds_of(k))}</td></tr>" for k, c, n, m in AOT_ROWS)
aot_n = sum(1 for x in AR if 'cs10aot' in x)
hang = AR[1]['cs10aot']['degrade']
hang_timeouts = hang['codes'].get('0', 0)
aot_gain_ready = rmed('cs11', lambda x: x['startup']['ready_ms']) / rmed('cs11aot', lambda x: x['startup']['ready_ms'])
aot_tp = rmed('cs11aot', lambda x: x['max']['good_rps']) / rmed('cs11', lambda x: x['max']['good_rps']) - 1
board.insert(2, ('NativeAOT', f"Removes the warm-up: ready in {rmed('cs11aot', lambda x: x['startup']['ready_ms']) / 1000:.1f} s like Go and Rust, CPU near its settled level from the start, a {rmed('cs11aot', lambda x: x['steady']['ok_p99_ms']):.0f} ms cold-start p99 and a 36 MB image. "
                     f"Settled CPU is unchanged, and .NET 11's peak throughput is {abs(aot_tp) * 100:.0f}% lower than with the JIT."))

foot_rows = ''.join(
    f"<tr><td><span class='sw' style='background:var(--{SLOT[k]})'></span>{esc(LAB[k][0])} <small>{esc(LAB[k][1])}</small></td>"
    f"<td>{fmt(A[k]['startup']['ready_ms'] / 1000, 2)} s</td><td>{fmt(A[k]['startup']['first_pay_ms'] / 1000, 2)} s</td>"
    f"<td class='mute'>{fmt(B[k]['startup']['first_pay_ms'] / 1000, 2)} s</td>"
    f"<td>{fmt(A[k]['idle']['mem_last_mb'], 1)} MB</td><td>{fmt(IMAGE_MB[k], 0)} MB</td></tr>" for k in ORDER)

html = f'''<title>Payments in Production</title>
<meta name="claude:viewport-fit-sides" content="cover">
{FONTS}
{STYLE}
<style>
:root{{--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--shade:#eb683414;--grid2:#e1e4de}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--shade:#d9592622;--grid2:#262b36}}}}
:root[data-theme="dark"]{{--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--shade:#d9592622;--grid2:#262b36}}
.best{{font:700 9.5px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--good)}}
.two2{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:0}}
.two2>div{{padding:20px;min-width:0}}
.two2>div+div{{border-left:1.5px solid var(--hair)}}
@media (max-width:860px){{.two2{{grid-template-columns:minmax(0,1fr)}}.two2>div+div{{border-left:0;border-top:1.5px solid var(--hair)}}}}
.st td small,.sm small{{font:500 11px var(--mono);color:var(--mute);margin-left:4px}}
.st td.mute{{color:var(--mute);font-size:12px}}
.st tr.aot td{{background:color-mix(in srgb,var(--blue) 6%,transparent)}}
.qa td:first-child{{width:22%}}
.prose p{{margin:10px 0 0;max-width:68ch}}
.smgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px;padding:0 20px 16px}}
.sm{{margin:0;min-width:0}}
.sm figcaption{{font:700 13px var(--disp);margin-bottom:2px}}
.sm svg{{width:100%;height:auto;display:block}}
.tk{{font:500 9.5px var(--mono);fill:var(--mute)}}
.flow{{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:12px}}
.flow span{{font:700 11px var(--mono);letter-spacing:.03em;border:1.5px solid var(--hair);background:var(--code);border-radius:6px;padding:5px 8px}}
.flow i{{font-style:normal;color:var(--mute)}}
.legend2{{font:500 12px var(--mono);color:var(--mute);padding:0 20px 8px}}
.legend2 b{{display:inline-block;width:14px;height:10px;background:var(--shade);border:1px solid var(--s2);vertical-align:-1px;margin-right:6px}}
</style>
<div class="wrap">
  <header>
    <div class="eyebrow">Compiler probes · set 4 · production-shaped</div>
    <h1>The same payment service, <em>in containers</em>, with real moving parts</h1>
    <p class="lede">Each service checks a JWT, rate-limits in Redis, validates the payment, records it in Postgres, charges a mock provider that is slow 1% of the time, captures it in a transaction with the merchant balance, logs a JSON line and replies. Each runs alone in a Linux container capped at 1 CPU and 512 MB.</p>
    <div class="flow" aria-label="request path"><span>JWT</span><i>→</i><span>Redis rate limit</span><i>→</i><span>validate</span><i>→</i><span>INSERT pending</span><i>→</i><span>provider call · 1 s timeout</span><i>→</i><span>tx: capture + balance</span><i>→</i><span>JSON log + reply</span></div>
    <div class="meta"><span class="chip">Docker Desktop · Linux VM, 4 CPUs</span><span class="chip">service: 1 CPU, 512 MB</span><span class="chip">Postgres 17 · Redis 7</span><span class="chip">{rate} payments/s steady</span><span class="chip">.NET 10.0.12 · .NET 11 RC2 · Go 1.27.2 · Rust 1.99</span></div>
  </header>

  <section class="card board" aria-labelledby="qh">
    <div class="pad" style="padding-bottom:6px"><h2 id="qh">The short version</h2></div>
    <table class="qa">{''.join(f'<tr><td><b>{esc(q)}</b></td><td>{esc(a)}</td></tr>' for q, a in board)}</table>
  </section>

  <section class="card" aria-labelledby="sh">
    <div class="pad" style="padding-bottom:0"><h2 id="sh">Steady load: {rate} payments a second</h2>
      <p class="sub">Started right after the cold start: 45 seconds of warm-up, then 60 measured seconds on a fixed schedule. Latency is for answered payments; the 1% the provider drops all take exactly the 1-second timeout and are counted separately. "CPU settled" comes from the eight-minute soaks below.</p></div>
    <div class="two2">
      <div>{bars(f'CPU used at {rate} payments/s once warm (8-minute soaks, mean of runs, of 1 CPU)', '%', lambda s: scpu(s['id']), lower_better=True, src=SK)}</div>
      <div>{bars('Most payments per second, as fast as it can', '/s', lambda s: s['max']['good_rps'])}</div>
    </div>
    <div class="st"><table><tr><th>Service</th><th>CPU 45–105 s</th><th>CPU settled</th><th>p50 ms</th><th>p99 ms</th><th>p99.9 ms</th><th>Peak memory</th><th>Max</th><th>Repeat round <small>p99 · max</small></th></tr>{steady_rows}</table></div>
    <div class="pad prose"><p>Numbers are from the first of two clean rounds; the last column is the repeat, run with the services in reverse order. In this window the C# builds are still warming up, which is why their CPU is far above the settled figure.</p></div>
  </section>

  <section class="card" aria-labelledby="dh">
    <div class="pad" style="padding-bottom:6px"><h2 id="dh">The provider has a bad half-minute</h2>
      <p class="sub">{rate} payments a second for 90 seconds. From 30 s to 60 s the provider's median goes from 30 ms to 300 ms and 10% of calls hang. The services have a 1-second timeout on that call.</p></div>
    <div class="legend2"><b></b>provider degraded · line: median response time, ms (shared scale)</div>
    <div class="smgrid">{deg_panels}</div>
    <div class="st"><table><tr><th>Service</th><th>Failed before</th><th>Failed during</th><th>Failed after</th><th>Worst median</th><th>Peak memory</th><th>Ledger consistent</th></tr>{deg_rows}</table></div>
    <div class="pad prose"><p>All five behave the same way, which is the result you want from a payment service: during the outage about {sum(window(k, 30, 60)[0] for k in ORDER) / 5:.0f}% of payments fail fast with a 502 (the 10% that hang, plus slow calls that cross the timeout), latency rises to the provider's new median, memory grows a little and comes back, and everything returns to normal the second the provider does. No retry storms, no queue that outlives the outage, no crash. Failed payments are marked failed in the database, never left pending.</p></div>
  </section>

  <section class="card" aria-labelledby="kh">
    <div class="pad" style="padding-bottom:6px"><h2 id="kh">Eight minutes at steady load</h2>
      <p class="sub">About 240,000 payments per service, looking for memory growth and latency drift. The .NET builds ran twice; the last column is the repeat.</p></div>
    <div class="legend2">line: container memory, MB (shared scale, 0–{mem_ymax})</div>
    <div class="smgrid">{soak_panels}</div>
    <div class="st"><table><tr><th>Service</th><th>Captured</th><th>p50</th><th>p99</th><th>Memory</th><th>CPU</th><th>Repeat soak <small>p99 · CPU</small></th></tr>{soak_rows}</table></div>
    <div class="pad prose"><p>Memory settles within the first minute in every runtime and stays flat, so none of them leaks under this workload. Latency stays flat too: no service fell behind at any point. An earlier, noisier run had the plain .NET 11 build fall behind for about a minute; it did not happen in either repeat, so it is not counted as a finding.</p></div>
  </section>

  <section class="card" aria-labelledby="fh">
    <div class="pad"><h2 id="fh">Start-up and footprint</h2>
      <p class="sub">Cold start is measured inside Linux, from the container's start to the first answered health check and to the first captured payment (JWT, Redis, Postgres and provider all warm).</p></div>
    <div class="st"><table><tr><th>Service</th><th>Ready</th><th>First payment</th><th>Repeat round</th><th>Idle memory</th><th>Image</th></tr>{foot_rows}</table></div>
  </section>


  <section class="card" aria-labelledby="ah">
    <div class="pad" style="padding-bottom:6px"><h2 id="ah">NativeAOT: the same code, compiled ahead of time</h2>
      <p class="sub">The C# service unchanged, published with <span class="code-in">PublishAot=true</span> inside a Linux SDK container and shipped on the same Alpine base. It already used the slim builder and source-generated JSON; Npgsql, StackExchange.Redis and JwtBearer built with no trim or AOT warnings. Medians over every clean round that ran each build (last column).</p></div>
    <div class="st"><table><tr><th>Build</th><th>Ready</th><th>Idle memory</th><th>CPU 45–105 s</th><th>p99 45–105 s</th><th>CPU settled</th><th>p99 settled</th><th>Max</th><th>Image</th><th>Rounds</th></tr>{aot_rows}</table></div>
    <div class="pad prose"><p>AOT takes away everything that comes from compiling at run time: start-up is {aot_gain_ready:.1f}× faster and level with Go and Rust, there is no 90-second warm-up, and the cold-start tail is as short as theirs. It does not make the steady-state work cheaper. Settled CPU is the same as the JIT build, and .NET 11's peak throughput is {abs(aot_tp) * 100:.0f}% lower, because the JIT's profile-guided recompilation does a little better than ahead-of-time code once it has warmed up. That gap is small, but it is not noise: across five rounds the AOT build's peak varied by about 3%, the JIT build's by under 1%. .NET 11 stays cheaper than .NET 10 under AOT too.</p>
    <p>One run went wrong. In the second of {aot_n} rounds, .NET 10 AOT stopped answering during the provider-outage test. It had already slowed to a 1.5–2 s median for ten seconds before the outage began; then, about 30 seconds after the outage began, nearly every request waited out the 10-second client timeout ({hang_timeouts:,} in all), while its CPU fell to about 30% and memory rose to 204 MB. It stayed up, the ledger stayed consistent, and the next three rounds were clean, with database connection states and service logs recorded and nothing unusual in either. Low CPU while unresponsive suggests something blocked rather than overloaded, but one episode in {aot_n} runs is not enough to pin it on NativeAOT.</p></div>
  </section>

  <section class="card pad" aria-labelledby="mh">
    <h2 id="mh">How this was measured, and what it still leaves out</h2>
    <div class="notes" style="margin-top:12px">
      <div><h3>Same work everywhere</h3><p>ASP.NET Core minimal API with JwtBearer, Npgsql, StackExchange.Redis and HttpClient; Go's net/http with pgx, go-redis and golang-jwt; Rust's axum with tokio-postgres, redis, reqwest and jsonwebtoken. Each uses a 32-connection database pool, releases it during the provider call, and returns byte-identical signatures for the same payment.</p></div>
      <div><h3>The load</h3><p>A Go load generator inside the Docker network, with a fresh payment id per request, a JWT per merchant, 2% invalid payments (422) and 1% repeated ids to exercise idempotency. Requests go out on a fixed schedule and are timed from when they were due, so queueing inside a service is counted.</p></div>
      <div><h3>Isolation</h3><p>Docker Desktop's VM has 4 CPUs: the service gets 1, Postgres 1.5, the load generator 1, the provider 0.5 and Redis 0.25. Only one payment service runs at a time, against an emptied database. The C# builds publish self-contained for Alpine with default settings (server GC, tiered PGO).</p></div>
      <div><h3>Still missing</h3><p>One machine and one laptop CPU underneath Docker, so container CPU is shared with Windows; no real network between services; one replica, no load balancer;, and a deliberately small schema. The next step that would matter is running this harness against a real service's hot endpoint.</p></div>
    </div>
  </section>
  <footer>Source and raw results: work4/ (cs, go, rust, mockpay, loadgen, compose.yml, run4.py, results/). .NET 11 is a release candidate.</footer>
</div>
'''
(HERE.parent / 'page' / 'payments-in-production.html').write_text(html)
print('ok', len(html))
for q, a in board: print('-', q, ':', a)
print('degraded failure %', {k: round(window(k, 30, 60)[0], 1) for k in ORDER})
