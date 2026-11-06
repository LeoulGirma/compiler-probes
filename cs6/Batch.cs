// Realistic decimal batch: fees and interest over 1,000,000 transactions, rounded to cents, summed per account.
// Reports milliseconds per pass (median of timed passes) for the full job and for an add-only control.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;

static class Batch
{
    const int Rows = 1_000_000, Accounts = 10_000;
    static readonly decimal FeeRate = 0.0175m, DailyRate = 0.000137m;

    [MethodImpl(MethodImplOptions.NoInlining)]
    static decimal FeesAndInterest(decimal[] amount, int[] account, int[] days, decimal[] totals)
    {
        Array.Clear(totals);
        decimal fees = 0;
        for (int i = 0; i < amount.Length; i++)
        {
            decimal a = amount[i];
            decimal fee = Math.Round(a * FeeRate, 2, MidpointRounding.ToEven);
            decimal interest = Math.Round(a * DailyRate * days[i], 2, MidpointRounding.ToEven);
            totals[account[i]] += a - fee + interest;
            fees += fee;
        }
        return fees;
    }

    // control: the same pass with the multiplications removed (rounding, adds and memory access stay)
    [MethodImpl(MethodImplOptions.NoInlining)]
    static decimal AddOnly(decimal[] amount, int[] account, int[] days, decimal[] totals)
    {
        Array.Clear(totals);
        decimal fees = 0;
        for (int i = 0; i < amount.Length; i++)
        {
            decimal a = amount[i];
            decimal fee = Math.Round(a + FeeRate, 2, MidpointRounding.ToEven);
            decimal interest = Math.Round(a + DailyRate + days[i], 2, MidpointRounding.ToEven);
            totals[account[i]] += a - fee + interest;
            fees += fee;
        }
        return fees;
    }

    static double Ms(Func<decimal> f, int passes)
    {
        var v = new List<double>();
        for (int k = 0; k < passes; k++)
        {
            long t = Stopwatch.GetTimestamp();
            sink += f();
            v.Add((Stopwatch.GetTimestamp() - t) * 1e3 / Stopwatch.Frequency);
        }
        v.Sort(); return v[v.Count / 2];
    }
    static decimal sink;

    public static void Main()
    {
        var rnd = new Random(2026);
        var amount = new decimal[Rows]; var account = new int[Rows]; var days = new int[Rows]; var totals = new decimal[Accounts];
        for (int i = 0; i < Rows; i++)
        {
            amount[i] = Math.Round((decimal)(rnd.NextDouble() * rnd.NextDouble()) * 50_000m + 1m, 2);   // skewed toward small payments
            account[i] = rnd.Next(Accounts); days[i] = 1 + rnd.Next(30);
        }
        Func<decimal> full = () => FeesAndInterest(amount, account, days, totals), ctl = () => AddOnly(amount, account, days, totals);
        for (int w = 0; w < 30; w++) { sink += full(); sink += ctl(); }   // tiered compilation + PGO settle
        System.Threading.Thread.Sleep(300);
        double mFull = Ms(full, 15), mCtl = Ms(ctl, 15);
        string check = FeesAndInterest(amount, account, days, totals).ToString(System.Globalization.CultureInfo.InvariantCulture);
        Console.WriteLine(FormattableString.Invariant(
            $"{{\"fees_interest_ms\":{mFull:F3},\"add_only_ms\":{mCtl:F3},\"runtime\":\"{System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription}\",\"check\":\"{check}\"}}"));
    }
}
