#!/usr/bin/env python3
""".NET 11 feature probes driver (set 2).

Builds cs2/Probes2.cs, rust2/probes2.rs and go2/main.go, measures them, pulls the machine code each
compiler produced for every probe, counts what matters (calls, bounds checks, multiply instructions),
measures startup (wall time + how many methods the JIT had to compile), and writes results2.json.

  python probe2.py --only cs --dotnet 10 --aot       # .NET 10: JIT, ReadyToRun, NativeAOT
  python probe2.py --only cs --dotnet 11 --aot       # .NET 11: JIT (runtime async off + on), ReadyToRun, NativeAOT
  python probe2.py --only rust ; python probe2.py --only go
  python probe2.py --out t1.json ...                 # write elsewhere (used for repeated rounds)
"""
import argparse, json, os, re, shutil, statistics, sys, tempfile, time
from pathlib import Path
from probe import run, bench_runs, timed, trim, rid, os_name, cpu_name, EXE, X86

HERE = Path(__file__).resolve().parent
PROBES = ['gvm', 'dim', 'pairs', 'from_end', 'guard', 'bigmul_s', 'bigmul_u']
SYM = {
    'rust': {p: 'probe_' + p for p in PROBES} | {'async': 'probe_async'},
    'go':   {'gvm': 'main.gvmLoop[', 'dim': 'main.probeDim', 'pairs': 'main.probePairs', 'from_end': 'main.probeFromEnd',
             'guard': 'main.probeGuard', 'bigmul_u': 'main.probeBigMulU', 'async': 'main.chain'},
    'cs':   {'gvm': 'ProbeGvm', 'dim': 'ProbeDim', 'pairs': 'ProbePairs', 'from_end': 'ProbeFromEnd', 'guard': 'ProbeGuard',
             'bigmul_s': 'ProbeBigMulS', 'bigmul_u': 'ProbeBigMulU'},
}
FEAT = {
    'calls':         {'rust': r'^\s*call\b', 'go': r'^\s*CALL\b', 'cs': r'^\s*call\b'},
    'indirect_calls':{'rust': r'^\s*call\s+(qword ptr \[|r[a-z0-9]+\b)', 'go': r'^\s*CALL\s+(\(|[A-Z][A-Z0-9]*$)', 'cs': r'^\s*call\s+(\[|qword ptr \[|r[a-z0-9]+\b)'},
    'gvm_lookups':   {'rust': r'(?!x)x', 'go': r'(?!x)x', 'cs': r'VIRTUAL_FUNC_PTR|GVMLookup|RuntimeHelpers.*Lookup'},
    'bounds_checks': {'rust': r'panic_bounds_check', 'go': r'^\s*CALL\s+runtime\.panic(Index|Bounds|Slice)', 'cs': r'RNGCHKFAIL'},
    'mul_instr':     {'rust': r'^\s*(i?mul|mulx)\b', 'go': r'^\s*(MULQ|IMULQ|MULXQ|IMUL3Q|MULL|IMULL|IMUL3L)\b', 'cs': r'^\s*(i?mul|mulx)\b'},
    'heap_calls':    {'rust': r'__rust_alloc\b|__rdl_alloc|\bmalloc\b', 'go': r'runtime\.(newobject|mallocgc)', 'cs': r'CORINFO_HELP_NEW'},
}

def features(lang, asm):
    t = '\n'.join(asm)
    f = {k: len(re.findall(v[lang], t, re.M)) for k, v in FEAT.items()}
    if lang == 'cs' and f['bounds_checks']:
        # RyuJIT shares one throw block per method, so count the branches that lead to it
        lbl = set(); cur = None
        for l in asm:
            m = re.match(r'^(G_M\d+_IG\d+):', l)
            if m: cur = m.group(1)
            elif 'RNGCHKFAIL' in l and cur: lbl.add(cur)
        f['bounds_checks'] = sum(1 for l in asm if re.match(r'^\s*j\w+\s+(SHORT\s+)?(G_M\d+_IG\d+)', l) and re.match(r'^\s*j\w+\s+(SHORT\s+)?(G_M\d+_IG\d+)', l).group(2) in lbl)
    f['instructions'] = sum(1 for l in asm[1:] if re.match(r'^\s+[a-zA-Z]', l) and not re.match(r'^\s+(align|\.|nop)', l))
    return f

def startup_runs(cmd, env=None, n=7):
    """wall time of the whole process (runtime start-up included) + the in-process timings, median of n"""
    walls, ins = [], []
    for _ in range(n):
        t = time.perf_counter(); p = run(cmd + ['startup'], env=env); walls.append((time.perf_counter() - t) * 1000)
        ins.append(json.loads(p.stdout))
    out = {k: round(statistics.median(r[k] for r in ins), 1) for k in ins[0] if k != 'check'}
    out['wall_ms'] = round(statistics.median(walls), 1)
    return out

# ---------------- Rust ----------------
def do_rust(a, work):
    rustc = (['rustup', 'run', a.rust, 'rustc'] if a.rust else ['rustc']) + ['--edition', '2021']
    ver = run(rustc[:-2] + ['--version']).stdout.strip()
    src = HERE / 'rust2' / 'probes2.rs'; exe = work / ('rs2' + EXE)
    flags = ['-C', 'opt-level=3']
    ms = timed(lambda: run(rustc + flags + [str(src), '-o', str(exe)]))
    run(rustc + flags + ['--emit=asm'] + (['-C', 'llvm-args=-x86-asm-syntax=intel'] if X86 else []) + [str(src), '-o', str(work / 'rs2.s')])
    text = (work / 'rs2.s').read_text().splitlines(); asm = {}
    for p, sym in SYM['rust'].items():
        i = next((n for n, l in enumerate(text) if l in (sym + ':', '_' + sym + ':')), None)
        if i is None: continue
        j = next((k for k in range(i + 1, len(text)) if text[k].startswith(('.Lfunc_end', 'Lfunc_end')) or text[k].strip().startswith(('.seh_endproc', '.def'))), min(len(text), i + 300))
        asm[p] = trim(text[i:j])
    bench = bench_runs([str(exe), 'bench'])
    return dict(id='rust', name='Rust', version=ver, mode='aot', flags='rustc -C opt-level=3', compile_ms=ms, bench=bench,
                startup=startup_runs([str(exe)]), asm=asm, features={p: features('rust', v) for p, v in asm.items()})

# ---------------- Go ----------------
def do_go(a, work):
    env = {'GOTOOLCHAIN': a.go} if a.go else {}
    gdir = work / 'go2'; shutil.copytree(HERE / 'go2', gdir, dirs_exist_ok=True)
    if not (gdir / 'go.mod').exists(): (gdir / 'go.mod').write_text('module probes2\n\ngo 1.22\n')
    ver = run(['go', 'version'], env=env).stdout.strip()
    exe = work / ('go2bin' + EXE); main = gdir / 'main.go'; base = main.read_text(); k = [0]
    def build():
        k[0] += 1; main.write_text(base + f'\n// build {k[0]} {time.time()}\n')
        run(['go', 'build', '-o', str(exe), '.'], env=env, cwd=gdir)
    ms = timed(build)
    main.write_text(base + f'\n// asm {time.time()}\n')
    out = run(['go', 'build', '-o', str(work / 'go2_asm'), '-gcflags=-S', '.'], env=env, cwd=gdir).stderr.splitlines()
    asm = {}
    for p, sym in SYM['go'].items():
        i = next((n for n, l in enumerate(out) if l.startswith(sym) and ' STEXT' in l and (sym.endswith('[') or l.startswith(sym + ' '))), None)
        if i is None: continue
        j = next((n for n in range(i + 1, len(out)) if not out[n].startswith(('\t', ' '))), len(out))
        asm[p] = trim([re.sub(r'^\s*0x[0-9a-f]+ \d+ \(.*?\)\s*', '\t', l) for l in out[i:j] if not re.search(r'PCDATA|FUNCDATA|^\s*0x[0-9a-f]+ [0-9a-f]{2} ', l)])
    build()
    bench = bench_runs([str(exe), 'bench'])
    return dict(id='go', name='Go', version=ver, mode='aot', flags='go build', compile_ms=ms, bench=bench,
                startup=startup_runs([str(exe)]), asm=asm, features={p: features('go', v) for p, v in asm.items()})

# ---------------- C# ----------------
def pick_dotnet(major):
    key = lambda v: [int(x) if x.isdigit() else 0 for x in re.split(r'[.-]', v)]
    sdks = [l.split()[0] for l in run(['dotnet', '--list-sdks']).stdout.splitlines()]
    rts = [l.split()[1] for l in run(['dotnet', '--list-runtimes']).stdout.splitlines() if l.startswith('Microsoft.NETCore.App ')]
    mine = lambda vs: sorted([v for v in vs if v.split('.')[0] == str(major)], key=key)
    if not mine(rts) or not mine(sdks): sys.exit(f'need a .NET {major} SDK and runtime (dotnet --list-sdks / --list-runtimes)')
    sdk, rt = mine(sdks)[-1], mine(rts)[-1]
    root = Path(run(['dotnet', '--list-sdks']).stdout.split(sdk)[1].split('[')[1].split(']')[0]).parent
    return sdk, rt, root

def cs_disasm(cmd, work, tag, env=None):
    f = work / f'jit2_{tag}.txt'
    run(cmd + ['bench'], env=(env or {}) | {'DOTNET_JitDisasm': ' '.join(SYM['cs'].values()), 'DOTNET_JitStdOutFile': str(f)})
    text = f.read_text().splitlines() if f.exists() else []; asm = {}
    starts = [(n, l) for n, l in enumerate(text) if l.startswith('; Assembly listing for method')]
    for k, (n, l) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(text)
        for p, sym in SYM['cs'].items():
            if f':{sym}(' in l: asm[p] = [l.split('for method ')[1]] + trim(text[n + 1:end])   # last listing = final tier
    return asm

def jit_count(cmd, work, tag, env=None):
    """how many methods the JIT compiled during the startup run (0 for NativeAOT)"""
    f = work / f'jitsum_{tag}.txt'
    run(cmd + ['startup'], env=(env or {}) | {'DOTNET_JitDisasmSummary': '1', 'DOTNET_JitStdOutFile': str(f)})
    lines = [l for l in (f.read_text().splitlines() if f.exists() else []) if 'JIT comp' in l or 'Tier' in l]
    return {'jitted_methods': len(lines), 'jitted_comparer_methods': sum(1 for l in lines if 'Comparer' in l)}

def do_cs(a, work):
    sdk, rt, root = pick_dotnet(a.dotnet); mj = rt.split('.')[0]
    csc = root / 'sdk' / sdk / 'Roslyn' / 'bincore' / 'csc.dll'
    refdir = sorted((root / 'packs' / 'Microsoft.NETCore.App.Ref').glob(f'{mj}.*'), key=lambda p: [int(x) if x.isdigit() else 0 for x in re.split(r'[.-]', p.name)])[-1] / 'ref' / f'net{mj}.0'
    refs = [f'-r:{p}' for p in sorted(refdir.glob('*.dll'))]
    variants = [('off', [])] + ([('on', ['-features:runtime-async=on'])] if int(mj) >= 11 else [])
    runs = []
    for tag, feat in variants:
        dll = work / f'p2_{mj}_{tag}.dll'
        ms = timed(lambda: run(['dotnet', str(csc), '-nologo', '-optimize+', '-nostdlib', f'-out:{dll}'] + feat + refs + [str(HERE / 'cs2' / 'Probes2.cs')]))
        (work / f'p2_{mj}_{tag}.runtimeconfig.json').write_text(json.dumps({'runtimeOptions': {'tfm': f'net{mj}.0', 'framework': {'name': 'Microsoft.NETCore.App', 'version': rt}}}))
        cmd = ['dotnet', str(dll)]
        bench = bench_runs(cmd)
        asm = cs_disasm(cmd, work, f'{mj}_{tag}')
        st = startup_runs(cmd) | jit_count(cmd, work, f'{mj}_{tag}')
        label = f'.NET {rt}' + (' · runtime async' if tag == 'on' else '')
        runs.append(dict(id='cs', name='C#', version=label, mode='jit', runtime_async=bench.get('runtime_async'),
                         flags='csc -optimize+' + (' -features:runtime-async=on' if tag == 'on' else ''), compile_ms=ms, bench=bench,
                         startup=st, asm=asm, features={p: features('cs', v) for p, v in asm.items()}))
    if a.aot:
        for kind in ('r2r', 'aot'):
            r = do_cs_publish(sdk, rt, mj, work, kind)
            if r: runs.append(r)
    return runs

def do_cs_publish(sdk, rt, mj, work, kind):
    label = {'r2r': 'ReadyToRun', 'aot': 'NativeAOT'}[kind]
    proj = work / f'cs2_{kind}_{mj}'; proj.mkdir(exist_ok=True)
    shutil.copy(HERE / 'cs2' / 'Probes2.cs', proj / 'Probes2.cs')
    (proj / 'global.json').write_text(json.dumps({'sdk': {'version': sdk, 'rollForward': 'disable'}}))
    prop = '<PublishReadyToRun>true</PublishReadyToRun><SelfContained>false</SelfContained>' if kind == 'r2r' else '<PublishAot>true</PublishAot>'
    (proj / 'probes2.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
        f'<TargetFramework>net{mj}.0</TargetFramework><AssemblyName>probes2</AssemblyName><Nullable>disable</Nullable>'
        f'<ImplicitUsings>disable</ImplicitUsings><InvariantGlobalization>true</InvariantGlobalization><Optimize>true</Optimize>{prop}'
        f'<RuntimeFrameworkVersion>{rt}</RuntimeFrameworkVersion><RollForward>Disable</RollForward>'
        '</PropertyGroup></Project>')
    out = proj / 'out'
    cmd = ['dotnet', 'publish', '-c', 'Release', '-r', rid(), '-o', str(out), '--nologo']
    print(f'   publishing {label}...', flush=True)
    p = run(cmd, cwd=proj, check=False)
    if p.returncode != 0:
        print(f'   {label} publish failed, skipping:\n' + '\n'.join((p.stdout + p.stderr).strip().splitlines()[-8:]), flush=True)
        return None
    ms = timed(lambda: run(cmd + ['--no-restore'], cwd=proj), n=1)
    exe = [str(out / ('probes2' + EXE))]
    bench = bench_runs(exe)
    st = startup_runs(exe) | jit_count(exe, work, f'{mj}_{kind}')
    asm = cs_disasm(exe, work, f'{mj}_{kind}') if kind == 'r2r' else {}
    return dict(id='cs', name='C#', version=f'.NET {rt} · {label}', mode=kind, runtime_async=bench.get('runtime_async'),
                flags=f'dotnet publish -c Release -r {rid()} -p:' + ('PublishReadyToRun=true' if kind == 'r2r' else 'PublishAot=true'),
                compile_ms=ms, bench=bench, startup=st, asm=asm, features={p: features('cs', v) for p, v in asm.items()})

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rust'); ap.add_argument('--go'); ap.add_argument('--dotnet')
    ap.add_argument('--aot', action='store_true'); ap.add_argument('--only', choices=['rust', 'go', 'cs'])
    ap.add_argument('--out', default=str(HERE / 'results2.json'))
    a = ap.parse_args(); out = Path(a.out)
    res = json.loads(out.read_text()) if out.exists() else {'runs': []}
    res['machine'] = {'cpu': cpu_name(), 'os': os_name()}; res['generated'] = time.strftime('%Y-%m-%d %H:%M')
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        for lang, fn in [('rust', do_rust), ('go', do_go), ('cs', do_cs)]:
            if a.only and a.only != lang: continue
            if lang == 'cs' and not a.dotnet: print('== cs skipped (pass --dotnet N)'); continue
            print(f'== {lang} ...', flush=True)
            got = fn(a, work)
            for r in (got if isinstance(got, list) else [got]):
                same = [k for k, x in enumerate(res['runs']) if x['id'] == r['id'] and x['version'] == r['version']]
                if same: res['runs'][same[0]] = r
                else: res['runs'].append(r)
                b = r['bench']
                print(f'   {r["version"]}: ' + ', '.join(f'{p} {b[p]:.0f}' for p in PROBES if p in b) +
                      f', await {b.get("async_ns_per_await")} ns/{b.get("async_bytes_per_await")} B, yield {b.get("yield_ns_per_op")} ns, startup {r["startup"]["wall_ms"]} ms', flush=True)
    out.write_text(json.dumps(res, indent=1))
    print('wrote', out)

if __name__ == '__main__':
    main()
