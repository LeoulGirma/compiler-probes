// Which loop shapes does .NET 11's one-operand mul/imul for Math.BigMul slow down?
// Hypothesis: only loops where a value stays live across the multiply in rax/rdx (a loop-carried accumulator) regress,
// because the new instruction must use those two registers and the JIT spills the live value to the stack.
// Each probe reports ns per element (median of timed runs) after warm-up.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;

static class Shapes
{
    const int N = 4096;
    const long KS = 0x5DEECE66DL * 977;
    const ulong KU = 0x9E3779B97F4A7C15UL;
    static long sink;

    // 1. the set 2 probe: one accumulator carried across iterations
    [MethodImpl(MethodImplOptions.NoInlining)]
    static long AccS(long[] a) { long acc = 0; for (int i = 0; i < a.Length; i++) { long hi = Math.BigMul(a[i], KS, out long lo); acc += hi ^ lo; } return acc; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static ulong AccU(ulong[] a) { ulong acc = 0; for (int i = 0; i < a.Length; i++) { ulong hi = Math.BigMul(a[i], KU, out ulong lo); acc += hi ^ lo; } return acc; }

    // 2. no loop-carried value: each result is stored
    [MethodImpl(MethodImplOptions.NoInlining)]
    static long StoreS(long[] a, long[] o) { for (int i = 0; i < a.Length; i++) { long hi = Math.BigMul(a[i], KS, out long lo); o[i] = hi ^ lo; } return o[7]; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static long StoreU(ulong[] a, ulong[] o) { for (int i = 0; i < a.Length; i++) { ulong hi = Math.BigMul(a[i], KU, out ulong lo); o[i] = hi ^ lo; } return (long)o[7]; }

    // 3. two accumulators, one per half
    [MethodImpl(MethodImplOptions.NoInlining)]
    static long TwoAccS(long[] a) { long h = 0, l = 0; for (int i = 0; i < a.Length; i++) { h += Math.BigMul(a[i], KS, out long lo); l ^= lo; } return h ^ l; }

    // 4. the multiply in its own non-inlined method: nothing of the caller is live inside it
    [MethodImpl(MethodImplOptions.NoInlining)]
    static long MulMix(long x) { long hi = Math.BigMul(x, KS, out long lo); return hi ^ lo; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static long CallS(long[] a) { long acc = 0; for (int i = 0; i < a.Length; i++) acc += MulMix(a[i]); return acc; }

    // 5. more values live across the multiply (register pressure): four accumulators
    [MethodImpl(MethodImplOptions.NoInlining)]
    static long PressureS(long[] a)
    {
        long s0 = 0, s1 = 0, s2 = 0, s3 = 0;
        for (int i = 0; i < a.Length; i++) { long hi = Math.BigMul(a[i], KS, out long lo); s0 += hi; s1 ^= lo; s2 += hi ^ lo; s3 += i; }
        return s0 ^ s1 ^ s2 ^ s3;
    }

    // 6. only the high half used (the shape of a fixed-point scale or Lemire bounded random)
    [MethodImpl(MethodImplOptions.NoInlining)]
    static ulong HighOnlyU(ulong[] a) { ulong acc = 0; for (int i = 0; i < a.Length; i++) acc += Math.BigMul(a[i], KU, out _); return acc; }

    static double Bench(Func<long> f, int reps)
    {
        var v = new List<double>();
        for (int k = 0; k < 15; k++)
        {
            long t = Stopwatch.GetTimestamp();
            for (int r = 0; r < reps; r++) sink += f();
            v.Add((Stopwatch.GetTimestamp() - t) * 1e9 / Stopwatch.Frequency / ((double)reps * N));
        }
        v.Sort(); return v[v.Count / 2];
    }

    public static void Main()
    {
        var la = new long[N]; var ua = new ulong[N]; var lo = new long[N]; var uo = new ulong[N];
        for (int i = 0; i < N; i++) { la[i] = (long)i * 0x1F3D5B79 - 7_000_000_000; ua[i] = (ulong)i * 0x9E3779B1UL + 12345; }
        var probes = new (string, Func<long>)[]
        {
            ("acc_signed", () => AccS(la)), ("acc_unsigned", () => (long)AccU(ua)),
            ("store_signed", () => StoreS(la, lo)), ("store_unsigned", () => StoreU(ua, uo)),
            ("two_acc_signed", () => TwoAccS(la)), ("call_signed", () => CallS(la)),
            ("pressure_signed", () => PressureS(la)), ("high_only_unsigned", () => (long)HighOnlyU(ua)),
        };
        // warm-up by time, not by call count: .NET 11 can take longer to replace OSR code with the final Tier1 code
        int warmMs = int.TryParse(Environment.GetEnvironmentVariable("WARM_MS"), out var w) ? w : 0;
        for (int pass = 0; pass < 2; pass++) { foreach (var (_, f) in probes) { var t0 = Stopwatch.GetTimestamp(); int r = 0; while (r < 3000 || Stopwatch.GetElapsedTime(t0).TotalMilliseconds < warmMs) { sink += f(); r++; } } System.Threading.Thread.Sleep(300); }
        var parts = new List<string>();
        foreach (var (name, f) in probes) parts.Add(FormattableString.Invariant($"\"{name}\":{Bench(f, 400):F4}"));
        parts.Add($"\"runtime\":\"{System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription}\"");
        parts.Add($"\"sink\":{sink & 0xFFFF}");
        Console.WriteLine("{" + string.Join(",", parts) + "}");
    }
}
