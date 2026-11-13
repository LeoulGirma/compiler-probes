#!/usr/bin/env python3
"""Scenario driver for the production-shaped stack (Windows host, Docker Desktop).

  python run4.py up                      start db, redis, mockpay, loadgen
  python run4.py round --round 1         cold start, steady 500 payments/s (--rate), max throughput, provider degradation, for every service
  python run4.py soak --minutes 8        long steady run per service: memory and latency drift
  python run4.py round --quick           short durations for a smoke test
Results: r4_round<N>.json / r4_soak.json.
"""
import argparse, datetime, json, os, re, subprocess, sys, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPOSE = ['docker', 'compose', '-f', str(HERE / 'compose.yml')]
SERVICES = [('cs10', 'C# .NET 10'), ('cs11', 'C# .NET 11'), ('cs11s70', 'C# .NET 11, spin limit 70'), ('cs11ra', 'C# .NET 11 + runtime async'), ('cs11pgo0', 'C# .NET 11, dynamic PGO off'), ('cs11tc0', 'C# .NET 11, tiered compilation off'), ('go', 'Go'), ('rust', 'Rust'),
            ('cs10aot', 'C# .NET 10 NativeAOT'), ('cs11aot', 'C# .NET 11 NativeAOT'),
            ('cs10aotx', 'C# .NET 10 NativeAOT, Speed + native ISA'), ('cs11aotx', 'C# .NET 11 NativeAOT, Speed + native ISA')]
NORMAL = 'median=30&sigma=0.6&fail=0.01'
DEGRADED = 'median=300&sigma=0.8&fail=0.10'

def sh(cmd, check=True, timeout=None):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        sys.exit(f'failed: {" ".join(cmd)}\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}')
    return p.stdout

def lg(*args, timeout=900):
    return json.loads(sh(['docker', 'exec', 'loadgen', '/app/run', '-addr', 'svc:8080'] + list(args), timeout=timeout))

def psql(sql):
    return sh(['docker', 'exec', 'db', 'psql', '-U', 'pay', '-d', 'pay', '-tAc', sql]).strip()

def provider(mode):
    sh(['docker', 'exec', 'loadgen', 'wget', '-qO-', '--post-data=', f'http://mockpay:9000/mode?{mode}'])

UNITS = {'B': 1 / 1048576, 'KiB': 1 / 1024, 'MiB': 1, 'GiB': 1024}
def mem_mb(s):
    m = re.match(r'([\d.]+)\s*([KMG]?i?B)', s.strip())
    return float(m.group(1)) * UNITS.get(m.group(2), 1) if m else None

def cg_stat(name):
    """the container's CPU-quota counters (cgroup v2 cpu.stat: nr_periods, nr_throttled, throttled_usec), or None"""
    try:
        cid = subprocess.run(['docker', 'inspect', '-f', '{{.Id}}', name], capture_output=True, text=True).stdout.strip()
        for f in (f'/sys/fs/cgroup/system.slice/docker-{cid}.scope/cpu.stat', f'/sys/fs/cgroup/docker/{cid}/cpu.stat'):
            if cid and os.path.exists(f):
                return {k: int(v) for k, v in (l.split() for l in open(f) if l.strip())}
    except (OSError, ValueError):
        pass
    return None

def host_cpu():
    """(busy, total, steal) jiffies for the whole host on Linux, else None: shows whether something else was running"""
    try:
        v = [int(x) for x in open('/proc/stat').readline().split()[1:9]]
        return sum(v) - v[3] - v[4], sum(v), v[7]
    except OSError:
        return None

class Stats:
    """samples docker stats for one container about once a second"""
    def __init__(self, name):
        self.name, self.samples, self.stop_ = name, [], False
        self.cg0, self.h0, self.t0 = cg_stat(name), host_cpu(), time.time()
        self.t = threading.Thread(target=self.loop, daemon=True); self.t.start()
    def loop(self):
        while not self.stop_:
            out = subprocess.run(['docker', 'stats', '--no-stream', '--format', '{{.MemUsage}}|{{.CPUPerc}}', self.name], capture_output=True, text=True).stdout.strip()
            if '|' in out:
                mu, cpu = out.split('|')
                try: self.samples.append((time.time(), mem_mb(mu.split('/')[0]), float(cpu.strip('%'))))
                except ValueError: pass
            time.sleep(0.5)
    def stop(self):
        self.stop_ = True; self.t.join(timeout=5)
        mems = [m for _, m, _ in self.samples if m is not None]; cpus = sorted(c for _, _, c in self.samples)
        cg1, h1, extra = cg_stat(self.name), host_cpu(), {}
        if self.cg0 and cg1:
            d = {k: cg1.get(k, 0) - self.cg0.get(k, 0) for k in ('nr_periods', 'nr_throttled', 'throttled_usec', 'usage_usec')}
            extra['throttle'] = {'periods': d['nr_periods'], 'throttled': d['nr_throttled'], 'throttled_ms': round(d['throttled_usec'] / 1000),
                                 'throttled_pct': round(100 * d['nr_throttled'] / max(1, d['nr_periods']), 1),
                                 'cpu_pct': round(100 * d['usage_usec'] / 1e6 / max(1e-9, time.time() - self.t0), 1)}
        if self.h0 and h1:
            tot = max(1, h1[1] - self.h0[1])
            extra['host'] = {'busy_pct': round(100 * (h1[0] - self.h0[0]) / tot, 1), 'steal_pct': round(100 * (h1[2] - self.h0[2]) / tot, 2)}
        return {**extra, 'mem_peak_mb': round(max(mems), 1) if mems else None, 'mem_last_mb': round(mems[-1], 1) if mems else None,
                'cpu_median_pct': round(cpus[len(cpus) // 2], 1) if cpus else None,
                'series': [(round(t - self.samples[0][0], 1), round(m or 0, 1), c) for t, m, c in self.samples]}

def integrity():
    """every captured payment must be counted in exactly one merchant balance"""
    captured, counted, failed, pending = psql("SELECT (SELECT count(*) FROM payments WHERE status='captured'), (SELECT coalesce(sum(count),0) FROM balances), "
                                              "(SELECT count(*) FROM payments WHERE status='failed'), (SELECT count(*) FROM payments WHERE status='pending')").split('|')
    return {'captured': int(captured), 'balance_count': int(counted), 'failed': int(failed), 'pending': int(pending), 'consistent': captured == counted}

def start(svc):
    sh(COMPOSE + ['--profile', 'svc', 'rm', '-sf', svc], check=False)
    psql('TRUNCATE payments; TRUNCATE balances;')
    sh(COMPOSE + ['--profile', 'svc', 'up', '-d', '--no-deps', svc])
    started = sh(['docker', 'inspect', '-f', '{{.State.StartedAt}}', svc]).strip()
    w = lg('-mode', 'wait', timeout=120)
    # StartedAt has nanosecond precision: 2026-10-22T08:05:48.730188123Z
    base = datetime.datetime.strptime(started[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp() * 1e9
    frac = re.search(r'\.(\d+)', started); base += int((frac.group(1) + '000000000')[:9]) if frac else 0
    return {'ready_ms': round((w['health_unix_ns'] - base) / 1e6, 1), 'first_pay_ms': round((w['first_pay_unix_ns'] - base) / 1e6, 1)}

def stop(svc):
    sh(COMPOSE + ['--profile', 'svc', 'rm', '-sf', svc], check=False)

def run_service(svc, label, q):
    r = {'id': svc, 'label': label}
    r['startup'] = start(svc)
    time.sleep(3)
    s = Stats(svc); time.sleep(3); r['idle'] = s.stop()
    provider(NORMAL)
    # CPU and memory are sampled only after the warm-up, so JIT tier-up after a cold start is not counted as steady-state cost
    res0 = {}
    th = threading.Thread(target=lambda: res0.update(lg('-mode', 'open', '-rate', str(q['rate']), '-dur', q['steady'], '-warm', f"{q['warm']}s", '-conns', '512', '-series')))
    th.start(); time.sleep(q['warm'] + 0.1); s = Stats(svc); th.join()
    r['steady'] = res0; r['steady_stats'] = s.stop(); r['steady_integrity'] = integrity()
    time.sleep(q['rest'])
    s = Stats(svc)
    r['max'] = lg('-mode', 'closed', '-conns', '256', '-dur', q['max'], '-warm', '5s')
    r['max_stats'] = s.stop()
    time.sleep(q['rest'])
    # degradation: the provider turns slow and flaky for a third of the run
    s = Stats(svc); res = {}
    th = threading.Thread(target=lambda: res.update(lg('-mode', 'open', '-rate', str(q['rate']), '-dur', q['deg'], '-warm', '5s', '-conns', '2048', '-series', '-timeout', '10s')))
    pg, pg_stop = [], threading.Event()
    def pg_loop():   # database connections by state, every 2 s: shows pool starvation or lock waits if the service stalls
        t0 = time.time()
        while not pg_stop.is_set():
            try: pg.append((round(time.time() - t0, 1), psql("SELECT coalesce(state,'?')||':'||count(*) FROM pg_stat_activity WHERE datname='pay' AND pid<>pg_backend_pid() GROUP BY state").replace('\n', ' ')))
            except SystemExit: pass
            time.sleep(2)
    pt = threading.Thread(target=pg_loop, daemon=True)
    th.start(); pt.start(); third = int(q['deg'][:-1]) / 3
    time.sleep(5 + third); provider(DEGRADED); time.sleep(third); provider(NORMAL); th.join(); pg_stop.set(); pt.join(timeout=5)
    r['degrade'] = res; r['degrade_stats'] = s.stop(); r['degrade_integrity'] = integrity(); r['degrade_pg'] = pg
    r['alive_after'] = sh(['docker', 'inspect', '-f', '{{.State.Running}} {{.State.OOMKilled}} {{.RestartCount}}', svc]).strip()
    lg_ = subprocess.run(['docker', 'logs', '--tail', '400', svc], capture_output=True, text=True)
    r['log_tail'] = [l for l in (lg_.stdout + lg_.stderr).splitlines() if '"LogLevel":"Information"' not in l and 'provider failed' not in l][-150:]
    stop(svc)
    st, d = r['steady'], r['degrade']
    print(f"   {label}: ready {r['startup']['ready_ms']} ms, first pay {r['startup']['first_pay_ms']} ms, idle {r['idle']['mem_last_mb']} MB | "
          f"{q['rate']} rps p50 {st.get('ok_p50_ms', st['p50_ms']):.1f} p99 {st.get('ok_p99_ms', st['p99_ms']):.1f} p99.9 {st.get('ok_p999_ms', st['p999_ms']):.1f} ms, cpu {r['steady_stats']['cpu_median_pct']}%, "
          f"throttled {r['steady_stats'].get('throttle', {}).get('throttled_pct')}%, host steal {r['steady_stats'].get('host', {}).get('steal_pct')}%, mem {r['steady_stats']['mem_peak_mb']} MB, "
          f"codes {st['codes']} | max {r['max']['good_rps']:.0f} rps | degraded ok-p99 {d.get('ok_p99_ms', d['p99_ms']):.0f} ms, mem {r['degrade_stats']['mem_peak_mb']} MB, "
          f"codes {d['codes']} | {r['alive_after']} | consistent {r['steady_integrity']['consistent']}/{r['degrade_integrity']['consistent']}", flush=True)
    return r

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['up', 'round', 'soak'])
    ap.add_argument('--round', type=int, default=1); ap.add_argument('--quick', action='store_true'); ap.add_argument('--minutes', type=int, default=8)
    ap.add_argument('--only'); ap.add_argument('--rate', type=int, default=500); ap.add_argument('--tag', default='')
    ap.add_argument('--keep-order', action='store_true', help='run --only services in the order given (no rotation)'); a = ap.parse_args()
    if a.cmd == 'up':
        sh(COMPOSE + ['up', '-d', '--wait', 'db', 'redis', 'mockpay', 'loadgen'], timeout=600); print('stack up'); return
    q = {'steady': '15s', 'max': '10s', 'deg': '30s', 'rest': 3, 'warm': 5} if a.quick else {'steady': '60s', 'max': '30s', 'deg': '90s', 'rest': 10, 'warm': 45}
    q['rate'] = a.rate
    svcs = [s for s in SERVICES if s[0] in a.only.split(',')] if a.only else SERVICES[:5]
    if a.keep_order and a.only:
        svcs = sorted(svcs, key=lambda s: a.only.split(',').index(s[0]))
    else:
        k = a.round % len(svcs); svcs = svcs[k:] + svcs[:k]
        if a.round % 2 == 0: svcs = svcs[::-1]
    info = {'docker': sh(['docker', 'info', '--format', '{{.ServerVersion}} {{.NCPU}} {{.MemTotal}}']).strip()}
    if a.cmd == 'round':
        res = {'round': a.round, 'quick': a.quick, 'info': info, 'services': [run_service(s, l, q) for s, l in svcs], 'rate': a.rate}
        out = HERE / f'r4{a.tag}_round{a.round}{"_quick" if a.quick else ""}.json'
    else:
        res = {'minutes': a.minutes, 'info': info, 'services': [], 'rate': a.rate}
        for svc, label in svcs:
            start(svc); time.sleep(3); provider(NORMAL)
            box = {}
            th = threading.Thread(target=lambda: box.update(lg('-mode', 'open', '-rate', str(a.rate), '-dur', f'{a.minutes * 60}s', '-warm', '45s', '-conns', '512', '-series', timeout=a.minutes * 60 + 300)))
            th.start(); time.sleep(45.1); s = Stats(svc); th.join(); r = box
            st = s.stop(); integ = integrity(); stop(svc)
            res['services'].append({'id': svc, 'label': label, 'soak': r, 'stats': st, 'integrity': integ})
            mems = [m for _, m, _ in st['series']]
            print(f"   {label}: soak p50 {r.get('ok_p50_ms', r['p50_ms']):.1f} p99 {r.get('ok_p99_ms', r['p99_ms']):.1f} p99.9 {r.get('ok_p999_ms', r['p999_ms']):.1f} ms, "
                  f"cpu {st.get('throttle', {}).get('cpu_pct')}%, throttled {st.get('throttle', {}).get('throttled_pct')}%, host steal {st.get('host', {}).get('steal_pct')}%, mem start {mems[min(5, len(mems)-1)]} -> end {mems[-1]} MB (peak {st['mem_peak_mb']}), "
                  f"codes {r['codes']}, consistent {integ['consistent']}", flush=True)
            time.sleep(10)
        out = HERE / f'r4{a.tag}_soak.json'
    out.write_text(json.dumps(res)); print('wrote', out)

if __name__ == '__main__':
    main()
