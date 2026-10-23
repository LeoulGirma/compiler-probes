// GC stress — C#. Same workload as gc/go/main.go and gc/rust/main.rs.
// Keeps a large live set of small orders (like an in-memory cache of recent payments), then for DURATION seconds
// runs a loop that allocates short-lived orders and replaces a few long-lived ones. Every iteration is timed, so
// any GC pause shows up as a slow iteration, the way a request handler would feel it.
using System.Diagnostics;
using System.Globalization;

sealed class Order { public string Id; public long Amount; public int[] Tags; public Order(int i, long a) { Id = "ord-" + i.ToString("D9", CultureInfo.InvariantCulture); Amount = a; Tags = new int[] { i & 7, i & 15, i & 31, i & 63 }; } }

static class Program
{
    static void Main(string[] args)
    {
        int live = args.Length > 0 ? int.Parse(args[0]) : 1_000_000;
        double seconds = args.Length > 1 ? double.Parse(args[1], CultureInfo.InvariantCulture) : 10;
        var sw = Stopwatch.StartNew();
        var set = new Order[live];
        for (int i = 0; i < live; i++) set[i] = new Order(i, i * 3L);
        double buildMs = sw.Elapsed.TotalMilliseconds;
        GC.Collect(); GC.WaitForPendingFinalizers();
        long gen0 = GC.CollectionCount(0), gen1 = GC.CollectionCount(1), gen2 = GC.CollectionCount(2);
        var pause0 = GC.GetTotalPauseDuration();
        var rng = new Random(42);
        var lat = new List<long>(1 << 20);
        long sink = 0, next = live;
        long end = Stopwatch.GetTimestamp() + (long)(seconds * Stopwatch.Frequency);
        while (true)
        {
            long t = Stopwatch.GetTimestamp();
            if (t >= end) break;
            for (int k = 0; k < 200; k++) { var o = new Order((int)(next + k), k); sink += o.Amount + o.Id.Length + o.Tags[3]; }   // short-lived
            for (int k = 0; k < 20; k++) set[rng.Next(live)] = new Order((int)next++, k);                                        // long-lived turnover
            lat.Add(Stopwatch.GetTimestamp() - t);
        }
        var pause = GC.GetTotalPauseDuration() - pause0;
        Report(lat, Stopwatch.Frequency, buildMs, sink + set[live / 2].Amount,
            $"\"gc_gen0\":{GC.CollectionCount(0) - gen0},\"gc_gen1\":{GC.CollectionCount(1) - gen1},\"gc_gen2\":{GC.CollectionCount(2) - gen2}," +
            $"\"gc_pause_ms\":{pause.TotalMilliseconds.ToString("F1", CultureInfo.InvariantCulture)},\"server_gc\":{(System.Runtime.GCSettings.IsServerGC ? "true" : "false")}," +
            $"\"heap_mb\":{(GC.GetTotalMemory(false) / 1048576.0).ToString("F0", CultureInfo.InvariantCulture)},\"runtime\":\"{System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription}\"");
    }

    static void Report(List<long> ticks, long freq, double buildMs, long sink, string extra)
    {
        var us = ticks.Select(t => t * 1e6 / freq).ToArray(); Array.Sort(us);
        double P(double p) => us[(int)(p * (us.Length - 1))];
        var inv = CultureInfo.InvariantCulture;
        Console.WriteLine(string.Format(inv, "{{\"iterations\":{0},\"iter_per_s\":{1:F0},\"p50_us\":{2:F1},\"p99_us\":{3:F1},\"p999_us\":{4:F1},\"max_us\":{5:F1},\"over_1ms\":{6},\"over_10ms\":{7},\"build_ms\":{8:F0},\"sink\":{9},{10}}}",
            us.Length, us.Length / (us.Sum() / 1e6), P(.5), P(.99), P(.999), us[^1], us.Count(x => x > 1000), us.Count(x => x > 10000), buildMs, sink % 1000, extra));
    }
}
