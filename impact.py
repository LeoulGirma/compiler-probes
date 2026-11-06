#!/usr/bin/env python3
"""Does .NET 11's Math.BigMul codegen slow down library code that calls it? (follow-up to set 2)

Builds cs5/Impact.cs for the newest installed .NET 10 and .NET 11 runtimes, as a framework-dependent JIT app and as
NativeAOT, then runs every build once per round in alternating order and keeps the median per probe.
System.IO.Hashing is pinned to one package version, so both runtimes run the same library code.

  python impact.py --rounds 3 --out impact.json
"""
import argparse, json, statistics, subprocess, sys
from pathlib import Path
import probe2 as p2

HERE = Path(__file__).resolve().parent
HASHING = '10.0.0'

def build(major, kind, work):
    sdk, rt, _ = p2.pick_dotnet(major)
    mj = rt.split('.')[0]
    proj = work / f'impact_{mj}_{kind}'; proj.mkdir(parents=True, exist_ok=True)
    (proj / 'Impact.cs').write_text((HERE / 'cs5' / 'Impact.cs').read_text())
    (proj / 'global.json').write_text(json.dumps({'sdk': {'version': sdk, 'rollForward': 'disable'}}))
    prop = '<PublishAot>true</PublishAot>' if kind == 'aot' else '<SelfContained>false</SelfContained>'
    (proj / 'impact.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
        f'<TargetFramework>net{mj}.0</TargetFramework><AssemblyName>impact</AssemblyName><Nullable>disable</Nullable>'
        f'<ImplicitUsings>disable</ImplicitUsings><InvariantGlobalization>true</InvariantGlobalization><Optimize>true</Optimize>{prop}'
        f'<RuntimeFrameworkVersion>{rt}</RuntimeFrameworkVersion><RollForward>Disable</RollForward></PropertyGroup>'
        f'<ItemGroup><PackageReference Include="System.IO.Hashing" Version="{HASHING}" /></ItemGroup></Project>')
    out = proj / 'out'
    print(f'   publishing .NET {rt} {kind}...', flush=True)
    p2.run(['dotnet', 'publish', '-c', 'Release', '-r', p2.rid(), '-o', str(out), '--nologo'], cwd=proj)
    return dict(id=f'{mj}_{kind}', runtime=rt, kind=kind, exe=str(out / ('impact' + p2.EXE)))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--rounds', type=int, default=3); ap.add_argument('--out', default='impact.json')
    a = ap.parse_args()
    work = HERE / 'work5'; work.mkdir(exist_ok=True)
    builds = [build(m, k, work) for m in (10, 11) for k in ('jit', 'aot')]
    runs = {b['id']: [] for b in builds}
    for r in range(a.rounds):
        order = builds if r % 2 == 0 else builds[::-1]
        print(f'== round {r + 1}', flush=True)
        for b in order:
            res = json.loads(subprocess.run([b['exe']], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
            runs[b['id']].append(res)
            print(f"   {b['id']:8s} " + ' '.join(f'{k}={v:.2f}' for k, v in res.items() if isinstance(v, float)), flush=True)
    keys = [k for k, v in runs[builds[0]['id']][0].items() if isinstance(v, float)]
    summary = {b['id']: dict(runtime=b['runtime'], kind=b['kind'],
               ns={k: dict(med=statistics.median(x[k] for x in runs[b['id']]), min=min(x[k] for x in runs[b['id']]), max=max(x[k] for x in runs[b['id']])) for k in keys})
               for b in builds}
    Path(a.out).write_text(json.dumps(dict(machine=dict(cpu=p2.cpu_name(), os=p2.os_name()), hashing=HASHING, rounds=a.rounds, summary=summary, runs=runs), indent=1))
    print('\nns per op, median: .NET 10 -> .NET 11 (change)')
    for kind in ('jit', 'aot'):
        s10, s11 = summary[f'10_{kind}']['ns'], summary[f'11_{kind}']['ns']
        print(f'  {kind}:')
        for k in keys:
            x, y = s10[k]['med'], s11[k]['med']
            print(f'    {k:20s} {x:9.3f} -> {y:9.3f}  ({(y / x - 1) * 100:+5.0f}%)')
    print('wrote', a.out)

if __name__ == '__main__':
    main()
