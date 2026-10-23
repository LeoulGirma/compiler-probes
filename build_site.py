#!/usr/bin/env python3
"""Assemble the shareable site: an overview page plus the four result pages, each with the same navigation bar.
   python build_site.py  ->  site/index.html (overview fragment, wrapped at publish) and site/*.html (full documents)."""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE, SITE = HERE / 'page', HERE / 'site'
SITE.mkdir(exist_ok=True)

# (file in site/, source page, nav label, short label for phones)
PAGES = [('start.html', None, 'Start here', 'Start'),
         ('watch.html', None, 'Watch', 'Watch'),
         ('concepts.html', None, 'Concepts', 'Concepts'),
         ('probes.html', 'compiler-probes.html', '1 · Machine code', '1 Machine code'),
         ('net11.html', 'compiler-probes-net11.html', '2 · .NET 11 claims', '2 .NET 11'),
         ('load.html', 'payments-under-load.html', '3 · Under load', '3 Load'),
         ('containers.html', 'payments-in-production.html', '4 · In containers', '4 Containers'),
         ('takeaways.html', None, 'Takeaways', 'Takeaways')]

# shown at the top of each result page: the question, what to look at first, and the concepts it leans on
ANSWER = {
 'probes.html': 'Each compiler wins somewhere. LLVM vectorises loops (Rust sums an array about 7× faster), RyuJIT\'s profile-guided JIT makes interface calls cheapest, and Go keeps builds fast and predictable. The machine code under every number explains why.',
 'net11.html': 'Of six .NET 11 claims, two delivered large wins (devirtualisation, 6.5× and 6.3× in our probes), runtime async is real but opt-in (awaits about 4× cheaper), Math.BigMul emits fewer instructions yet runs 31% slower, and two showed no change.',
 'load.html': 'Throughput is close: the slowest build reaches 79% of the fastest. The real differences are CPU per request, memory and tail latency. Here .NET 11 RC2 used about 11% more CPU per request than .NET 10, the opposite of what set 4 found.',
 'containers.html': 'With a database and a provider in the path, medians converge at 28–30 ms. C# needs about 90 s under load to warm up and more CPU per payment; Native AOT removes the warm-up but not the CPU cost. Every build survived a simulated provider outage with its ledger intact.',
}
PRIMER = {
 'probes.html': ('What does each compiler do with the same five small functions?',
   'Open the matrix first: each cell is time per call, and clicking it shows the machine code that produced it. Then the warm-up curve shows the JIT tiers at work.',
   ['aot-vs-jit', 'tiering', 'pgo', 'simd', 'bounds', 'devirt']),
 'net11.html': ('Do the runtime changes listed for .NET 11 show up when measured?',
   'The verdict board gives one line per claim. Each card below it has the timing, the machine code before and after, and what Rust and Go do with the same code.',
   ['devirt', 'async', 'regalloc', 'bounds', 'r2r']),
 'load.html': ('How close are the languages when they serve a real API, with no database in the way?',
   'Start with the short version. Throughput is close; the interesting rows are CPU per request, memory and the heap-pressure test.',
   ['tail', 'openloop', 'gc', 'nativeaot', 'footprint']),
 'containers.html': ('What changes with Postgres, Redis, a flaky provider and a one-CPU container?',
   'Read the short version, then compare "CPU 45–105 s" with "CPU settled": that gap is the JIT warming up. The NativeAOT section shows what happens when there is no JIT.',
   ['cpulimit', 'coldstart', 'tiering', 'nativeaot', 'footprint', 'tail', 'openloop']),
}
SHORT = {'aot-vs-jit': 'AOT vs JIT', 'tiering': 'Tiered JIT', 'pgo': 'Dynamic PGO', 'r2r': 'ReadyToRun', 'nativeaot': 'NativeAOT',
         'simd': 'SIMD', 'bounds': 'Bounds checks', 'devirt': 'Devirtualisation', 'async': 'Runtime async', 'regalloc': 'Register spills',
         'gc': 'Garbage collection', 'footprint': 'Footprint', 'tail': 'Tail latency', 'openloop': 'Open-loop load', 'coldstart': 'Cold start', 'cpulimit': 'CPU limits'}

def primer(f):
    q, look, ids = PRIMER[f]
    chips = ''.join(f'<a href="concepts.html#{i}">{SHORT[i]}</a>' for i in ids)
    return (f'<aside class="card primer" aria-label="The answer"><div class="ans"><div class="ph">The answer</div><p>{ANSWER[f]}</p></div><div><div class="ph">The question</div><p>{q}</p></div>'
            f'<div><div class="ph">Concepts used</div><div class="pchips">{chips}</div></div></aside>')

NAV_CSS = '''<style>
/* site navigation: one sticky bar shared by every page; colours come from each page's own tokens */
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:30;background:var(--surface)}
.sitenav{position:sticky;top:env(safe-area-inset-top,0px);z-index:20;margin:-28px -16px 26px;background:color-mix(in srgb,var(--surface) 96%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--hair)}
.sitenav .in{max-width:1164px;margin:0 auto;display:flex;align-items:center;gap:28px;padding:0 22px;min-height:62px}
.sitenav .brand{font:800 17px var(--disp);letter-spacing:-.03em;color:var(--ink);text-decoration:none;white-space:nowrap}
.sitenav .brand b{color:var(--blue)}
.sitenav ul{list-style:none;margin:0 0 0 auto;padding:0;display:flex;align-items:center;gap:4px;min-width:0}
.sitenav a.l{display:block;font:700 10.5px var(--mono);letter-spacing:.03em;text-transform:uppercase;color:var(--mute);text-decoration:none;padding:10px 9px;border-radius:6px;white-space:nowrap}
.sitenav a.l:hover{color:var(--blue);background:color-mix(in srgb,var(--blue) 9%,transparent)}
.sitenav a.l:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.sitenav a.l[aria-current=page]{color:var(--blue);background:color-mix(in srgb,var(--blue) 11%,transparent)}
.sitenav .mnav{display:none;margin-left:auto;position:relative}
.sitenav .mnav summary{list-style:none;cursor:pointer;white-space:nowrap;display:flex;gap:10px;align-items:center;font:700 12px var(--mono);letter-spacing:.04em;text-transform:uppercase;color:var(--ink);border:1.5px solid var(--hair);border-radius:8px;padding:8px 12px;background:var(--surface)}
.sitenav .mnav summary::-webkit-details-marker{display:none}
.sitenav .mnav summary i{font-style:normal;color:var(--blue)}
.sitenav .mnav summary:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.sitenav .mlist{position:absolute;right:0;top:calc(100% + 8px);min-width:240px;background:var(--surface);border:1.5px solid var(--ink);border-radius:12px;padding:6px;display:flex;flex-direction:column;box-shadow:6px 6px 0 color-mix(in srgb,var(--ink) 15%,transparent)}
.sitenav .mlist a{font:700 13px var(--mono);color:var(--ink);text-decoration:none;padding:11px 12px;border-radius:8px}
.sitenav .mlist a:hover,.sitenav .mlist a[aria-current]{background:color-mix(in srgb,var(--blue) 12%,transparent);color:var(--blue)}
@media (max-width:1040px){.sitenav ul{display:none}.sitenav .mnav{display:block}.sitenav .in{justify-content:space-between}}
.pager{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font:700 12px var(--mono)}
.pager a{color:var(--ink);text-decoration:none;border:1.5px solid var(--hair);background:var(--surface);border-radius:8px;padding:10px 14px}
.pager a:hover{border-color:var(--blue)}
.primer{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);row-gap:14px;gap:18px;padding:16px 20px;border-color:var(--hair);background:var(--surface)}
@media (max-width:860px){.primer{grid-template-columns:minmax(0,1fr)}}
.primer>div{min-width:0}
.primer .ans{grid-column:1/-1;border-bottom:1px solid var(--hair);padding-bottom:14px}
.primer .ans p{font-size:19px;line-height:1.45;max-width:78ch;font-weight:600}
/* quieter background, larger small labels, and a visible hint on tables that scroll sideways */
html body{background-image:linear-gradient(color-mix(in srgb,var(--grid) 50%,transparent) 1px,transparent 1px),linear-gradient(90deg,color-mix(in srgb,var(--grid) 50%,transparent) 1px,transparent 1px)}
html body .blab{font-size:12px} html body .tk{font-size:11px} html body .chip{font-size:11.5px} html body .bval small{font-size:11.5px}
html body .st th,html body .mc th{font-size:11.5px}
.scrolls{position:relative;background:linear-gradient(to left,color-mix(in srgb,var(--ink) 10%,transparent),transparent 28px) right/28px 100% no-repeat}
.scrollhint{display:none;font:700 11px var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--blue);padding:6px 20px 0}
.scrolls + .scrollhint,.scrollhint.on{display:block}
details.more{border-top:1px solid var(--hair)}
details.more>summary{cursor:pointer;list-style:none;font:700 12px var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--blue);padding:12px 20px}
details.more>summary::-webkit-details-marker{display:none}
details.more>summary::before{content:'+ '}
details.more[open]>summary::before{content:'− '}
details.more>summary:focus-visible{outline:2px solid var(--blue);outline-offset:-2px}
.primer .ph{font:700 10.5px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--mute);margin-bottom:4px}
.primer p{margin:0;font-size:15px}
.pchips{display:flex;flex-wrap:wrap;gap:6px}
.pchips a{font:700 11.5px var(--mono);letter-spacing:.04em;color:var(--ink);text-decoration:none;border:1.5px solid var(--hair);border-radius:999px;padding:3px 9px;background:var(--bg)}
.pchips a:hover{border-color:var(--blue);color:var(--blue)}
.pager small{display:block;font:500 10px var(--mono);color:var(--mute);letter-spacing:.06em;text-transform:uppercase;margin-bottom:2px}
</style>'''

def nav(cur):
    items = ''.join(f'<li><a class="l" href="{f}"{" aria-current=\"page\"" if f == cur else ""}>{short}</a></li>' for f, _, full, short in PAGES)
    menu = ''.join(f'<a href="{f}"{" aria-current=\"page\"" if f == cur else ""}>{full}</a>' for f, _, full, short in PAGES)
    here = next(short for f, _, full, short in PAGES if f == cur)
    return (f'<nav class="sitenav" aria-label="Sections"><div class="in"><a class="brand" href="start.html">Compiler <b>probes</b></a><ul>{items}</ul>'
            f'<details class="mnav"><summary><span>{here}</span><i aria-hidden="true">Menu</i></summary><div class="mlist">{menu}</div></details></div></nav>')

def pager(cur):
    i = [p[0] for p in PAGES].index(cur)
    prev = f'<a href="{PAGES[i-1][0]}"><small>Previous</small>← {PAGES[i-1][2]}</a>' if i > 0 else '<span></span>'
    nxt = f'<a href="{PAGES[i+1][0]}"><small>Next</small>{PAGES[i+1][2]} →</a>' if i + 1 < len(PAGES) else '<span></span>'
    return f'<div class="pager">{prev}{nxt}</div>'

SCROLL_JS = '''<script>
(() => { const mark = () => document.querySelectorAll('.st,.board,.mcw,.tw,.decw,.scroll').forEach(el => {
  const wide = el.scrollWidth > el.clientWidth + 4; el.classList.toggle('scrolls', wide);
  let h = el.nextElementSibling; if (wide && !(h && h.classList.contains('scrollhint'))) { h = document.createElement('div'); h.className = 'scrollhint'; h.textContent = 'Scroll sideways for more →'; el.after(h); }
  if (h && h.classList.contains('scrollhint')) h.classList.toggle('on', wide); });
  addEventListener('load', mark); addEventListener('resize', mark); setTimeout(mark, 300); })();
</script>'''

def fold_tables(s):
    """detail tables start folded: the chart and the prose carry the finding, the full numbers are one click away"""
    return re.sub(r'<div class="st">(<table>.*?</table>)</div>', r'<details class="more"><summary>Full table</summary><div class="st">\1</div></details>', s, flags=re.S)

def place(frag, cur):
    """put the nav bar right before the page's main wrapper and the pager at the end of it"""
    i = frag.index('<div class="wrap">')
    frag = frag[:i] + NAV_CSS + nav(cur) + frag[i:]
    j = frag.rindex('</div>', 0, frag.index('<script', i) if '<script' in frag[i:] else len(frag))
    # the wrapper's closing tag is the last </div> before the first trailing script (or end of file)
    return frag[:j] + pager(cur) + frag[j:] + SCROLL_JS

DOC = '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}[hidden]{display:none!important}img{max-width:100%}</style>\n'

def full_doc(frag):
    head_end = frag.index('<div class="wrap">') if '<nav class="sitenav"' not in frag else frag.index('<style>\n/* site navigation')
    return DOC + frag[:head_end] + '\n</head>\n<body>\n' + frag[head_end:] + '\n</body>\n</html>\n'

def light_default(h):
    """remove every @media (prefers-color-scheme: dark){...} block, so the site opens light even on a dark OS"""
    out, i, key = [], 0, '@media (prefers-color-scheme: dark)'
    while True:
        k = h.find(key, i)
        if k < 0: out.append(h[i:]); return ''.join(out)
        out.append(h[i:k]); d, j = 0, h.index('{', k)
        while True:
            if h[j] == '{': d += 1
            elif h[j] == '}':
                d -= 1
                if d == 0: break
            j += 1
        i = j + 1

def strip_personal(name, s):
    s = re.sub(r'<footer>Source and raw results: work4/[^<]*</footer>', '<footer>.NET 11 is a release candidate (RC2); numbers can change by GA.</footer>', s)
    s = re.sub(r'<div class="pad prose"><p>Headline numbers are from the second round.*?</p></div>', '', s, flags=re.S)
    s = s.replace('Each runs alone in a Linux container capped at 1 CPU and 512 MB.</p>', 'Each runs alone in a Linux container capped at 1 CPU and 512 MB. The provider is a mock with injected delays and failures: a realistic simulation, not a deployed system.</p>')
    return s

if __name__ == '__main__':
    for f, src, *_ in PAGES:
        if src is None:
            frag = place((HERE / f).read_text(), f)
            if f == 'start.html':
                (SITE / 'index.html').write_text(light_default(frag))      # the published page (fragment; the host adds the skeleton)
            (SITE / f).write_text(light_default(full_doc(frag)))
        else:
            s = strip_personal(src, (PAGE / src).read_text())
            if f in ('containers.html', 'load.html'): s = fold_tables(s)
            h = s.index('</header>') + len('</header>')
            s = s[:h] + '\n  ' + primer(f) + s[h:]
            (SITE / f).write_text(light_default(full_doc(place(s, f))))
    for p in sorted(SITE.iterdir()): print(p.name, p.stat().st_size)
