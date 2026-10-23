#!/usr/bin/env python3
"""Build Linux binaries on the Windows host, then the Docker images.  python build4.py [step ...]
steps: go rust cs images (default: all). Go cross-compiles natively; Rust targets x86_64-unknown-linux-musl linked with
rust-lld (the crates are pure Rust); C# publishes self-contained for linux-musl-x64 (Alpine)."""
import json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BIN = HERE / 'bin'; BUILD = HERE / 'build'
DL = Path(os.environ.get('DOTNET_LOCAL', HERE.parent.parent / 'dotnet-local'))   # side-by-side .NET 10 + 11 RC2 SDKs
SDK = {'10': '10.0.401', '11': '11.0.100-rc.2.26504.105'}

def env():
    e = dict(os.environ)
    e.update({'DOTNET_ROOT': str(DL), 'PATH': f"{DL};{Path.home() / '.cargo' / 'bin'};{e['PATH']}", 'DOTNET_MULTILEVEL_LOOKUP': '0',
              'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'DOTNET_NOLOGO': '1', 'GOTOOLCHAIN': 'go1.27.2'})
    return e

def sh(cmd, cwd=None, extra=None):
    e = env(); e.update(extra or {})
    cmd = [shutil.which(cmd[0], path=e['PATH']) or cmd[0]] + list(cmd[1:])
    print('  $', ' '.join(map(str, cmd)), flush=True)
    p = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f'failed: {cmd}\n{p.stdout[-4000:]}\n{p.stderr[-4000:]}')
    return p

def go():
    lin = {'GOOS': 'linux', 'GOARCH': 'amd64', 'CGO_ENABLED': '0'}
    for name in ('go', 'mockpay', 'loadgen'):
        d = HERE / name
        sh(['go', 'mod', 'tidy'], cwd=d)
        (BIN / name).mkdir(parents=True, exist_ok=True)
        sh(['go', 'build', '-o', str(BIN / name / 'run'), '.'], cwd=d, extra=lin)

def rust():
    sh(['rustup', 'target', 'add', '--toolchain', '1.99.0', 'x86_64-unknown-linux-musl'])
    sh(['cargo', '+1.99.0', 'build', '--release', '--target', 'x86_64-unknown-linux-musl', '--target-dir', str(BUILD / 'rust-target')],
       cwd=HERE / 'rust', extra={'CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER': 'rust-lld'})
    (BIN / 'rust').mkdir(parents=True, exist_ok=True)
    shutil.copy(BUILD / 'rust-target' / 'x86_64-unknown-linux-musl' / 'release' / 'paysvc', BIN / 'rust' / 'run')

def cs():
    for name, ver, extra in (('cs10', '10', []), ('cs11', '11', []), ('cs11ra', '11', ['-p:Features=runtime-async=on'])):
        d = BUILD / name
        if d.exists(): shutil.rmtree(d)
        shutil.copytree(HERE / 'cs', d, ignore=shutil.ignore_patterns('bin', 'obj'))
        (d / 'global.json').write_text(json.dumps({'sdk': {'version': SDK[ver], 'rollForward': 'disable'}}))
        pj = d / 'paysvc.csproj'; pj.write_text(pj.read_text().replace('<TargetFramework>net10.0</TargetFramework>', f'<TargetFramework>net{ver}.0</TargetFramework>'))
        o = BIN / name
        if o.exists(): shutil.rmtree(o)
        sh(['dotnet', 'publish', '-c', 'Release', '-r', 'linux-musl-x64', '--self-contained', '-o', str(o), '--nologo'] + extra, cwd=d)

def images():
    sh(['docker', 'compose', '-f', str(HERE / 'compose.yml'), '--profile', 'svc', 'build'], cwd=HERE)

if __name__ == '__main__':
    steps = sys.argv[1:] or ['go', 'rust', 'cs', 'images']
    for s in steps:
        print('==', s, flush=True); globals()[s]()
    print('BUILD OK')
