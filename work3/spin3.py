#!/usr/bin/env python3
"""Thread-pool spin experiment on the set 3 harness (Windows).

.NET 11 raised the default of DOTNET_ThreadPool_UnfairSemaphoreSpinLimit from 70 to 1024: idle workers spin longer
before sleeping. This runs the set 3 payment service for .NET 10 and .NET 11 with the default and with the other
version's default swapped in (plus 0 as a check that the setting takes effect), in rotating order, and records
CPU per request both at saturation (closed loop) and at a fixed 8,000 req/s (open loop, where idle time exists).

  python spin3.py build
  python spin3.py run --rounds 4      -> spin3.json (the published runs are spin3_run1.json and spin3_run2.json)
"""
import argparse, json, shutil, sys, time
from pathlib import Path
import workload3 as w

CONFIGS = [  # id, build, label, extra env (0x prefix: unambiguous whatever base the runtime parses)
    ('cs10',      'cs10', '.NET 10, default (70)', {}),
    ('cs10_1024', 'cs10', '.NET 10, spin 1024',    {'DOTNET_ThreadPool_UnfairSemaphoreSpinLimit': '0x400'}),
    ('cs11',      'cs11', '.NET 11, default (1024)', {}),
    ('cs11_70',   'cs11', '.NET 11, spin 70',      {'DOTNET_ThreadPool_UnfairSemaphoreSpinLimit': '0x46'}),
    ('cs11_0',    'cs11', '.NET 11, spin 0',       {'DOTNET_ThreadPool_UnfairSemaphoreSpinLimit': '0x0'}),
]

def build():
    w.OUT.mkdir(exist_ok=True); w.BUILD.mkdir(exist_ok=True)
    for ver in ('10', '11'):
        name = f'cs{ver}'; d = w.BUILD / name
        if d.exists(): shutil.rmtree(d)
        shutil.copytree(w.HERE / 'cs', d, ignore=shutil.ignore_patterns('bin', 'obj'))
        (d / 'global.json').write_text(json.dumps({'sdk': {'version': w.SDK[ver], 'rollForward': 'disable'}}))
        for pj in d.glob('*.csproj'):
            pj.write_text(pj.read_text().replace('<TargetFramework>net10.0</TargetFramework>', f'<TargetFramework>net{ver}.0</TargetFramework>'))
        o = w.OUT / name
        if o.exists(): shutil.rmtree(o)
        w.sh(['dotnet', 'publish', '-c', 'Release', '-r', 'win-x64', '-o', str(o), '--nologo',
              f'-p:RuntimeFrameworkVersion={w.FX[ver]}', '-p:RollForward=Disable', '-p:SelfContained=false'], cwd=d)
    (w.OUT / 'loadgen').mkdir(exist_ok=True)
    w.sh(['go', 'build', '-o', str(w.OUT / 'loadgen' / 'loadgen.exe'), '.'], cwd=w.HERE / 'loadgen')
    print('built', flush=True)

def sys_busy():
    """(busy, total) seconds across all CPUs, from GetSystemTimes"""
    from ctypes import wintypes, byref
    i, k, u = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    w.k32.GetSystemTimes(byref(i), byref(k), byref(u))
    f = lambda ft: (ft.dwHighDateTime << 32 | ft.dwLowDateTime) / 1e7
    return f(k) + f(u) - f(i), f(k) + f(u)

def wait_idle(limit=0.18, hold=20, cap=7200):
    """block until the whole machine stays under `limit` busy for `hold` seconds (Windows maintenance, scans)"""
    t0 = time.time(); calm = 0; b0, t_0 = sys_busy()
    while calm < hold and time.time() - t0 < cap:
        time.sleep(2); b1, t_1 = sys_busy()
        frac = (b1 - b0) / max(1e-9, t_1 - t_0); b0, t_0 = b1, t_1
        calm = calm + 2 if frac < limit else 0
    waited = time.time() - t0
    if waited > 25: print(f'   (waited {waited:.0f} s for the machine to go idle)', flush=True)
    return round(waited)

def one(cid, build_id, label, extra, port, dur, rate, clock):
    env = w.env_base(); env.update({'PORT': str(port), 'WORKERS': '4'}); env.update(extra)
    exe = w.OUT / build_id / 'paysvc.exe'
    p = w.start_pinned([str(exe)], w.SERVER_MASK, env=env); h = p._handle; t0 = time.perf_counter()
    while not w.health(port):
        if p.poll() is not None or time.perf_counter() - t0 > 30: sys.exit(f'{label} did not start')
        time.sleep(0.002)
    time.sleep(1.0)
    w.loadgen(['-addr', f'127.0.0.1:{port}', '-conns', '64', '-dur', '5s', '-warm', '1s'])   # warm-up
    secs = float(dur[:-1])
    c0 = w.cpu_s(h); a = time.time()
    closed = w.loadgen(['-addr', f'127.0.0.1:{port}', '-conns', '64', '-dur', dur, '-warm', '1s'])
    c1 = w.cpu_s(h); b = time.time()
    closed_cpu = (c1 - c0) * 1e6 / max(1, closed['requests'] * (1 + 1 / secs))
    c2 = w.cpu_s(h); a2 = time.time(); s0 = sys_busy()
    opened = w.loadgen(['-addr', f'127.0.0.1:{port}', '-conns', '64', '-dur', dur, '-warm', '1s', '-rate', str(rate)])
    c3 = w.cpu_s(h); b2 = time.time(); s1 = sys_busy()
    open_cpu = (c3 - c2) * 1e6 / max(1, opened['requests'] * (1 + 1 / secs))
    p.kill(); p.wait()
    r = {'id': cid, 'label': label, 'env': extra,
         'closed': {'rps': closed['rps'], 'p99_us': closed['p99_us'], 'cpu_us_per_req': round(closed_cpu, 2), 'mhz': clock.between(a, b)},
         'open': {'rps': opened['rps'], 'p50_us': opened['p50_us'], 'p99_us': opened['p99_us'], 'p999_us': opened['p999_us'],
                  'cpu_us_per_req': round(open_cpu, 2), 'cores_busy': round((c3 - c2) / (b2 - a2), 3),
                  'machine_cores_busy': round((s1[0] - s0[0]) / (b2 - a2), 2), 'mhz': clock.between(a2, b2)}}
    print(f"   {label:24s} closed {closed['rps']:8.0f} rps {closed_cpu:6.1f} us/req | at {rate}/s {open_cpu:6.1f} us/req, "
          f"{r['open']['cores_busy']:.2f} cores (machine {r['open']['machine_cores_busy']:.2f}), p99 {opened['p99_us']:.0f} us", flush=True)
    return r

def run(a):
    dur = '3s' if a.quick else '10s'; rest = 3 if a.quick else 20
    clock = w.Clock(); time.sleep(2); res = {'rate': a.rate, 'runs': []}
    out = w.HERE / ('spin3_quick.json' if a.quick else 'spin3.json')
    for rnd in range(1, a.rounds + 1):
        order = CONFIGS[rnd % len(CONFIGS):] + CONFIGS[:rnd % len(CONFIGS)]
        if rnd % 2 == 0: order = order[::-1]
        print(f'== round {rnd}', flush=True)
        for i, c in enumerate(order):
            if res['runs']: time.sleep(rest)
            waited = wait_idle()
            r = one(*c, 18080 + i, dur, a.rate, clock); r['round'] = rnd; r['waited_s'] = waited; res['runs'].append(r)
            out.write_text(json.dumps(res, indent=1))
    clock.stop(); print('wrote', out, flush=True)

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['build', 'run'])
    ap.add_argument('--rounds', type=int, default=4); ap.add_argument('--rate', type=int, default=8000); ap.add_argument('--quick', action='store_true')
    a = ap.parse_args()
    build() if a.cmd == 'build' else run(a)
