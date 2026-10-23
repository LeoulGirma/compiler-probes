// .NET 11 feature probes — C#. Same semantics as rust2/probes2.rs and go2/main.go.
// Each probe targets one thing .NET 11 says it changed:
//   async_sync / async_yield  runtime async (opt-in: csc -features:runtime-async=on)
//   gvm                       devirtualising a generic virtual method
//   dim                       devirtualising a default interface method on a generic interface
//   pairs / from_end / guard  new bounds-check-elimination patterns (i + 1 < len, a[^1], !s.IsEmpty && s[0])
//   bigmul_s / bigmul_u       Math.BigMul(long, long, out long) as one MUL instruction (unsigned for reference)
//   startup                   ReadyToRun: precompiled EqualityComparer<T>.Default / Comparer<T>.Default
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Numerics;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;

public abstract class Op { public abstract T Apply<T>(T x) where T : INumber<T>; }
public sealed class AddOne : Op { public override T Apply<T>(T x) => x + T.One; }

public interface IScale<T> where T : INumber<T> { T Scale(T x) => x * (T.One + T.One + T.One); }
public sealed class Tripler : IScale<int> { }

public readonly struct Key : IEquatable<Key>
{
    public readonly int A, B;
    public Key(int a, int b) { A = a; B = b; }
    public bool Equals(Key o) => A == o.A && B == o.B;
    public override bool Equals(object o) => o is Key k && Equals(k);
    public override int GetHashCode() => HashCode.Combine(A, B);
}

public static class P2
{
    const int N = 4096, DEPTH = 10;
    static readonly Op Op1 = new AddOne();
    static readonly IScale<int> Sc = new Tripler();

    // ---- devirtualisation ----
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int ProbeGvm(int[] a) { int s = 0; for (int i = 0; i < a.Length; i++) s += Op1.Apply(a[i]); return s; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int ProbeDim(int[] a) { int s = 0; for (int i = 0; i < a.Length; i++) s += Sc.Scale(a[i]); return s; }

    // ---- bounds checks ----
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int ProbePairs(int[] a) { int s = 0; for (int i = 0; i + 1 < a.Length; i++) s += a[i] * a[i + 1]; return s; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int ProbeFromEnd(int[][] xs) { int s = 0; foreach (var x in xs) if (x.Length > 0) s += x[^1]; return s; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int ProbeGuard(int[][] xs, int v) { int c = 0; foreach (var x in xs) { ReadOnlySpan<int> sp = x; if (!sp.IsEmpty && sp[0] == v) c++; } return c; }

    // ---- 128-bit multiply ----
    const long KS = 0x5DEECE66DL * 977; const ulong KU = 0x9E3779B97F4A7C15UL;
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static long ProbeBigMulS(long[] a) { long acc = 0; for (int i = 0; i < a.Length; i++) { long hi = Math.BigMul(a[i], KS, out long lo); acc += hi ^ lo; } return acc; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static ulong ProbeBigMulU(ulong[] a) { ulong acc = 0; for (int i = 0; i < a.Length; i++) { ulong hi = Math.BigMul(a[i], KU, out ulong lo); acc += hi ^ lo; } return acc; }

    // ---- async: a chain of DEPTH awaits; the leaf completes synchronously, or suspends once (Task.Yield) ----
    [MethodImpl(MethodImplOptions.NoInlining)]
    static async Task<int> Chain(int depth, int x) { if (depth == 0) return x + 1; return await Chain(depth - 1, x) + 1; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static async Task<int> ChainY(int depth, int x) { if (depth == 0) { await Task.Yield(); return x + 1; } return await ChainY(depth - 1, x) + 1; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static async Task<long> ProbeAsync(int n) { long s = 0; for (int i = 0; i < n; i++) s += await Chain(DEPTH, i); return s; }
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static async Task<long> ProbeAsyncYield(int n) { long s = 0; for (int i = 0; i < n; i++) s += await ChainY(DEPTH, i); return s; }
    static bool RuntimeAsync() => typeof(P2).GetMethod("Chain", BindingFlags.NonPublic | BindingFlags.Static).GetCustomAttribute<AsyncStateMachineAttribute>() == null;

    // ---- startup work: first use of default comparers on our own key type and on built-ins ----
    static string Startup(long t0)
    {
        double us() => (Stopwatch.GetTimestamp() - t0) * 1e6 / Stopwatch.Frequency;
        var inv = System.Globalization.CultureInfo.InvariantCulture;
        double tMain = us();
        var d = new Dictionary<Key, int>(); for (int i = 0; i < 20000; i++) d[new Key(i, i * 3)] = i;
        long s = 0; for (int i = 0; i < 20000; i++) s += d[new Key(i, i * 3)];
        double tDict = us();
        var hs = new HashSet<long>(); for (long i = 0; i < 20000; i++) hs.Add(i * 7919); s += hs.Count;
        var ds = new Dictionary<string, int>(); for (int i = 0; i < 2000; i++) ds["k" + i] = i; s += ds["k1999"];
        double tSet = us();
        var l = new List<long>(20000); for (int i = 0; i < 20000; i++) l.Add((i * 7919L) % 20011); l.Sort(); s += l[100];
        var keys = new List<Key>(); for (int i = 0; i < 2000; i++) keys.Add(new Key(i % 97, i)); s += keys.IndexOf(new Key(5, 1999)) + (keys.Contains(new Key(1, 1)) ? 1 : 0);
        double tSort = us();
        return string.Format(inv, "{{\"main_us\":{0:F0},\"dict_us\":{1:F0},\"set_us\":{2:F0},\"sort_us\":{3:F0},\"total_us\":{4:F0},\"check\":{5}}}",
            tMain, tDict - tMain, tSet - tDict, tSort - tSet, tSort, s);
    }

    static long sink;
    static double Bench(Func<long> f, int reps)
    {
        for (int i = 0; i < reps; i++) sink += f();
        var v = new List<double>();
        for (int k = 0; k < 15; k++)
        {
            long t = Stopwatch.GetTimestamp();
            for (int i = 0; i < reps; i++) sink += f();
            v.Add((Stopwatch.GetTimestamp() - t) * 1e9 / Stopwatch.Frequency / reps);
        }
        v.Sort(); return v[v.Count / 2];
    }

    public static void Main(string[] args)
    {
        long t0 = Process.GetCurrentProcess().StartTime.ToUniversalTime().Ticks;   // for main_us: time from process start
        long now = DateTime.UtcNow.Ticks, ts = Stopwatch.GetTimestamp();
        long startTs = ts - (long)((now - t0) / 1e7 * Stopwatch.Frequency);
        string mode = args.Length > 0 ? args[0] : "bench";
        if (mode == "startup") { Console.WriteLine(Startup(startTs)); return; }

        var a = new int[N]; var la = new long[N]; var ua = new ulong[N];
        for (int i = 0; i < N; i++) { a[i] = (i * 7) % 1000; la[i] = (long)i * 0x1F3D5B79 - 7_000_000_000; ua[i] = (ulong)i * 0x9E3779B1UL + 12345; }
        var xs = new int[1024][]; for (int i = 0; i < xs.Length; i++) { xs[i] = new int[i % 5]; for (int j = 0; j < xs[i].Length; j++) xs[i][j] = (i + j) % 7; }

        void Warm() { for (int w = 0; w < 3000; w++) { sink += ProbeGvm(a) + ProbeDim(a) + ProbePairs(a) + ProbeFromEnd(xs) + ProbeGuard(xs, 3) + ProbeBigMulS(la) + (long)ProbeBigMulU(ua); sink += ProbeAsync(20).GetAwaiter().GetResult(); } }
        Warm(); System.Threading.Thread.Sleep(300); Warm();
        for (int w = 0; w < 200; w++) sink += ProbeAsyncYield(20).GetAwaiter().GetResult();

        double rGvm = Bench(() => ProbeGvm(a), 1000), rDim = Bench(() => ProbeDim(a), 1000);
        double rPairs = Bench(() => ProbePairs(a), 2000), rEnd = Bench(() => ProbeFromEnd(xs), 4000), rGuard = Bench(() => ProbeGuard(xs, 3), 4000);
        double rBs = Bench(() => ProbeBigMulS(la), 2000), rBu = Bench(() => (long)ProbeBigMulU(ua), 2000);
        const int AN = 1000;
        double rAsync = Bench(() => ProbeAsync(AN).GetAwaiter().GetResult(), 20) / (AN * (DEPTH + 1));
        long b0 = GC.GetAllocatedBytesForCurrentThread(); sink += ProbeAsync(AN).GetAwaiter().GetResult(); long b1 = GC.GetAllocatedBytesForCurrentThread();
        double asyncBytes = (double)(b1 - b0) / (AN * (DEPTH + 1));
        const int YN = 200;
        double rYield = Bench(() => ProbeAsyncYield(YN).GetAwaiter().GetResult(), 5) / YN;
        long y0 = GC.GetTotalAllocatedBytes(true); sink += ProbeAsyncYield(YN).GetAwaiter().GetResult(); long y1 = GC.GetTotalAllocatedBytes(true);
        double yieldBytes = (double)(y1 - y0) / YN;

        long chk = ProbeGvm(a) + ProbeDim(a) + ProbePairs(a) + ProbeFromEnd(xs) + ProbeGuard(xs, 3) + ProbeBigMulS(la) + (long)ProbeBigMulU(ua) + ProbeAsync(10).GetAwaiter().GetResult();
        var inv = System.Globalization.CultureInfo.InvariantCulture;
        Console.WriteLine(string.Format(inv,
            "{{\"gvm\":{0:F1},\"dim\":{1:F1},\"pairs\":{2:F1},\"from_end\":{3:F1},\"guard\":{4:F1},\"bigmul_s\":{5:F1},\"bigmul_u\":{6:F1}," +
            "\"async_ns_per_await\":{7:F2},\"async_bytes_per_await\":{8:F1},\"yield_ns_per_op\":{9:F0},\"yield_bytes_per_op\":{10:F0},\"runtime_async\":{11},\"check\":{12},\"runtime\":\"{13}\"}}",
            rGvm, rDim, rPairs, rEnd, rGuard, rBs, rBu, rAsync, asyncBytes, rYield, yieldBytes, RuntimeAsync() ? "true" : "false", chk,
            System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription));
    }
}
