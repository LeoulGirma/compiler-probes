// Production-shaped payment service — Rust (axum, tokio-postgres + deadpool, redis, reqwest, jsonwebtoken, tracing).
// Same contract as cs/Program.cs and go/main.go:
//   POST /pay  Bearer JWT (HS256, iss/aud/exp, sub must equal the merchant) -> Redis per-merchant rate limit ->
//              validate -> INSERT pending (idempotent on id) -> provider call (1 s timeout) ->
//              transaction: mark captured + upsert merchant balance -> JSON reply with HMAC signature.
//   GET /health
use axum::{extract::State, http::{HeaderMap, StatusCode}, response::{IntoResponse, Response}, routing::{get, post}, Json, Router};
use deadpool_postgres::{Manager, ManagerConfig, Pool, RecyclingMethod};
use hmac::{Hmac, Mac};
use jsonwebtoken::{decode, Algorithm, DecodingKey, Validation};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sha2::Sha256;
use std::{sync::Arc, time::{Duration, SystemTime, UNIX_EPOCH}};

#[derive(Deserialize)] struct Payer { msisdn: String, #[allow(dead_code)] name: String }
#[derive(Deserialize)] struct Item { #[allow(dead_code)] sku: String, qty: i32, price: i64 }
#[derive(Deserialize)]
struct PayRequest { id: String, merchant: String, amount: i64, currency: String, payer: Payer, items: Vec<Item>, #[allow(dead_code)] note: String }
#[derive(Deserialize)] struct Claims { sub: String }
#[derive(Deserialize)] struct ProviderReply { #[serde(rename = "ref")] reference: String }
#[derive(Serialize)] #[serde(rename_all = "camelCase")]
struct PayResponse { id: String, status: &'static str, provider_ref: String, signature: String, merchant_count: i64, merchant_total: i64 }

struct App { db: Pool, redis: redis::aio::ConnectionManager, http: reqwest::Client, provider: String, jwt_key: DecodingKey, jwt_val: Validation, rate_limit: i64 }
const SIGN_KEY: &[u8] = b"probes-demo-signing-key-0123456789";

fn validate(r: &PayRequest) -> Option<&'static str> {
    if r.amount <= 0 { return Some("amount"); }
    if r.currency != "ETB" && r.currency != "USD" { return Some("currency"); }
    let m = r.payer.msisdn.as_bytes();
    if m.len() != 12 || &m[..3] != b"251" || !m.iter().all(|c| c.is_ascii_digit()) { return Some("msisdn"); }
    if r.merchant.is_empty() || r.merchant.len() > 16 { return Some("merchant"); }
    if r.items.is_empty() { return Some("items"); }
    let mut sum = 0i64;
    for it in &r.items { if it.qty <= 0 || it.price < 0 { return Some("item"); } sum += it.qty as i64 * it.price; }
    if sum != r.amount { return Some("sum"); }
    None
}
fn hex(b: &[u8]) -> String { b.iter().map(|x| format!("{x:02x}")).collect() }
fn err(code: StatusCode, id: &str, reason: &str) -> Response { (code, Json(json!({"id": id, "status": "rejected", "reason": reason}))).into_response() }

async fn pay(State(app): State<Arc<App>>, headers: HeaderMap, Json(r): Json<PayRequest>) -> Response {
    let t0 = std::time::Instant::now();
    // 1. authenticate
    let token = headers.get("authorization").and_then(|v| v.to_str().ok()).and_then(|v| v.strip_prefix("Bearer ")).unwrap_or("");
    let claims = match decode::<Claims>(token, &app.jwt_key, &app.jwt_val) { Ok(c) => c.claims, Err(_) => return err(StatusCode::UNAUTHORIZED, &r.id, "token") };
    if claims.sub != r.merchant { return err(StatusCode::FORBIDDEN, &r.id, "merchant"); }
    // 2. rate limit: one counter per merchant per second
    let sec = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
    let key = format!("rl:{}:{}", r.merchant, sec);
    let mut rc = app.redis.clone();
    let n: i64 = match redis::pipe().incr(&key, 1).expire(&key, 5).ignore().query_async::<(i64,)>(&mut rc).await { Ok((n,)) => n, Err(_) => return err(StatusCode::SERVICE_UNAVAILABLE, &r.id, "redis") };
    if n > app.rate_limit { return err(StatusCode::TOO_MANY_REQUESTS, &r.id, "rate") }
    // 3. validate
    if let Some(reason) = validate(&r) { return err(StatusCode::UNPROCESSABLE_ENTITY, &r.id, reason); }
    // 4. record as pending; a repeated id is an idempotent replay
    let db = match app.db.get().await { Ok(c) => c, Err(_) => return err(StatusCode::SERVICE_UNAVAILABLE, &r.id, "db") };
    let inserted = db.execute("INSERT INTO payments (id, merchant, amount, currency, status) VALUES ($1, $2, $3, $4, 'pending') ON CONFLICT (id) DO NOTHING",
        &[&r.id, &r.merchant, &r.amount, &r.currency]).await;
    match inserted {
        Ok(0) => {
            let row = db.query_opt("SELECT status, coalesce(provider_ref, '') FROM payments WHERE id = $1", &[&r.id]).await.ok().flatten();
            let (status, pref): (String, String) = row.map(|x| (x.get(0), x.get(1))).unwrap_or_default();
            return Json(json!({"id": r.id, "status": "duplicate", "original": status, "providerRef": pref})).into_response();
        }
        Ok(_) => {}
        Err(_) => return err(StatusCode::SERVICE_UNAVAILABLE, &r.id, "db"),
    }
    drop(db); // do not hold a database connection across the provider call
    // 5. charge with the provider
    let charged = app.http.post(&app.provider).json(&json!({"id": r.id, "amount": r.amount, "currency": r.currency})).send().await;
    let pref = match charged {
        Ok(resp) if resp.status().is_success() => resp.json::<ProviderReply>().await.ok().map(|p| p.reference),
        _ => None,
    };
    let mut db = match app.db.get().await { Ok(c) => c, Err(_) => return err(StatusCode::SERVICE_UNAVAILABLE, &r.id, "db") };
    let Some(pref) = pref else {
        let _ = db.execute("UPDATE payments SET status = 'failed', updated_at = now() WHERE id = $1", &[&r.id]).await;
        tracing::warn!(id = %r.id, merchant = %r.merchant, "provider failed");
        return err(StatusCode::BAD_GATEWAY, &r.id, "provider");
    };
    // 6. capture + balance in one transaction
    let result = async {
        let tx = db.transaction().await?;
        tx.execute("UPDATE payments SET status = 'captured', provider_ref = $2, updated_at = now() WHERE id = $1", &[&r.id, &pref]).await?;
        let row = tx.query_one("INSERT INTO balances (merchant, total, count) VALUES ($1, $2, 1) ON CONFLICT (merchant) DO UPDATE SET total = balances.total + EXCLUDED.total, count = balances.count + 1 RETURNING total, count",
            &[&r.merchant, &r.amount]).await?;
        tx.commit().await?;
        Ok::<(i64, i64), tokio_postgres::Error>((row.get(0), row.get(1)))
    }.await;
    let Ok((total, count)) = result else { return err(StatusCode::SERVICE_UNAVAILABLE, &r.id, "db") };
    let mut mac = Hmac::<Sha256>::new_from_slice(SIGN_KEY).unwrap();
    mac.update(format!("{}|{}|{}|{}", r.id, r.merchant, r.amount, r.currency).as_bytes());
    tracing::info!(id = %r.id, merchant = %r.merchant, amount = r.amount, ms = t0.elapsed().as_secs_f64() * 1e3, "captured");
    Json(PayResponse { id: r.id, status: "captured", provider_ref: pref, signature: hex(&mac.finalize().into_bytes()), merchant_count: count, merchant_total: total }).into_response()
}

fn env(k: &str, d: &str) -> String { std::env::var(k).unwrap_or_else(|_| d.to_string()) }

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt().json().with_target(false).init();
    let mut pg = tokio_postgres::Config::new();
    pg.host(&env("DB_HOST", "localhost")).port(5432).user(&env("DB_USER", "pay")).password(env("DB_PASS", "pay")).dbname(&env("DB_NAME", "pay"));
    let mgr = Manager::from_config(pg, tokio_postgres::NoTls, ManagerConfig { recycling_method: RecyclingMethod::Fast });
    let db = Pool::builder(mgr).max_size(env("DB_POOL", "32").parse().unwrap()).build().unwrap();
    let redis = redis::Client::open(format!("redis://{}:6379/", env("REDIS_HOST", "localhost"))).unwrap().get_connection_manager().await.unwrap();
    let http = reqwest::Client::builder().timeout(Duration::from_millis(env("PROVIDER_TIMEOUT_MS", "1000").parse().unwrap())).pool_max_idle_per_host(256).build().unwrap();
    let secret = env("JWT_SECRET", "probes-test-jwt-secret-0123456789abcdef");
    let mut val = Validation::new(Algorithm::HS256);
    val.set_issuer(&["probes-test"]); val.set_audience(&["payments"]);
    let app = Arc::new(App { db, redis, http, provider: env("PROVIDER_URL", "http://localhost:9000/charge"), jwt_key: DecodingKey::from_secret(secret.as_bytes()),
        jwt_val: val, rate_limit: env("RATE_LIMIT", "100000").parse().unwrap() });
    let router = Router::new().route("/health", get(|| async { "ok" })).route("/pay", post(pay)).with_state(app);
    let l = tokio::net::TcpListener::bind(format!("0.0.0.0:{}", env("PORT", "8080"))).await.unwrap();
    axum::serve(l, router).await.unwrap();
}
