// Does .NET 11's Math.BigMul change slow down library code that calls it?
// Each probe reports nanoseconds per operation (median of timed runs) after warm-up. Same source for .NET 10 and 11.
using System;
using System.Buffers.Binary;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO.Hashing;
using System.Numerics;
using System.Runtime.CompilerServices;

static class Impact
{
    const int N = 4096;
    static long sink;

    // control: the set 2 probe
    const long KS = 0x5DEECE66DL * 977;
    [MethodImpl(MethodImplOptions.NoInlining)]
    static long BigMulLoop(long[] a) { long acc = 0; for (int i = 0; i < a.Length; i++) { long hi = Math.BigMul(a[i], KS, out long lo); acc += hi ^ lo; } return acc; }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static decimal DecMul(decimal[] a, decimal[] b) { decimal acc = 0; for (int i = 0; i < a.Length; i++) acc += a[i] * b[i]; return acc; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static decimal DecDiv(decimal[] a, decimal[] b) { decimal acc = 0; for (int i = 0; i < a.Length; i++) acc += a[i] / b[i]; return acc; }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static UInt128 U128Mul(UInt128[] a) { UInt128 acc = 1, k = new UInt128(0x9E3779B97F4A7C15, 0xBF58476D1CE4E5B9); for (int i = 0; i < a.Length; i++) acc += a[i] * k; return acc; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static Int128 I128Mul(Int128[] a) { Int128 acc = 1, k = new Int128(0x1234_5678, 0x9E3779B97F4A7C15); for (int i = 0; i < a.Length; i++) acc += a[i] * k; return acc; }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static long RandBounded(Random r) { long acc = 0; for (int i = 0; i < N; i++) acc += r.NextInt64(1_000_000_007L); return acc; }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static BigInteger BigIntMul(BigInteger x, BigInteger y) { BigInteger acc = 0; for (int i = 0; i < 64; i++) acc += x * y; return acc; }

    static double Bench(Func<long> f, int reps, int perCall)
    {
        var v = new List<double>();
        for (int k = 0; k < 15; k++)
        {
            long t = Stopwatch.GetTimestamp();
            for (int r = 0; r < reps; r++) sink += f();
            double ns = (Stopwatch.GetTimestamp() - t) * 1e9 / Stopwatch.Frequency;
            v.Add(ns / ((double)reps * perCall));
        }
        v.Sort(); return v[v.Count / 2];
    }

    public static void Main()
    {
        var rnd = new Random(12345);   // seeded: data only
        var la = new long[N]; var da = new decimal[N]; var db = new decimal[N]; var ua = new UInt128[N]; var ia = new Int128[N];
        for (int i = 0; i < N; i++)
        {
            la[i] = (long)i * 0x1F3D5B79 - 7_000_000_000;
            da[i] = Math.Round((decimal)rnd.NextDouble() * 10_000m, 4); db[i] = Math.Round((decimal)rnd.NextDouble() * 2m + 0.0315m, 4);
            ua[i] = new UInt128((ulong)rnd.NextInt64(), (ulong)rnd.NextInt64()); ia[i] = new Int128((ulong)rnd.NextInt64(), (ulong)rnd.NextInt64());
        }
        var buf = new byte[1 << 20]; rnd.NextBytes(buf);
        var xoshiro = new Random();    // unseeded: the Xoshiro256** implementation, whose NextInt64(max) uses Math.BigMul
        var bx = BigInteger.Parse("1" + new string('7', 300)); var by = BigInteger.Parse("9" + new string('3', 300));

        var probes = new (string name, Func<long> f, int reps, int per)[]
        {
            ("bigmul_loop", () => BigMulLoop(la), 400, N),
            ("decimal_mul", () => (long)DecMul(da, db), 100, N),
            ("decimal_div", () => (long)DecDiv(da, db), 20, N),
            ("uint128_mul", () => (long)(ulong)U128Mul(ua), 300, N),
            ("int128_mul", () => (long)I128Mul(ia), 300, N),
            ("xxhash3_per_kb", () => (long)XxHash3.HashToUInt64(buf), 20, buf.Length / 1024),
            ("xxhash128_per_kb", () => (long)XxHash128.HashToUInt128(buf).GetHashCode(), 20, buf.Length / 1024),
            ("random_nextint64", () => RandBounded(xoshiro), 100, N),
            ("bigint_mul_1000bit", () => (long)(BigIntMul(bx, by) & long.MaxValue), 200, 64),
        };
        // warm-up: enough calls for tiered compilation and PGO to settle, twice with a pause between
        // warm-up by time, not by call count: .NET 11 can take longer to replace OSR code with the final Tier1 code
        int warmMs = int.TryParse(Environment.GetEnvironmentVariable("WARM_MS"), out var w) ? w : 0;
        for (int pass = 0; pass < 2; pass++) { foreach (var p in probes) { var t0 = Stopwatch.GetTimestamp(); int r = 0; while (r < 300 || Stopwatch.GetElapsedTime(t0).TotalMilliseconds < warmMs) { sink += p.f(); r++; } } System.Threading.Thread.Sleep(300); }

        var parts = new List<string>();
        foreach (var p in probes) parts.Add(FormattableString.Invariant($"\"{p.name}\":{Bench(p.f, p.reps, p.per):F4}"));
        parts.Add($"\"runtime\":\"{System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription}\"");
        parts.Add($"\"aot\":{(!RuntimeFeature.IsDynamicCodeSupported ? "true" : "false")}");
        parts.Add($"\"sink\":{sink & 0xFFFF}");
        Console.WriteLine("{" + string.Join(",", parts) + "}");
    }
}
