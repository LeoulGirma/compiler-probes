#!/usr/bin/env python3
"""Compiler probes driver.

Builds the same probe program in Rust, Go and C#, measures it, extracts the
machine code the compiler produced, and writes everything to results.json.

  python3 probe.py                        # whatever rustc / go / dotnet are on PATH
  python3 probe.py --rust 1.99.0          # uses `rustup run 1.99.0 rustc`
  python3 probe.py --go go1.27.2          # uses GOTOOLCHAIN=go1.27.2
  python3 probe.py --dotnet 10            # newest installed SDK + runtime with major 10
  python3 probe.py --only cs --dotnet 11  # add a .NET 11 column to an existing results.json
  python3 probe.py --only cs --dotnet 10 --aot   # plus ReadyToRun and NativeAOT builds

Needs only Python 3.8+ and the toolchains. No NuGet, no cargo, no network.
"""
import argparse, json, os, platform, re, shutil, statistics, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBES = ['vec_sum', 'bounds_one', 'bounds_two', 'dyn', 'alloc']
SYM = {  # function names per language
    'rust': {'vec_sum': 'probe_vec_sum', 'bounds_one': 'probe_bounds_one', 'bounds_two': 'probe_bounds_two', 'dyn': 'probe_dyn', 'alloc': 'probe_alloc', 'generic': 'probe_generic'},
    'go':   {'vec_sum': 'main.probeVecSum', 'bounds_one': 'main.probeBoundsOne', 'bounds_two': 'main.probeBoundsTwo', 'dyn': 'main.probeDyn', 'alloc': 'main.probeAlloc'},
    'cs':   {'vec_sum': 'ProbeVecSum', 'bounds_one': 'ProbeBoundsOne', 'bounds_two': 'ProbeBoundsTwo', 'dyn': 'ProbeDyn', 'alloc': 'ProbeAlloc'},
}
FEAT = {  # regexes over each function's machine code (x86-64 and arm64)
    'vector_add':    {'rust': r'\bv?padd[dq]\b|\badd\s+v\d+\.4s', 'go': r'\bV?PADD[DQ]\b|\bVADD\b', 'cs': r'\bv?padd[dq]\b|\badd\s+v\d+\.4s'},
    'bounds_checks': {'rust': r'panic_bounds_check', 'go': r'runtime\.panic(Index|Bounds)', 'cs': r'RNGCHKFAIL'},
    'indirect_calls':{'rust': r'\bcall\s+(qword ptr \[|r[a-z0-9]+\b)|\bblr\b', 'go': r'\bCALL\s+(\(|[A-Z][A-Z0-9]*$)', 'cs': r'\bcall\s+(\[|qword ptr \[|r[a-z0-9]+\b)|\bblr\b'},
    'heap_calls':    {'rust': r'__rust_alloc\b|__rdl_alloc|\bmalloc\b', 'go': r'runtime\.(newobject|mallocgc)', 'cs': r'CORINFO_HELP_NEW'},
}
X86 = platform.machine().lower() in ('x86_64', 'amd64')
EXE = '.exe' if os.name == 'nt' else ''

def run(cmd, env=None, cwd=None, check=True):
    e = dict(os.environ); e.update(env or {})
    p = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True)
    if check and p.returncode != 0:
        sys.exit(f"command failed: {' '.join(map(str, cmd))}\n{p.stdout}\n{p.stderr}")
    return p

def bench_runs(cmd, env=None, cwd=None, n=3):
    """run the bench process n times; median of every numeric field (process-to-process noise is the biggest error)"""
    rs = [json.loads(run(cmd, env=env, cwd=cwd).stdout) for _ in range(n)]
    out = dict(rs[0])
    for k, v in rs[0].items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and k != 'check':
            out[k] = round(statistics.median(r[k] for r in rs), 1)
    out['runs'] = n
    return out

def timed(fn, n=3):
    ts = []
    for _ in range(n):
        t = time.perf_counter(); fn(); ts.append((time.perf_counter() - t) * 1000)
    return round(statistics.median(ts), 1)

def buckets(calls):
    out, lo = [], 1
    while lo <= len(calls):
        hi = min(len(calls), lo * 2 - 1)
        out.append([lo, hi, statistics.median(calls[lo - 1:hi])])
        lo = hi + 1
    return out

def features(lang, asm):
    return {k: len(re.findall(v[lang], '\n'.join(asm), re.M)) for k, v in FEAT.items()}

def trim(lines):
    keep = []
    for l in lines:
        s = l.rstrip()
        if not s.strip() or s.strip().startswith(('.cfi', '.seh_', '.p2align', '#', ';;', '; ')) and 'offset' not in s: continue
        keep.append(s)
    return keep[:120]

# ---------------- Rust ----------------
def do_rust(a, work):
    rustc = ['rustup', 'run', a.rust, 'rustc'] if a.rust else ['rustc']
    ver = run(rustc + ['--version']).stdout.strip()
    src = HERE / 'rust' / 'probes.rs'; exe = work / ('rs_probes' + EXE)
    flags = ['-C', 'opt-level=3']                      # = cargo build --release
    ms = timed(lambda: run(rustc + flags + [str(src), '-o', str(exe)]))
    run(rustc + flags + ['--emit=asm'] + (['-C', 'llvm-args=-x86-asm-syntax=intel'] if X86 else []) + [str(src), '-o', str(work / 'rs.s')])
    text = (work / 'rs.s').read_text().splitlines()
    asm = {}
    for p, sym in SYM['rust'].items():
        i = next((n for n, l in enumerate(text) if l in (sym + ':', '_' + sym + ':')), None)
        if i is None: continue
        # ELF/Mach-O end a function with a func_end label; Windows COFF has none, so stop at .seh_endproc or the next .def
        j = next((k for k in range(i + 1, len(text)) if text[k].startswith(('.Lfunc_end', 'Lfunc_end')) or text[k].strip().startswith(('.seh_endproc', '.def'))), min(len(text), i + 200))
        asm[p] = trim(text[i:j])
    bench = bench_runs([str(exe), 'bench'])
    warm = json.loads(run([str(exe), 'warmup']).stdout)['calls_ns']
    feats = {p: features('rust', asm.get(p, [])) for p in PROBES}
    # the counting allocator disables LLVM's heap-allocation removal, so allocations are read from the machine code
    bench['alloc_per_elem'] = 1.0 if feats['alloc']['heap_calls'] else 0.0
    bench['alloc_bytes_per_elem'] = 16.0 if feats['alloc']['heap_calls'] else 0.0
    return dict(id='rust', name='Rust', version=ver, flags='rustc -C opt-level=3 (cargo --release)', compile_ms=ms,
                bench=bench, warmup=buckets(warm), asm=asm, features=feats)

# ---------------- Go ----------------
def do_go(a, work):
    env = {'GOTOOLCHAIN': a.go} if a.go else {}
    gdir = work / 'go'; shutil.copytree(HERE / 'go', gdir, dirs_exist_ok=True)
    if not (gdir / 'go.mod').exists(): (gdir / 'go.mod').write_text('module probes\n\ngo 1.22\n')
    ver = run(['go', 'version'], env=env).stdout.strip()
    exe = work / ('go_probes' + EXE); main = gdir / 'main.go'; base = main.read_text(); k = [0]
    def build():  # touch the source so only our package recompiles (std stays cached, like Rust's prebuilt std)
        k[0] += 1; main.write_text(base + f'\n// build {k[0]} {time.time()}\n')
        run(['go', 'build', '-o', str(exe), '.'], env=env, cwd=gdir)
    ms = timed(build)
    def go_asm(extra):
        main.write_text(base + f'\n// asm {time.time()}\n')
        out = run(['go', 'build', '-o', str(work / 'go_asm_bin'), '-gcflags=-S'] + extra + ['.'], env=env, cwd=gdir).stderr.splitlines()
        res = {}
        for p, sym in SYM['go'].items():
            i = next((n for n, l in enumerate(out) if l.startswith(sym + ' STEXT')), None)
            if i is None: continue
            j = next((n for n in range(i + 1, len(out)) if not out[n].startswith(('\t', ' '))), len(out))
            lines = [re.sub(r'^\s*0x[0-9a-f]+ \d+ \(.*?\)\s*', '', l) for l in out[i:j] if not re.search(r'PCDATA|FUNCDATA|^\s*0x[0-9a-f]+ [0-9a-f]{2} ', l)]
            res[p] = trim(lines)
        return res
    build(); asm = go_asm([])
    bench = bench_runs([str(exe), 'bench'])
    warm = json.loads(run([str(exe), 'warmup']).stdout)['calls_ns']
    # profile-guided optimisation: profile the interface-call probe, rebuild with it
    prof = work / 'cpu.pprof'; run([str(exe), 'prof', str(prof)])
    main.write_text(base); run(['go', 'build', '-pgo=' + str(prof), '-o', str(work / ('go_pgo' + EXE)), '.'], env=env, cwd=gdir)
    pgo = bench_runs([str(work / ('go_pgo' + EXE)), 'bench'])
    asm_pgo = go_asm(['-pgo=' + str(prof)])
    bench['dyn_pgo'] = pgo['dyn']
    feats = {p: features('go', asm.get(p, [])) for p in PROBES}
    feats['dyn_pgo'] = features('go', asm_pgo.get('dyn', []))
    asm['dyn_pgo'] = asm_pgo.get('dyn', [])
    return dict(id='go', name='Go', version=ver, flags='go build (defaults) · PGO column: go build -pgo=profile', compile_ms=ms,
                bench=bench, warmup=buckets(warm), asm=asm, features=feats)

# ---------------- C# ----------------
def do_cs(a, work):
    major = a.dotnet
    sdks = [l.split()[0] for l in run(['dotnet', '--list-sdks']).stdout.splitlines()]
    rts = [l.split()[1] for l in run(['dotnet', '--list-runtimes']).stdout.splitlines() if l.startswith('Microsoft.NETCore.App ')]
    pick = lambda vs: sorted([v for v in vs if not major or v.split('.')[0] == str(major)], key=lambda v: [int(x) if x.isdigit() else 0 for x in re.split(r'[.-]', v)])[-1]
    if not [v for v in rts if not major or v.split('.')[0] == str(major)]: sys.exit(f'no .NET {major} runtime installed (dotnet --list-runtimes)')
    # a newer SDK's compiler can target an older runtime, so fall back to the newest SDK when that major has none
    sdk, rt = (pick(sdks) if [v for v in sdks if v.split('.')[0] == str(major)] or not major else sorted(sdks, key=lambda v: [int(x) if x.isdigit() else 0 for x in re.split(r'[.-]', v)])[-1]), pick(rts)
    root = Path(run(['dotnet', '--list-sdks']).stdout.split(sdk)[1].split('[')[1].split(']')[0]).parent
    csc = root / 'sdk' / sdk / 'Roslyn' / 'bincore' / 'csc.dll'
    mj = rt.split('.')[0]
    refdir = sorted((root / 'packs' / 'Microsoft.NETCore.App.Ref').glob(f'{mj}.*'))[-1] / 'ref' / f'net{mj}.0'
    refs = [f'-r:{p}' for p in sorted(refdir.glob('*.dll'))]
    dll = work / f'cs{mj}.dll'
    ms = timed(lambda: run(['dotnet', str(csc), '-nologo', '-optimize+', '-nostdlib', f'-out:{dll}'] + refs + [str(HERE / 'cs' / 'Probes.cs')]))
    (work / f'cs{mj}.runtimeconfig.json').write_text(json.dumps({'runtimeOptions': {'tfm': f'net{mj}.0', 'framework': {'name': 'Microsoft.NETCore.App', 'version': rt}}}))
    bench = bench_runs(['dotnet', str(dll), 'bench'])
    nopgo = bench_runs(['dotnet', str(dll), 'bench'], env={'DOTNET_TieredPGO': '0'})
    warm = json.loads(run(['dotnet', str(dll), 'warmup']).stdout)['calls_ns']
    jit = work / f'jit{mj}.txt'
    run(['dotnet', str(dll), 'bench'], env={'DOTNET_JitDisasm': 'Probe*', 'DOTNET_JitStdOutFile': str(jit)})
    text = jit.read_text().splitlines(); asm = {}
    starts = [(n, l) for n, l in enumerate(text) if l.startswith('; Assembly listing for method')]
    for k, (n, l) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(text)
        for p, sym in SYM['cs'].items():
            if f':{sym}(' in l: asm[p] = [l.split('for method ')[1]] + trim(text[n + 1:end])   # keep the last (final tier)
    bench['dyn_nopgo'] = nopgo['dyn']
    feats = {p: features('cs', asm.get(p, [])) for p in PROBES}
    runs = [dict(id='cs', name='C#', version=f'.NET {rt} (SDK {sdk})', flags='csc -optimize+ · runtime defaults (tiered + dynamic PGO) · no-PGO column: DOTNET_TieredPGO=0',
                compile_ms=ms, bench=bench, warmup=buckets(warm), asm=asm, features=feats)]
    if a.aot:
        for kind in ('r2r', 'aot'):
            r = do_cs_publish(sdk, rt, work, kind)
            if r: runs.append(r)
    return runs

def rid():
    arch = 'arm64' if platform.machine().lower() in ('arm64', 'aarch64') else 'x64'
    osn = 'win' if os.name == 'nt' else 'osx' if sys.platform == 'darwin' else 'linux'
    return f'{osn}-{arch}'

def do_cs_publish(sdk, rt, work, kind):
    """ReadyToRun (precompiled, JIT still tiers up) or NativeAOT (no JIT at all), built with `dotnet publish`.
    Needs network once for the crossgen2 / ILCompiler packages; NativeAOT also needs the platform linker
    (Windows: Visual Studio 'Desktop development with C++'; Linux: clang; macOS: Xcode tools)."""
    label = {'r2r': 'ReadyToRun', 'aot': 'NativeAOT'}[kind]
    mj = rt.split('.')[0]
    proj = work / f'cs_{kind}_{mj}'; proj.mkdir(exist_ok=True)
    shutil.copy(HERE / 'cs' / 'Probes.cs', proj / 'Probes.cs')
    (proj / 'global.json').write_text(json.dumps({'sdk': {'version': sdk, 'rollForward': 'latestFeature'}}))
    prop = '<PublishReadyToRun>true</PublishReadyToRun><SelfContained>false</SelfContained>' if kind == 'r2r' else '<PublishAot>true</PublishAot>'
    (proj / 'probes.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
        f'<TargetFramework>net{mj}.0</TargetFramework><AssemblyName>probes</AssemblyName><Nullable>disable</Nullable>'
        f'<ImplicitUsings>disable</ImplicitUsings><InvariantGlobalization>true</InvariantGlobalization><Optimize>true</Optimize>{prop}'
        '</PropertyGroup></Project>')
    out = proj / 'out'
    cmd = ['dotnet', 'publish', '-c', 'Release', '-r', rid(), '-o', str(out), '--nologo']
    print(f'   publishing {label} (first time downloads the compiler package)...', flush=True)
    p = run(cmd, cwd=proj, check=False)
    if p.returncode != 0:
        tail = '\n'.join((p.stdout + p.stderr).strip().splitlines()[-8:])
        print(f'   {label} publish failed, skipping:\n{tail}', flush=True)
        return None
    ms = timed(lambda: run(cmd + ['--no-restore'], cwd=proj), n=1)
    exe = out / ('probes' + EXE)
    bench = bench_runs([str(exe), 'bench'])
    warm = json.loads(run([str(exe), 'warmup']).stdout)['calls_ns']
    return dict(id='cs', name='C#', version=f'.NET {rt} · {label}', mode=kind,
                flags=f'dotnet publish -c Release -r {rid()} -p:' + ('PublishReadyToRun=true' if kind == 'r2r' else 'PublishAot=true'),
                compile_ms=ms, bench=bench, warmup=buckets(warm), asm={}, features=None)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rust'); ap.add_argument('--go'); ap.add_argument('--dotnet')
    ap.add_argument('--aot', action='store_true', help='C#: also build ReadyToRun and NativeAOT variants');
    ap.add_argument('--only', choices=['rust', 'go', 'cs']); ap.add_argument('--out', default=str(HERE / 'results.json'))
    a = ap.parse_args()
    out = Path(a.out)
    res = json.loads(out.read_text()) if out.exists() and a.only else {'runs': []}
    res['machine'] = {'cpu': cpu_name(), 'os': os_name(), 'python': platform.python_version()}
    res['generated'] = time.strftime('%Y-%m-%d %H:%M %Z')
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        for lang, fn in [('rust', do_rust), ('go', do_go), ('cs', do_cs)]:
            if a.only and a.only != lang: continue
            print(f'== {lang} ...', flush=True)
            got = fn(a, work)
            for r in (got if isinstance(got, list) else [got]):
                same = [k for k, x in enumerate(res['runs']) if x['id'] == r['id'] and x['version'] == r['version']]
                if same: res['runs'][same[0]] = r          # keep column order stable on re-runs
                else: res['runs'].append(r)
                print(f'   {r["version"]}: ' + ', '.join(f'{p} {r["bench"][p]:.0f} ns' for p in PROBES), flush=True)
    out.write_text(json.dumps(res, indent=1))
    print('wrote', out)

def os_name():
    p = platform.platform()
    # older Pythons report Windows 11 as "Windows-10-10.0.22000+"
    if p.startswith('Windows-10-') and int((platform.version().split('.') + ['0'] * 3)[2] or 0) >= 22000: p = 'Windows-11-' + p[len('Windows-10-'):]
    return p

def cpu_name():
    try:
        for l in open('/proc/cpuinfo'):
            if l.startswith('model name'): return l.split(':', 1)[1].strip()
    except OSError: pass
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as k:
            return winreg.QueryValueEx(k, 'ProcessorNameString')[0].strip()
    except (ImportError, OSError): pass
    return platform.processor() or platform.machine()

if __name__ == '__main__':
    main()
