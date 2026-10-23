#!/usr/bin/env python3
"""Workload tier driver (Windows). Builds the payment service in every variant, load-tests each one pinned to its own
CPUs, runs the GC stress programs, and writes one JSON file per round.

  python workload3.py build                 # build everything into out3\\
  python workload3.py run --round 1         # one round -> w_round1.json (order of services rotates with the round number)
  python workload3.py run --round 1 --quick # short durations, for a smoke test

Server: logical CPUs 0-3 (two physical cores). Load generator: CPUs 4-7. No pip packages needed (uses ctypes).
"""
import argparse, ctypes, json, os, shutil, statistics, subprocess, sys, threading, time, urllib.request
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'out3'; BUILD = HERE / 'build3'
DL = Path(os.environ.get('DOTNET_LOCAL', HERE.parent.parent / 'dotnet-local'))   # side-by-side .NET 10 + 11 RC2 SDKs
SDK = {'10': '10.0.401', '11': '11.0.100-rc.2.26504.105'}
FX = {'10': '10.0.12', '11': '11.0.0-rc.2.26504.105'}
SERVER_MASK, CLIENT_MASK = 0x0F, 0x30   # CPUs 6-7 stay free for Windows and the Claude app
SERVERS = [  # id, label, exe relative to OUT
    ('cs10', 'C# .NET 10 (JIT)', 'cs10/paysvc.exe'),
    ('cs11', 'C# .NET 11 (JIT)', 'cs11/paysvc.exe'),
    ('cs11ra', 'C# .NET 11 (JIT, runtime async)', 'cs11ra/paysvc.exe'),
    ('cs10aot', 'C# .NET 10 (NativeAOT)', 'cs10aot/paysvc.exe'),
    ('cs11aot', 'C# .NET 11 (NativeAOT)', 'cs11aot/paysvc.exe'),
    ('go', 'Go', 'go/paysvc.exe'),
    ('rust', 'Rust (axum)', 'rust/paysvc.exe'),
]
GCS = [  # id, label, exe, env
    ('cs10', 'C# .NET 10 (workstation GC)', 'gc_cs10/gcstress.exe', {}),
    ('cs10srv', 'C# .NET 10 (server GC)', 'gc_cs10/gcstress.exe', {'DOTNET_gcServer': '1'}),
    ('cs11', 'C# .NET 11 (workstation GC)', 'gc_cs11/gcstress.exe', {}),
    ('cs11srv', 'C# .NET 11 (server GC)', 'gc_cs11/gcstress.exe', {'DOTNET_gcServer': '1'}),
    ('go', 'Go', 'gc_go/gcstress.exe', {}),
    ('rust', 'Rust (no GC)', 'gc_rust/gcstress.exe', {}),
]

def env_base():
    e = dict(os.environ)
    e.update({'DOTNET_ROOT': str(DL), 'PATH': f"{DL};{Path.home() / '.cargo' / 'bin'};{e['PATH']}", 'DOTNET_MULTILEVEL_LOOKUP': '0',
              'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'DOTNET_NOLOGO': '1', 'GOTOOLCHAIN': 'go1.27.2'})
    return e

def sh(cmd, cwd=None, env=None):
    print('  $', ' '.join(map(str, cmd)), flush=True)
    env = env or env_base()
    cmd = [shutil.which(cmd[0], path=env['PATH']) or cmd[0]] + list(cmd[1:])   # Windows resolves the program with the parent's PATH otherwise
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f'failed: {cmd}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}')
    return p

# ---------------- build ----------------
def build():
    OUT.mkdir(exist_ok=True); BUILD.mkdir(exist_ok=True)
    def cs_publish(src, name, ver, extra):
        d = BUILD / name
        if d.exists(): shutil.rmtree(d)
        shutil.copytree(src, d, ignore=shutil.ignore_patterns('bin', 'obj'))
        (d / 'global.json').write_text(json.dumps({'sdk': {'version': SDK[ver], 'rollForward': 'disable'}}))
        for pj in d.glob('*.csproj'):   # set the target in the project itself so restore and publish agree
            pj.write_text(pj.read_text().replace('<TargetFramework>net10.0</TargetFramework>', f'<TargetFramework>net{ver}.0</TargetFramework>'))
        o = OUT / name
        if o.exists(): shutil.rmtree(o)
        sh(['dotnet', 'publish', '-c', 'Release', '-r', 'win-x64', '-o', str(o), '--nologo',
            f'-p:RuntimeFrameworkVersion={FX[ver]}', '-p:RollForward=Disable'] + extra, cwd=d)
    for ver in ('10', '11'):
        cs_publish(HERE / 'cs', f'cs{ver}', ver, ['-p:SelfContained=false'])
        cs_publish(HERE / 'cs', f'cs{ver}aot', ver, ['-p:PublishAot=true'])
        cs_publish(HERE / 'gc' / 'cs', f'gc_cs{ver}', ver, ['-p:SelfContained=false'])
    cs_publish(HERE / 'cs', 'cs11ra', '11', ['-p:SelfContained=false', '-p:Features=runtime-async=on'])
    for name, src in (('go', HERE / 'go'), ('gc_go', HERE / 'gc' / 'go'), ('loadgen', HERE / 'loadgen')):
        (OUT / name).mkdir(exist_ok=True)
        exe = 'loadgen.exe' if name == 'loadgen' else ('gcstress.exe' if name == 'gc_go' else 'paysvc.exe')
        sh(['go', 'build', '-o', str(OUT / name / exe), '.'], cwd=src)
    (OUT / 'rust').mkdir(exist_ok=True); (OUT / 'gc_rust').mkdir(exist_ok=True)
    sh(['cargo', '+1.99.0', 'build', '--release', '--target-dir', str(BUILD / 'rust-target')], cwd=HERE / 'rust')
    shutil.copy(BUILD / 'rust-target' / 'release' / 'paysvc.exe', OUT / 'rust' / 'paysvc.exe')
    sh(['rustc', '+1.99.0', '-C', 'opt-level=3', str(HERE / 'gc' / 'rust' / 'main.rs'), '-o', str(OUT / 'gc_rust' / 'gcstress.exe')])
    versions = {
        'go': sh(['go', 'version']).stdout.strip(),
        'rust': sh(['rustc', '+1.99.0', '--version']).stdout.strip(),
        'dotnet10': FX['10'], 'dotnet11': FX['11'],
    }
    (OUT / 'versions.json').write_text(json.dumps(versions))
    print('built:', versions)

# ---------------- Windows process helpers ----------------
k32 = ctypes.WinDLL('kernel32', use_last_error=True) if os.name == 'nt' else None
ntdll = ctypes.WinDLL('ntdll') if os.name == 'nt' else None
class PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [(n, ctypes.c_size_t) for n in (
        'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
        'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]

def mem(h):
    c = PMC(); c.cb = ctypes.sizeof(PMC)
    k32.K32GetProcessMemoryInfo(wintypes.HANDLE(h), ctypes.byref(c), c.cb)
    return c.WorkingSetSize / 1048576, c.PeakWorkingSetSize / 1048576, c.PagefileUsage / 1048576   # MB: current, peak, private

def cpu_s(h):
    t = [wintypes.FILETIME() for _ in range(4)]
    k32.GetProcessTimes(wintypes.HANDLE(h), *[ctypes.byref(x) for x in t])
    f = lambda ft: (ft.dwHighDateTime << 32 | ft.dwLowDateTime) / 1e7
    return f(t[2]) + f(t[3])

def start_pinned(cmd, mask, env=None, stdout=subprocess.DEVNULL):
    """start suspended, pin to CPUs, then resume, so the runtime sizes its thread pool for the pinned CPUs"""
    p = subprocess.Popen(cmd, env=env, stdout=stdout, stderr=subprocess.STDOUT, creationflags=0x4)  # CREATE_SUSPENDED
    k32.SetProcessAffinityMask(wintypes.HANDLE(p._handle), ctypes.c_size_t(mask))
    ntdll.NtResumeProcess(wintypes.HANDLE(p._handle))
    return p

def health(port):
    """raw HTTP over a socket: urllib's proxy lookup alone costs hundreds of ms on Windows"""
    import socket
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5) as s:
            s.sendall(b'GET /health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
            return s.recv(64).startswith(b'HTTP/1.1 200')
    except OSError: return False

class Clock:
    """samples the CPU clock (MHz) once a second with typeperf; % Processor Performance x nominal 2.5 GHz"""
    def __init__(self):
        self.samples = []; self.p = subprocess.Popen(['typeperf', r'\Processor Information(_Total)\% Processor Performance', '-si', '1'],
                                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        threading.Thread(target=self._read, daemon=True).start()
    def _read(self):
        for line in self.p.stdout:
            parts = line.strip().strip('"').split('","')
            if len(parts) == 2:
                try: self.samples.append((time.time(), float(parts[1]) * 25))
                except ValueError: pass
    def between(self, a, b):
        v = sorted(s for t, s in self.samples if a <= t <= b)
        return {'min': round(v[0]), 'med': round(v[len(v) // 2]), 'max': round(v[-1]), 'n': len(v)} if v else None
    def stop(self): self.p.kill()

def loadgen(args):
    p = start_pinned([str(OUT / 'loadgen' / 'loadgen.exe')] + args, CLIENT_MASK, stdout=subprocess.PIPE)
    out, _ = p.communicate()
    return json.loads(out)

def dir_mb(d):
    return sum(f.stat().st_size for f in Path(d).rglob('*') if f.is_file()) / 1048576

# ---------------- run ----------------
def run_server(sid, label, exe, port, dur, rate, clock, open_only=False):
    env = env_base(); env.update({'PORT': str(port), 'WORKERS': '4'})
    exe = OUT / exe
    t0 = time.perf_counter()
    p = start_pinned([str(exe)], SERVER_MASK, env=env)
    h = p._handle
    while not health(port):
        if p.poll() is not None: sys.exit(f'{label} exited during startup')
        if time.perf_counter() - t0 > 30: sys.exit(f'{label} did not start')
        time.sleep(0.002)
    ready_ms = (time.perf_counter() - t0) * 1000
    time.sleep(1.0)
    idle_mb = mem(h)[0]
    res = {'id': sid, 'label': label, 'ready_ms': round(ready_ms, 1), 'idle_mb': round(idle_mb, 1),
           'exe_mb': round(exe.stat().st_size / 1048576, 2), 'dir_mb': round(dir_mb(exe.parent), 1)}
    loadgen(['-addr', f'127.0.0.1:{port}', '-conns', '64', '-dur', '5s', '-warm', '1s'])          # warm-up (JIT tiering, pools)
    if open_only:
        a = time.time()
        opened = loadgen(['-addr', f'127.0.0.1:{port}', '-conns', '64', '-dur', dur, '-warm', '1s', '-rate', str(rate)])
        opened['mhz'] = clock.between(a, time.time()); p.kill(); p.wait()
        print(f"   {label}: at {rate} rps p50 {opened['p50_us']:.0f} p99 {opened['p99_us']:.0f} p99.9 {opened['p999_us']:.0f} us, client send lag p99 {opened['send_lag_p99_us']:.0f} us", flush=True)
        return {'id': sid, 'label': label, 'open': opened}
    c0 = cpu_s(h); a = time.time()
    closed = loadgen(['-addr', f'127.0.0.1:{port}', '-conns', '64', '-dur', dur, '-warm', '1s'])
    c1 = cpu_s(h); b = time.time()
    closed['server_cpu_ms_per_1k'] = round((c1 - c0) * 1e6 / max(1, closed['requests'] * (1 + 1 / float(dur[:-1]))), 2)  # the 1 s warm-up inside this run used CPU too
    closed['mhz'] = clock.between(a, b)
    a = time.time()
    opened = loadgen(['-addr', f'127.0.0.1:{port}', '-conns', '64', '-dur', dur, '-warm', '1s', '-rate', str(rate)])
    opened['mhz'] = clock.between(a, time.time())
    cur, peak, priv = mem(h)
    res.update(closed=closed, open=opened, peak_mb=round(peak, 1), private_mb=round(priv, 1))
    p.kill(); p.wait()
    print(f"   {label}: ready {ready_ms:.0f} ms, idle {idle_mb:.0f} MB, max {closed['rps']:.0f} rps p99 {closed['p99_us']:.0f} us, "
          f"at {rate} rps p99 {opened['p99_us']:.0f} us p99.9 {opened['p999_us']:.0f} us, peak {peak:.0f} MB, cpu {closed['server_cpu_ms_per_1k']} ms/1k", flush=True)
    return res

def run_gc(gid, label, exe, extra, seconds, clock):
    env = env_base(); env.update(extra)
    a = time.time()
    p = start_pinned([str(OUT / exe), '1000000', str(seconds)], SERVER_MASK, env=env, stdout=subprocess.PIPE)
    peak = 0
    def poll():
        nonlocal peak
        while p.poll() is None:
            try: peak = max(peak, mem(p._handle)[1])
            except Exception: pass
            time.sleep(0.2)
    th = threading.Thread(target=poll); th.start()
    out, _ = p.communicate(); th.join()
    r = json.loads(out); r.update(id=gid, label=label, peak_mb=round(peak, 1), mhz=clock.between(a, time.time()))
    print(f"   {label}: {r['iter_per_s']:.0f} it/s, p99 {r['p99_us']:.0f} us, p99.9 {r['p999_us']:.0f} us, max {r['max_us'] / 1000:.1f} ms, "
          f">10ms {r['over_10ms']}, pause {r.get('gc_pause_ms')} ms, peak {peak:.0f} MB", flush=True)
    return r

def run(a):
    dur = '3s' if a.quick else '10s'; gsec = 3 if a.quick else 10; rest = 3 if a.quick else 30
    order = SERVERS[a.round % len(SERVERS):] + SERVERS[:a.round % len(SERVERS)]
    if a.round % 2 == 0: order = order[::-1]
    clock = Clock(); time.sleep(2)
    res = {'round': a.round, 'rate': a.rate, 'versions': json.loads((OUT / 'versions.json').read_text()), 'servers': [], 'gc': []}
    for i, (sid, label, exe) in enumerate(order):
        if i: time.sleep(rest)
        res['servers'].append(run_server(sid, label, exe, 18080 + i, dur, a.rate, clock, a.cmd == 'open'))
    if a.cmd == 'open':
        clock.stop(); out = HERE / f'w_open{a.round}.json'; out.write_text(json.dumps(res, indent=1)); print('wrote', out); return
    gorder = GCS if a.round % 2 else GCS[::-1]
    for gid, label, exe, extra in gorder:
        time.sleep(rest // 2)
        res['gc'].append(run_gc(gid, label, exe, extra, gsec, clock))
    clock.stop()
    out = HERE / f'w_round{a.round}.json'; out.write_text(json.dumps(res, indent=1)); print('wrote', out)

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['build', 'run', 'open'])
    ap.add_argument('--round', type=int, default=1); ap.add_argument('--rate', type=int, default=8000); ap.add_argument('--quick', action='store_true')
    a = ap.parse_args()
    build() if a.cmd == 'build' else run(a)   # 'open' = only the fixed-rate latency test
