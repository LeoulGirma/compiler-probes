#!/usr/bin/env python3
"""Bake data2.json + the write-up into page/compiler-probes-net11.html."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / 'data2.json').read_text())
KEEP = {'gvm', 'dim', 'pairs', 'bigmul_s', 'bigmul_u'}
for r in data['runs']:
    r['asm'] = {k: v for k, v in r.get('asm', {}).items() if k in KEEP and r['id'] == 'cs' and r['mode'] == 'jit' and not r.get('runtime_async')}

def run(test):
    return next(r for r in data['runs'] if test(r))
c10 = run(lambda r: r['id'] == 'cs' and r['mode'] == 'jit' and r['version'].startswith('.NET 10'))
c11 = run(lambda r: r['id'] == 'cs' and r['mode'] == 'jit' and r['version'].startswith('.NET 11') and not r['runtime_async'])
cra = run(lambda r: r['id'] == 'cs' and r['mode'] == 'jit' and r['runtime_async'])
a10 = run(lambda r: r['id'] == 'cs' and r['mode'] == 'aot' and r['version'].startswith('.NET 10'))
a11 = run(lambda r: r['id'] == 'cs' and r['mode'] == 'aot' and r['version'].startswith('.NET 11'))
r10 = run(lambda r: r['id'] == 'cs' and r['mode'] == 'r2r' and r['version'].startswith('.NET 10'))
r11 = run(lambda r: r['id'] == 'cs' and r['mode'] == 'r2r' and r['version'].startswith('.NET 11'))
rs = run(lambda r: r['id'] == 'rust'); go = run(lambda r: r['id'] == 'go')
B = lambda r, k: r['bench'][k]['med']
S = lambda r, k: r['startup'][k]['med']
x = lambda a, b: f'{a / b:.1f}×'
N = 4096
per = lambda r, k: B(r, k) / N

notes = {
 'lede': (f"Microsoft lists a set of runtime and JIT changes for .NET 11. We wrote a small probe for each one, ran it on .NET 10 and on .NET 11 RC2, "
          f"and put Rust and Go next to them doing the same work. Two changes are large and real, one is real but switched off by default, "
          f"one makes a loop slower, and two did not show up at all."),
 'feats': [
  dict(id='async', name='Runtime async', verdict='yes', vtext='Real · opt-in',
       claim='The runtime, not the compiler, tracks await points. No state-machine classes, fewer allocations.',
       delta=f"{x(B(c11,'async_ns_per_await'), B(cra,'async_ns_per_await'))} cheaper await",
       code=f"{B(c11,'async_bytes_per_await'):.0f} → 0 bytes per await",
       body=[f"A chain of ten <span class='code-in'>async</span> methods, each awaiting the next. On .NET 10 every level costs {B(c10,'async_ns_per_await'):.1f} ns and allocates "
             f"{B(c10,'async_bytes_per_await'):.0f} bytes. .NET 11 behaves exactly the same until you compile with <span class='code-in'>runtime-async=on</span>; then an await costs "
             f"{B(cra,'async_ns_per_await'):.1f} ns and allocates nothing.",
             f"When the leaf really suspends (<span class='code-in'>await Task.Yield()</span>, one trip through the thread pool), a whole operation drops from "
             f"{B(c10,'yield_ns_per_op'):,.0f} ns on .NET 10 to {B(cra,'yield_ns_per_op'):,.0f} ns, and from {B(c10,'yield_bytes_per_op'):,.0f} to {B(cra,'yield_bytes_per_op'):,.0f} bytes.",
             "It is off by default. Neither a plain compile nor <span class='code-in'>dotnet publish</span> with the RC2 SDK turned it on; the probe checks for the compiler-generated "
             "state machine at run time and reports which mode it got.",
             f"Rust's async functions nest into one inline state machine ({B(rs,'async_ns_per_await'):.1f} ns, no heap). Go needs no async at all: goroutines have growable stacks, "
             f"so the same chain is ordinary calls ({B(go,'async_ns_per_await'):.1f} ns), and a real suspension is a goroutine hand-off ({B(go,'yield_ns_per_op'):,.0f} ns). "
             f"Rust's {B(rs,'yield_ns_per_op'):.0f} ns suspension uses a single-threaded executor with no thread hop, so it is a floor, not a like-for-like number."],
       charts=[dict(key='async_ns_per_await', cols=['cs10', 'cs11', 'csra', 'rust', 'go'], unit='ns / await', title='Cost of one await, chain completes synchronously'),
               dict(key='async_bytes_per_await', cols=['cs10', 'cs11', 'csra', 'rust', 'go'], unit='bytes / await', title='Heap allocated per await'),
               dict(key='yield_ns_per_op', cols=['cs10', 'cs11', 'csra', 'rust', 'go'], unit='ns / operation', title='One suspension and resume through ten levels')]),
  dict(id='gvm', name='Generic virtual methods', verdict='yes', vtext='Real',
       claim='The JIT can now devirtualise calls to generic virtual methods when it knows the exact type.',
       delta=f"{x(B(c10,'gvm'), B(c11,'gvm'))} faster",
       code=f"lookup + indirect call → inlined",
       body=[f"<span class='code-in'>op.Apply&lt;int&gt;(x)</span> on an abstract class, called 4,096 times through a <span class='code-in'>static readonly</span> field. "
             f".NET 10 resolves the target on every call with a runtime lookup helper and then calls through a register: {per(c10,'gvm'):.2f} ns per call. "
             f".NET 11 sees the exact type, devirtualises and inlines it: {per(c11,'gvm'):.2f} ns per call, a {x(B(c10,'gvm'), B(c11,'gvm'))} gain. "
             f"NativeAOT gets it too ({B(a10,'gvm')/N:.2f} → {B(a11,'gvm')/N:.2f} ns).",
             f"Rust has no generic methods in vtables, so the same code is monomorphised and vectorised ({per(rs,'gvm'):.2f} ns). Go has no generic methods either; its nearest "
             f"form, a generic function calling a method on its type parameter, goes through a dictionary and an indirect call ({per(go,'gvm'):.2f} ns)."],
       charts=[dict(key='gvm', cols=['cs10', 'cs11', 'rust', 'go'], per=N, unit='ns / call', title='One generic virtual call, steady state')],
       mc=dict(probe='gvm', cols=['cs10', 'cs11', 'rust', 'go'], metrics=[['calls', 'Calls in loop'], ['indirect_calls', 'Indirect calls'], ['gvm_lookups', 'Runtime lookups'], ['instructions', 'Instructions']]),
       asm=dict(probe='gvm', a='cs10', b='cs11')),
  dict(id='dim', name='Default interface methods', verdict='yes', vtext='Real · JIT only',
       claim='Default interface methods on generic interfaces can be devirtualised.',
       delta=f"{x(B(c10,'dim'), B(c11,'dim'))} faster",
       code='indirect call → inlined',
       body=[f"<span class='code-in'>IScale&lt;int&gt;.Scale</span> has a default body and the class does not override it. .NET 10 calls it through the interface every time "
             f"({per(c10,'dim'):.2f} ns); .NET 11's JIT inlines it ({per(c11,'dim'):.2f} ns).",
             f"NativeAOT did not get this one: {B(a10,'dim')/N:.2f} → {B(a11,'dim')/N:.2f} ns, still a real call. Rust's number goes through a vtable on purpose "
             f"(the probe hides the concrete type), and Go's embedded-struct method is an interface call ({per(go,'dim'):.2f} ns)."],
       charts=[dict(key='dim', cols=['cs10', 'cs11', 'rust', 'go'], per=N, unit='ns / call', title='One default-interface-method call, steady state')],
       mc=dict(probe='dim', cols=['cs10', 'cs11', 'rust', 'go'], metrics=[['calls', 'Calls in loop'], ['indirect_calls', 'Indirect calls'], ['instructions', 'Instructions']]),
       asm=dict(probe='dim', a='cs10', b='cs11')),
  dict(id='bigmul', name='Math.BigMul', verdict='part', vtext='Shorter, slower',
       claim='Math.BigMul(long, long, out long) becomes a single MUL instruction on x64.',
       delta=f"{(B(c11,'bigmul_s')/B(c10,'bigmul_s')-1)*100:.0f}% slower",
       code=f"{c10['features']['bigmul_s']['instructions']} → {c11['features']['bigmul_s']['instructions']} instructions",
       body=[f"The claim holds for the code: .NET 11 emits one <span class='code-in'>imul rdx:rax</span> where .NET 10 used <span class='code-in'>mulx</span> plus a sign fix-up. "
             f"The loop still got slower on this CPU: {per(c10,'bigmul_s'):.2f} → {per(c11,'bigmul_s'):.2f} ns per multiply for the signed form, and "
             f"{per(c10,'bigmul_u'):.2f} → {per(c11,'bigmul_u'):.2f} ns for the unsigned one, which was already a single instruction.",
             "The cause is visible in the listing: .NET 11 keeps the running total in a stack slot and stores and reloads it on every iteration, "
             "so each step waits on a store-to-load round trip. That is a register-allocation regression around the new instruction, not the multiply itself.",
             f"NativeAOT is the opposite story: {B(a10,'bigmul_s')/N:.2f} → {B(a11,'bigmul_s')/N:.2f} ns, about {x(B(a10,'bigmul_s'), B(a11,'bigmul_s'))} faster. "
             f"Rust's <span class='code-in'>i128</span> multiply unrolls the loop ({per(rs,'bigmul_s'):.2f} ns); Go only has the unsigned <span class='code-in'>bits.Mul64</span> ({per(go,'bigmul_u'):.2f} ns)."],
       charts=[dict(key='bigmul_s', cols=['cs10', 'cs11', 'rust'], per=N, unit='ns / multiply', title='Signed 64×64→128 multiply'),
               dict(key='bigmul_u', cols=['cs10', 'cs11', 'rust', 'go'], per=N, unit='ns / multiply', title='Unsigned 64×64→128 multiply')],
       mc=dict(probe='bigmul_s', cols=['cs10', 'cs11', 'rust'], metrics=[['mul_instr', 'Multiply instructions'], ['instructions', 'Instructions']]),
       asm=dict(probe='bigmul_s', a='cs10', b='cs11')),
  dict(id='bounds', name='Bounds-check removal', verdict='no', vtext='Not seen',
       claim='New patterns: i + k < length, values[^1], and a check after !span.IsEmpty.',
       delta=f"{B(c11,'pairs')/B(c10,'pairs'):.2f}× (no change)",
       code=f"{c10['features']['pairs']['bounds_checks']} → {c11['features']['pairs']['bounds_checks']} checks left",
       body=[f"<span class='code-in'>for (i = 0; i + 1 &lt; a.Length; i++) s += a[i] * a[i + 1];</span> keeps both bounds checks on .NET 11, exactly as on .NET 10, "
             f"and runs at the same speed ({per(c10,'pairs'):.2f} vs {per(c11,'pairs'):.2f} ns per element).",
             f"The other two patterns, <span class='code-in'>x[^1]</span> after a length test and <span class='code-in'>!s.IsEmpty &amp;&amp; s[0] == v</span>, already had no checks on .NET 10, so there was nothing left to remove.",
             f"Rust removes both checks and vectorises the loop ({per(rs,'pairs'):.2f} ns). Go keeps both, like .NET ({per(go,'pairs'):.2f} ns)."],
       charts=[dict(key='pairs', cols=['cs10', 'cs11', 'rust', 'go'], per=N, unit='ns / element', title='a[i] * a[i + 1] while i + 1 < length')],
       mc=dict(probe='pairs', cols=['cs10', 'cs11', 'rust', 'go'], metrics=[['bounds_checks', 'Bounds checks'], ['instructions', 'Instructions']]),
       asm=dict(probe='pairs', a='cs10', b='cs11')),
  dict(id='startup', name='ReadyToRun comparers', verdict='no', vtext='Not seen',
       claim='EqualityComparer<T>.Default and Comparer<T>.Default are precompiled in ReadyToRun images, avoiding the JIT.',
       delta=f"{S(r10,'wall_ms'):.0f} → {S(r11,'wall_ms'):.0f} ms",
       code=f"{S(r10,'jitted_comparer_methods'):.0f} → {S(r11,'jitted_comparer_methods'):.0f} comparer methods JIT-compiled",
       body=[], charts=[]),
 ],
 'startup': (f"A cold process fills a <span class='code-in'>Dictionary&lt;Key,int&gt;</span> keyed by our own struct, a <span class='code-in'>HashSet&lt;long&gt;</span> and a string dictionary, sorts a list and searches it. "
             f"In the ReadyToRun build the JIT still compiled {S(r11,'jitted_comparer_methods'):.0f} comparer-related methods on .NET 11 ({S(r10,'jitted_comparer_methods'):.0f} on .NET 10), "
             f"and the dictionary step took the same {S(r11,'dict_us')/1000:.1f} ms. Microsoft's up-to-20× figure may apply to other key types; it did not show up for a user-defined struct. "
             f".NET 11 does JIT fewer methods overall ({S(c10,'jitted_methods'):.0f} → {S(c11,'jitted_methods'):.0f} in the JIT build). NativeAOT starts in {S(a11,'wall_ms'):.0f} ms on both versions, "
             f"against {S(rs,'wall_ms'):.0f} ms for Rust and {S(go,'wall_ms'):.0f} ms for Go."),
 'method': [
   ['Machine', f"{data['machine']['cpu']}, {data['machine']['os']}, on AC power with Turbo Boost on. The CPU clock was logged during every run and stayed between 3.3 and 4.4 GHz. Background apps and services were closed."],
   ['Rounds', "Three rounds, alternating the order of Rust, Go, .NET 10 and .NET 11 so heat and drift hit every column equally. Each number is the median of 15 timed batches, then the median of 3 processes, then the median of the 3 rounds. The thin line on each bar is the range across rounds."],
   ['Builds', "C# JIT columns are compiled with csc -optimize+ and run on the default runtime settings (tiered compilation and dynamic PGO on). The runtime-async column adds -features:runtime-async=on. ReadyToRun and NativeAOT use dotnet publish. Rust uses rustc -C opt-level=3; Go uses a plain go build."],
   ['Machine code', "C# listings come from DOTNET_JitDisasm after tier-up, so they show the code that actually ran. Rust is read from rustc --emit=asm, Go from -gcflags=-S. Counts are taken from those listings by pattern, per function."],
   ['Same work', "The C# and Rust probes return identical checksums. Go's differs only because it has no signed 128-bit multiply, so that probe is left out for Go."],
   ['Also faster', f"Build time, though no probe targets it: NativeAOT publish went from {a10['compile_ms']['med']/1000:.1f} s to {a11['compile_ms']['med']/1000:.1f} s and ReadyToRun from {r10['compile_ms']['med']/1000:.1f} s to {r11['compile_ms']['med']/1000:.1f} s, mostly from .NET 11 turning the MSBuild server on by default."],
 ],
 'foot': 'Probes, driver and raw results: probe2.py, cs2/Probes2.cs, rust2/probes2.rs, go2/main.go. .NET 11 is a release candidate; results can change by GA.',
}
html = (HERE / 'page' / 'template2.html').read_text()
html = html.replace('/*DATA*/null', json.dumps(data, separators=(',', ':'))).replace('/*NOTES*/null', json.dumps(notes, ensure_ascii=False))
(HERE / 'page' / 'compiler-probes-net11.html').write_text(html)
print('ok', len(html))
for f in notes['feats']: print(f['name'], '|', f['delta'], '|', f['code'])
