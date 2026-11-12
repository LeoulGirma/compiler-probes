#!/usr/bin/env python3
"""Set 1 consistency rounds for C#: probe.py for .NET 10 and .NET 11 (JIT, ReadyToRun, NativeAOT),
alternating which version goes first, N rounds. Before every run it waits for the machine to go idle,
and it records how busy the machine was (and, on Linux, CPU steal) while the run was measuring.

  python set1_rounds.py --rounds 3 --tag laptop
  python set1_rounds.py --summary --tag laptop      # print the table again from the saved files

Writes set1_<tag>_r<N>.json (one probe.py results file per round) and set1_<tag>_meta.json.
The summary gives, per probe and build, the median over rounds with the min-max range, and marks a
difference as consistent only when every round points the same way and the ranges do not overlap.
"""
import argparse, json, os, re, statistics, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBES = ['vec_sum', 'bounds_one', 'bounds_two', 'dyn', 'alloc']

def cpu_times():
    """(busy, total, steal) seconds summed over all CPUs"""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes, byref
        i, k, u = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        ctypes.windll.kernel32.GetSystemTimes(byref(i), byref(k), byref(u))
        f = lambda ft: (ft.dwHighDateTime << 32 | ft.dwLowDateTime) / 1e7
        return f(k) + f(u) - f(i), f(k) + f(u), 0.0
    v = [float(x) for x in Path('/proc/stat').read_text().split('\n')[0].split()[1:]]
    hz = os.sysconf('SC_CLK_TCK'); idle = v[3] + v[4]; total = sum(v[:8])
    return (total - idle) / hz, total / hz, v[7] / hz

def wait_idle(limit=0.18, hold=20, cap=3600):
    t0 = time.time(); calm = 0; b0, t_0, _ = cpu_times()
    while calm < hold and time.time() - t0 < cap:
        time.sleep(2); b1, t_1, _ = cpu_times()
        frac = (b1 - b0) / max(1e-9, t_1 - t_0); b0, t_0 = b1, t_1
        calm = calm + 2 if frac < limit else 0
    return round(time.time() - t0)

def label(run):
    m = re.match(r'\.NET (\d+)\.(\S+?)(?: \(SDK [^)]*\))?(?: · (.*))?$', run['version'])
    return f".NET {m.group(1)} {m.group(3) or 'JIT'}" if m else run['version']

def summary(tag):
    files = sorted(HERE.glob(f'set1_{tag}_r*.json'), key=lambda p: int(re.search(r'_r(\d+)\.json$', p.name).group(1)))
    meta = json.loads((HERE / f'set1_{tag}_meta.json').read_text()) if (HERE / f'set1_{tag}_meta.json').exists() else []
    vals, versions = {}, {}
    for f in files:
        for r in json.loads(f.read_text())['runs']:
            versions.setdefault(label(r), set()).add(r['version'].split(' (')[0].split(' · ')[0])
            for p in PROBES:
                vals.setdefault((label(r), p), []).append(r['bench'][p])
    print(f'{len(files)} rounds; runtime versions: ' + '; '.join(f'{k}: {", ".join(sorted(v))}' for k, v in sorted(versions.items())))
    for m in meta:
        print(f"   round {m['round']} .NET {m['dotnet']}: waited {m['waited_s']} s for idle, machine busy {m['busy_pct']}% while measuring" + (f", steal {m['steal_pct']}%" if m.get('steal_pct') else ''))
    out = {}
    for build in ('JIT', 'ReadyToRun', 'NativeAOT'):
        a, b = f'.NET 10 {build}', f'.NET 11 {build}'
        print(f'\n{build}: ns per call, median [min-max] over rounds')
        for p in PROBES:
            x, y = vals.get((a, p)), vals.get((b, p))
            if not x or not y: continue
            mx, my = statistics.median(x), statistics.median(y)
            pairs = list(zip(x, y))
            same_way = all(v < u for u, v in pairs) or all(v > u for u, v in pairs)
            apart = max(y) < min(x) or min(y) > max(x)
            verdict = 'consistent' if same_way and apart else 'inconclusive'
            ch = (my / mx - 1) * 100
            out[f'{build}/{p}'] = {'net10': x, 'net11': y, 'change_pct': round(ch, 1), 'verdict': verdict}
            print(f'   {p:11s} {mx:8.0f} [{min(x):.0f}-{max(x):.0f}]  ->  {my:8.0f} [{min(y):.0f}-{max(y):.0f}]  {ch:+6.1f}%  {verdict}')
    (HERE / f'set1_{tag}_summary.json').write_text(json.dumps(out, indent=1))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rounds', type=int, default=3); ap.add_argument('--tag', default='host')
    ap.add_argument('--summary', action='store_true'); ap.add_argument('--no-idle', action='store_true')
    a = ap.parse_args()
    if a.summary: return summary(a.tag)
    if os.name == 'nt':   # keep the machine from going to sleep while this process runs (ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        import ctypes; ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    meta_f = HERE / f'set1_{a.tag}_meta.json'; meta = []
    for n in range(1, a.rounds + 1):
        for major in (['10', '11'] if n % 2 else ['11', '10']):
            waited = 0 if a.no_idle else wait_idle()
            b0, t0, s0 = cpu_times()
            print(f'== round {n} .NET {major} (waited {waited} s for idle)', flush=True)
            p = subprocess.run([sys.executable, '-u', str(HERE / 'probe.py'), '--only', 'cs', '--dotnet', major, '--aot',
                                '--out', str(HERE / f'set1_{a.tag}_r{n}.json')])
            b1, t1, s1 = cpu_times()
            meta.append({'round': n, 'dotnet': major, 'waited_s': waited, 'rc': p.returncode,
                         'busy_pct': round(100 * (b1 - b0) / max(1e-9, t1 - t0), 1), 'steal_pct': round(100 * (s1 - s0) / max(1e-9, t1 - t0), 2)})
            meta_f.write_text(json.dumps(meta, indent=1))
    summary(a.tag)

if __name__ == '__main__':
    main()
