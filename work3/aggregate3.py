#!/usr/bin/env python3
"""Merge w_round*.json into data3.json: median (+min/max) across rounds for every numeric field."""
import json, statistics, sys
from pathlib import Path
files = [Path(f) for f in sys.argv[1:-1]]; out = Path(sys.argv[-1])
rounds = [json.loads(f.read_text()) for f in files]
def agg(vals):
    vals = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return {'med': round(statistics.median(vals), 2), 'min': round(min(vals), 2), 'max': round(max(vals), 2)} if vals else None
def merge(items):
    first = items[0]; res = {}
    for k, v in first.items():
        if isinstance(v, dict) and k not in ('codes', 'mhz'):
            res[k] = merge([i[k] for i in items])
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            res[k] = agg([i[k] for i in items])
        else:
            res[k] = v
    res['mhz_min'] = min((i.get('mhz') or {}).get('min', 9e9) for i in items) if 'mhz' in first else None
    return res
servers = [merge([next(s for s in r['servers'] if s['id'] == sid) for r in rounds]) for sid in [s['id'] for s in rounds[0]['servers']]]
for s in servers:
    s['mhz_min'] = min(min((r2[k].get('mhz') or {}).get('min', 9e9) for k in ('closed', 'open')) for r2 in [next(x for x in r['servers'] if x['id'] == s['id']) for r in rounds])
gc = [merge([next(g for g in r['gc'] if g['id'] == gid) for r in rounds]) for gid in [g['id'] for g in rounds[0]['gc']]]
json.dump({'versions': rounds[0]['versions'], 'rate': rounds[0]['rate'], 'rounds': len(rounds), 'servers': servers, 'gc': gc}, out.open('w'), indent=1)
m = lambda d: d['med'] if d else None
print('server            maxrps[min-max]        closed p99   open p50/p99/p999           idle peak priv  cpu/1k  exe/dir MB  mhz_min')
for s in servers:
    c, o = s['closed'], s['open']
    print(f"{s['id']:9} {m(c['rps']):>8.0f} [{c['rps']['min']:.0f}-{c['rps']['max']:.0f}] {m(c['p99_us']):>8.0f}  {m(o['p50_us']):>6.0f}/{m(o['p99_us']):>6.0f}/{m(o['p999_us']):>6.0f} [{o['p99_us']['min']:.0f}-{o['p99_us']['max']:.0f}] "
          f"{m(s['idle_mb']):>4.0f} {m(s['peak_mb']):>4.0f} {m(s['private_mb']):>4.0f} {m(c['server_cpu_ms_per_1k']):>6.1f}  {m(s['exe_mb']):.1f}/{m(s['dir_mb']):.1f}  {s['mhz_min']}  ready {m(s['ready_ms'])}")
print('gc')
for g in gc:
    print(f"{g['id']:8} it/s {m(g['iter_per_s']):>6.0f} [{g['iter_per_s']['min']:.0f}-{g['iter_per_s']['max']:.0f}] p99 {m(g['p99_us'])} p999 {m(g['p999_us'])} [{g['p999_us']['min']}-{g['p999_us']['max']}] max {m(g['max_us'])/1000:.1f}ms [{g['max_us']['min']/1000:.1f}-{g['max_us']['max']/1000:.1f}] >10ms {m(g['over_10ms'])} >1ms {m(g['over_1ms'])} pause {m(g.get('gc_pause_ms'))} peak {m(g['peak_mb'])} heap {m(g.get('heap_mb'))} {g.get('gc_gen2') and m(g['gc_gen2'])} cycles {g.get('gc_cycles') and m(g['gc_cycles'])} stw {g.get('gc_max_stw_ms') and m(g['gc_max_stw_ms'])}")
