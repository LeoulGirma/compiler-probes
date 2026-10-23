// Production-shaped payment service — C# (ASP.NET Core minimal API, JwtBearer, Npgsql, StackExchange.Redis, HttpClient,
// JSON console logging). Same contract as go/main.go and rust/src/main.rs.
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Serialization;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.IdentityModel.Tokens;
using Npgsql;
using StackExchange.Redis;

static string Env(string k, string d) => Environment.GetEnvironmentVariable(k) is { Length: > 0 } v ? v : d;

var b = WebApplication.CreateSlimBuilder(args);
b.Logging.ClearProviders();
b.Logging.AddJsonConsole();
b.Logging.AddFilter("Microsoft", LogLevel.Warning);
b.Services.ConfigureHttpJsonOptions(o => o.SerializerOptions.TypeInfoResolverChain.Insert(0, AppJson.Default));
b.WebHost.UseUrls("http://0.0.0.0:" + Env("PORT", "8080"));
b.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme).AddJwtBearer(o =>
{
    o.MapInboundClaims = false;
    o.TokenValidationParameters = new TokenValidationParameters
    {
        ValidIssuer = "probes-test", ValidAudience = "payments", ValidAlgorithms = new[] { SecurityAlgorithms.HmacSha256 },
        IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(Env("JWT_SECRET", "probes-test-jwt-secret-0123456789abcdef"))),
        ClockSkew = TimeSpan.FromSeconds(30),
    };
});
b.Services.AddAuthorization();

var ds = new NpgsqlDataSourceBuilder($"Host={Env("DB_HOST", "localhost")};Username={Env("DB_USER", "pay")};Password={Env("DB_PASS", "pay")};" +
    $"Database={Env("DB_NAME", "pay")};Maximum Pool Size={Env("DB_POOL", "32")}").Build();
var redis = await ConnectionMultiplexer.ConnectAsync(Env("REDIS_HOST", "localhost") + ":6379");
var http = new HttpClient(new SocketsHttpHandler { PooledConnectionLifetime = TimeSpan.FromMinutes(5) })
    { Timeout = TimeSpan.FromMilliseconds(int.Parse(Env("PROVIDER_TIMEOUT_MS", "1000"))) };
var svc = new PayService(ds, redis.GetDatabase(), http, Env("PROVIDER_URL", "http://localhost:9000/charge"), long.Parse(Env("RATE_LIMIT", "100000")));

var app = b.Build();
app.UseAuthentication();
app.UseAuthorization();
app.MapGet("/health", () => "ok");
app.MapPost("/pay", (PayRequest r, HttpContext ctx, ILogger<PayService> log) => svc.PayAsync(r, ctx.User.FindFirst("sub")?.Value, log)).RequireAuthorization();
app.Run();

public sealed class Payer { public string Msisdn { get; set; } = ""; public string Name { get; set; } = ""; }
public sealed class Item { public string Sku { get; set; } = ""; public int Qty { get; set; } public long Price { get; set; } }
public sealed class PayRequest
{
    public string Id { get; set; } = ""; public string Merchant { get; set; } = ""; public long Amount { get; set; }
    public string Currency { get; set; } = ""; public Payer Payer { get; set; } = new(); public List<Item> Items { get; set; } = new();
    public string Note { get; set; } = "";
}
public sealed class PayResponse { public string Id { get; set; } = ""; public string Status { get; set; } = ""; public string ProviderRef { get; set; } = ""; public string Signature { get; set; } = ""; public long MerchantCount { get; set; } public long MerchantTotal { get; set; } }
public sealed class Rejected { public string Id { get; set; } = ""; public string Status { get; set; } = "rejected"; public string Reason { get; set; } = ""; }
public sealed class Duplicate { public string Id { get; set; } = ""; public string Status { get; set; } = "duplicate"; public string Original { get; set; } = ""; public string ProviderRef { get; set; } = ""; }
public sealed class ProviderRequest { public string Id { get; set; } = ""; public long Amount { get; set; } public string Currency { get; set; } = ""; }
public sealed class ProviderReply { [JsonPropertyName("ref")] public string Ref { get; set; } = ""; }

[JsonSerializable(typeof(PayRequest))]
[JsonSerializable(typeof(PayResponse))]
[JsonSerializable(typeof(Rejected))]
[JsonSerializable(typeof(Duplicate))]
[JsonSerializable(typeof(ProviderRequest))]
[JsonSerializable(typeof(ProviderReply))]
[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
internal partial class AppJson : JsonSerializerContext { }

public sealed class PayService(NpgsqlDataSource db, IDatabase redis, HttpClient http, string provider, long rateLimit)
{
    static readonly byte[] SignKey = Encoding.UTF8.GetBytes("probes-demo-signing-key-0123456789");

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
        return sum != r.Amount ? "sum" : null;
    }
    static IResult Reject(int code, string id, string reason) => Results.Json(new Rejected { Id = id, Reason = reason }, AppJson.Default.Rejected, statusCode: code);
    static NpgsqlCommand Cmd(NpgsqlConnection c, string sql, params object[] args)
    {
        var cmd = new NpgsqlCommand(sql, c);
        foreach (var a in args) cmd.Parameters.Add(new NpgsqlParameter { Value = a });
        return cmd;
    }

    public async Task<IResult> PayAsync(PayRequest r, string sub, ILogger log)
    {
        long t0 = Environment.TickCount64;
        // 1. authenticated by JwtBearer; the token's subject must be the paying merchant
        if (sub != r.Merchant) return Reject(403, r.Id, "merchant");
        // 2. rate limit: one counter per merchant per second
        var key = $"rl:{r.Merchant}:{DateTimeOffset.UtcNow.ToUnixTimeSeconds()}";
        long n;
        try
        {
            var batch = redis.CreateBatch();
            var incr = batch.StringIncrementAsync(key);
            var exp = batch.KeyExpireAsync(key, TimeSpan.FromSeconds(5));
            batch.Execute();
            n = await incr; await exp;
        }
        catch (RedisException) { return Reject(503, r.Id, "redis"); }
        if (n > rateLimit) return Reject(429, r.Id, "rate");
        // 3. validate
        if (Validate(r) is string reason) return Reject(422, r.Id, reason);
        try
        {
            // 4. record as pending; a repeated id is an idempotent replay
            await using (var c = await db.OpenConnectionAsync())
            {
                await using var ins = Cmd(c, "INSERT INTO payments (id, merchant, amount, currency, status) VALUES ($1, $2, $3, $4, 'pending') ON CONFLICT (id) DO NOTHING",
                    r.Id, r.Merchant, r.Amount, r.Currency);
                if (await ins.ExecuteNonQueryAsync() == 0)
                {
                    await using var sel = Cmd(c, "SELECT status, coalesce(provider_ref, '') FROM payments WHERE id = $1", r.Id);
                    await using var rd = await sel.ExecuteReaderAsync();
                    var d = new Duplicate { Id = r.Id };
                    if (await rd.ReadAsync()) { d.Original = rd.GetString(0); d.ProviderRef = rd.GetString(1); }
                    return Results.Json(d, AppJson.Default.Duplicate);
                }
            } // connection goes back to the pool before the provider call
            // 5. charge with the provider
            string pref = null;
            try
            {
                using var resp = await http.PostAsJsonAsync(provider, new ProviderRequest { Id = r.Id, Amount = r.Amount, Currency = r.Currency }, AppJson.Default.ProviderRequest);
                if (resp.IsSuccessStatusCode) pref = (await resp.Content.ReadFromJsonAsync(AppJson.Default.ProviderReply))?.Ref;
            }
            catch (Exception e) when (e is HttpRequestException or TaskCanceledException) { }
            await using var conn = await db.OpenConnectionAsync();
            if (pref == null)
            {
                await using var fail = Cmd(conn, "UPDATE payments SET status = 'failed', updated_at = now() WHERE id = $1", r.Id);
                await fail.ExecuteNonQueryAsync();
                log.LogWarning("provider failed {Id} {Merchant}", r.Id, r.Merchant);
                return Reject(502, r.Id, "provider");
            }
            // 6. capture + balance in one transaction
            await using var tx = await conn.BeginTransactionAsync();
            await using (var up = Cmd(conn, "UPDATE payments SET status = 'captured', provider_ref = $2, updated_at = now() WHERE id = $1", r.Id, pref))
                await up.ExecuteNonQueryAsync();
            long total, count;
            await using (var bal = Cmd(conn, "INSERT INTO balances (merchant, total, count) VALUES ($1, $2, 1) ON CONFLICT (merchant) DO UPDATE SET total = balances.total + EXCLUDED.total, count = balances.count + 1 RETURNING total, count", r.Merchant, r.Amount))
            await using (var rd = await bal.ExecuteReaderAsync())
            {
                await rd.ReadAsync(); total = rd.GetInt64(0); count = rd.GetInt64(1);
            }
            await tx.CommitAsync();
            var sig = Convert.ToHexStringLower(HMACSHA256.HashData(SignKey, Encoding.UTF8.GetBytes($"{r.Id}|{r.Merchant}|{r.Amount}|{r.Currency}")));
            log.LogInformation("captured {Id} {Merchant} {Amount} {Ms}", r.Id, r.Merchant, r.Amount, Environment.TickCount64 - t0);
            return Results.Json(new PayResponse { Id = r.Id, Status = "captured", ProviderRef = pref, Signature = sig, MerchantCount = count, MerchantTotal = total }, AppJson.Default.PayResponse);
        }
        catch (NpgsqlException) { return Reject(503, r.Id, "db"); }
    }
}
