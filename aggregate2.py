#!/usr/bin/env python3
"""Merge round1..N.json from probe2.py into data2.json: median across rounds (+min/max) per column."""
import json, statistics, sys
from pathlib import Path

files = [Path(f) for f in sys.argv[1:-1]]; out = Path(sys.argv[-1])
cols = {}
machine = None
for f in files:
    d = json.loads(f.read_text()); machine = d.get('machine', machine)
    for r in d['runs']:
        cols.setdefault((r['id'], r['version']), []).append(r)

def agg(vals):
    vals = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not vals: return None
    return {'med': round(statistics.median(vals), 2), 'min': round(min(vals), 2), 'max': round(max(vals), 2), 'n': len(vals)}

res = []
for (cid, ver), rs in cols.items():
    first = rs[0]
    bench = {k: agg([r['bench'].get(k) for r in rs]) for k in first['bench'] if k not in ('check', 'runs', 'n')}
    st = {k: agg([r['startup'].get(k) for r in rs]) for k in first['startup'] if k != 'main_us'}
    res.append(dict(id=cid, name=first['name'], version=ver, mode=first.get('mode'), runtime_async=first.get('runtime_async'),
                    flags=first.get('flags'), compile_ms=agg([r.get('compile_ms') for r in rs]), bench=bench, startup=st,
                    features=first.get('features', {}), asm=first.get('asm', {}), rounds=len(rs)))
out.write_text(json.dumps({'machine': machine, 'runs': res}, indent=1))
for r in res:
    b = r['bench']
    print(f"{r['version'][:52]:52} n={r['rounds']} " + ' '.join(f"{k}={v['med']}" for k, v in b.items() if v) + f" | wall={r['startup'].get('wall_ms')}")
