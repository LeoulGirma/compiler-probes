// Compiler probes — C#. Same semantics as rust/probes.rs and go/main.go.
// Build: Release (optimize+). Runs on the default runtime settings (tiered compilation + dynamic PGO on).
using System;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Collections.Generic;
using System.Linq;

public interface IShape { long Area(); }
public sealed class Square : IShape { public long Side; public Square(long s) { Side = s; } public long Area() => Side * Side; }
public sealed class Point { public long X, Y; public Point(long x, long y) { X = x; Y = y; } }

public static class Probes
{
    const int N = 4096;

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int ProbeVecSum(int[] a) { int s = 0; foreach (int x in a) s += x; return s; }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int ProbeBoundsOne(int[] a) { int s = 0; for (int i = 0; i < a.Length; i++) s += a[i]; return s; }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static int ProbeBoundsTwo(int[] a, int[] b) { int s = 0; for (int i = 0; i < a.Length; i++) s += a[i] * b[i]; return s; }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static long ProbeDyn(IShape[] xs) { long s = 0; foreach (var x in xs) s += x.Area(); return s; }

    [MethodImpl(MethodImplOptions.NoInlining)]
    public static long ProbeAlloc(int[] a) { long s = 0; foreach (int v in a) { var p = new Point(v, (long)v * 2); s += p.X + p.Y; } return s; }

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
        string mode = args.Length > 0 ? args[0] : "bench";
        var a = new int[N]; var b = new int[N];
        for (int i = 0; i < N; i++) { a[i] = (i * 7) % 1000; b[i] = (i * 13) % 1000; }
        if (mode == "warmup")
        {
            var outv = new long[20000];
            for (int i = 0; i < outv.Length; i++) { long t = Stopwatch.GetTimestamp(); sink += ProbeVecSum(a); outv[i] = (long)((Stopwatch.GetTimestamp() - t) * 1e9 / Stopwatch.Frequency); }
            Console.WriteLine("{\"calls_ns\":[" + string.Join(",", outv) + "]}");
            return;
        }
        var shapes = new IShape[N]; for (int i = 0; i < N; i++) shapes[i] = new Square(i % 100);
        // let tiering + PGO settle before measuring steady state
        for (int w = 0; w < 3000; w++) { sink += ProbeVecSum(a) + ProbeBoundsOne(a) + ProbeBoundsTwo(a, b) + ProbeDyn(shapes) + ProbeAlloc(a); }
        System.Threading.Thread.Sleep(300);
        for (int w = 0; w < 3000; w++) { sink += ProbeVecSum(a) + ProbeBoundsOne(a) + ProbeBoundsTwo(a, b) + ProbeDyn(shapes) + ProbeAlloc(a); }
        double rVec = Bench(() => ProbeVecSum(a), 2000), rB1 = Bench(() => ProbeBoundsOne(a), 2000), rB2 = Bench(() => ProbeBoundsTwo(a, b), 1000);
        double rDyn = Bench(() => ProbeDyn(shapes), 500);
        long b0 = GC.GetAllocatedBytesForCurrentThread(); sink += ProbeAlloc(a); long b1 = GC.GetAllocatedBytesForCurrentThread();
        double bytes = (double)(b1 - b0) / N;
        double rAlloc = Bench(() => ProbeAlloc(a), 300);
        long chk = ProbeVecSum(a) + ProbeDyn(shapes) + ProbeAlloc(a);
        var inv = System.Globalization.CultureInfo.InvariantCulture;
        Console.WriteLine(string.Format(inv, "{{\"n\":{0},\"vec_sum\":{1:F1},\"bounds_one\":{2:F1},\"bounds_two\":{3:F1},\"dyn\":{4:F1},\"alloc\":{5:F1},\"alloc_bytes_per_elem\":{6:F1},\"alloc_per_elem\":{7:F3},\"check\":{8},\"runtime\":\"{9}\"}}",
            N, rVec, rB1, rB2, rDyn, rAlloc, bytes, bytes / 32.0, chk, System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription));
    }
}
