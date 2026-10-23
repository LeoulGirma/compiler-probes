// Payment-style HTTP service — C# (ASP.NET Core minimal API, source-generated JSON so it also builds for NativeAOT).
// Same contract as go/main.go and rust/src/main.rs:
//   POST /pay   parse JSON -> validate -> HMAC-SHA256 signature -> record in a sharded in-memory ledger -> JSON reply (200, or 422 when invalid)
//   GET /health "ok"
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Serialization;

var builder = WebApplication.CreateSlimBuilder(args);
builder.Logging.ClearProviders();
builder.Services.ConfigureHttpJsonOptions(o => o.SerializerOptions.TypeInfoResolverChain.Insert(0, AppJson.Default));
builder.WebHost.UseUrls("http://127.0.0.1:" + (Environment.GetEnvironmentVariable("PORT") ?? "8080"));
var app = builder.Build();
app.MapGet("/health", () => "ok");
app.MapPost("/pay", async (PayRequest r) => await Pay.HandleAsync(r));
app.Run();

public sealed class Payer { public string Msisdn { get; set; } = ""; public string Name { get; set; } = ""; }
public sealed class Item { public string Sku { get; set; } = ""; public int Qty { get; set; } public long Price { get; set; } }
public sealed class PayRequest
{
    public string Id { get; set; } = ""; public string Merchant { get; set; } = ""; public long Amount { get; set; }
    public string Currency { get; set; } = ""; public Payer Payer { get; set; } = new(); public List<Item> Items { get; set; } = new();
    public string Note { get; set; } = "";
}
public sealed class PayResponse { public string Id { get; set; } = ""; public string Status { get; set; } = ""; public string Signature { get; set; } = ""; public long MerchantCount { get; set; } public long MerchantTotal { get; set; } }
public sealed class PayRejected { public string Id { get; set; } = ""; public string Status { get; set; } = ""; public string Reason { get; set; } = ""; }

[JsonSerializable(typeof(PayRequest))]
[JsonSerializable(typeof(PayResponse))]
[JsonSerializable(typeof(PayRejected))]
[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
internal partial class AppJson : JsonSerializerContext { }

static class Ledger
{
    sealed class Shard { public readonly object Lock = new(); public readonly Dictionary<string, (long Count, long Total)> Map = new(); }
    static readonly Shard[] Shards = Enumerable.Range(0, 64).Select(_ => new Shard()).ToArray();
    // completes synchronously, like a cache hit in front of a database; the call is still awaited, as real handlers are
    public static ValueTask<(long Count, long Total)> RecordAsync(string merchant, long amount)
    {
        var s = Shards[(uint)StringHash(merchant) % 64];
        lock (s.Lock)
        {
            s.Map.TryGetValue(merchant, out var v);
            v = (v.Count + 1, v.Total + amount);
            s.Map[merchant] = v;
            return new ValueTask<(long, long)>(v);
        }
    }
    static int StringHash(string s) { uint h = 2166136261; foreach (char c in s) h = (h ^ c) * 16777619; return (int)h; }   // FNV-1a, same in all three
}

static class Pay
{
    static readonly byte[] Key = Encoding.UTF8.GetBytes("probes-demo-signing-key-0123456789");
    static string Validate(PayRequest r)
    {
        if (r.Amount <= 0) return "amount";
        if (r.Currency != "ETB" && r.Currency != "USD") return "currency";
        var m = r.Payer.Msisdn;
        if (m.Length != 12 || !m.StartsWith("251", StringComparison.Ordinal)) return "msisdn";
        foreach (char c in m) if (c < '0' || c > '9') return "msisdn";
        if (r.Merchant.Length == 0 || r.Merchant.Length > 16) return "merchant";
        if (r.Items.Count == 0) return "items";
        long sum = 0; foreach (var it in r.Items) { if (it.Qty <= 0 || it.Price < 0) return "item"; sum += it.Qty * it.Price; }
        if (sum != r.Amount) return "sum";
        return null;
    }
    public static async Task<IResult> HandleAsync(PayRequest r)
    {
        var reason = Validate(r);
        if (reason != null)
            return Results.Json(new PayRejected { Id = r.Id, Status = "rejected", Reason = reason }, AppJson.Default.PayRejected, statusCode: 422);
        var sig = Convert.ToHexStringLower(HMACSHA256.HashData(Key, Encoding.UTF8.GetBytes($"{r.Id}|{r.Merchant}|{r.Amount}|{r.Currency}")));
        var (count, total) = await Ledger.RecordAsync(r.Merchant, r.Amount);
        return Results.Json(new PayResponse { Id = r.Id, Status = "accepted", Signature = sig, MerchantCount = count, MerchantTotal = total }, AppJson.Default.PayResponse);
    }
}
