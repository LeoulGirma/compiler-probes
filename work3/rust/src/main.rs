// Payment-style HTTP service — Rust (axum on tokio, serde_json, hmac + sha2). Same contract as cs/Program.cs and go/main.go.
// Worker threads: WORKERS env var (the driver sets it to the CPUs the process is pinned to), else tokio's default.
use axum::{http::StatusCode, response::IntoResponse, routing::{get, post}, Json, Router};
use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

#[derive(Deserialize)] struct Payer { msisdn: String, #[allow(dead_code)] name: String }
#[derive(Deserialize)] struct Item { #[allow(dead_code)] sku: String, qty: i32, price: i64 }
#[derive(Deserialize)]
struct PayRequest { id: String, merchant: String, amount: i64, currency: String, payer: Payer, items: Vec<Item>, #[allow(dead_code)] note: String }
#[derive(Serialize)] #[serde(rename_all = "camelCase")]
struct PayResponse { id: String, status: &'static str, signature: String, merchant_count: i64, merchant_total: i64 }
#[derive(Serialize)] struct PayRejected { id: String, status: &'static str, reason: &'static str }

static SHARDS: OnceLock<Vec<Mutex<HashMap<String, (i64, i64)>>>> = OnceLock::new();
const KEY: &[u8] = b"probes-demo-signing-key-0123456789";

fn fnv(s: &str) -> u32 { let mut h: u32 = 2166136261; for c in s.chars() { h = (h ^ c as u32).wrapping_mul(16777619); } h }

// completes immediately, like a cache hit in front of a database; still awaited, as real handlers are
async fn record(merchant: &str, amount: i64) -> (i64, i64) {
    let mut m = SHARDS.get().unwrap()[(fnv(merchant) % 64) as usize].lock().unwrap();
    let e = m.entry(merchant.to_string()).or_insert((0, 0));
    e.0 += 1; e.1 += amount; *e
}

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

fn hex(b: &[u8]) -> String { const H: &[u8; 16] = b"0123456789abcdef"; let mut s = String::with_capacity(b.len() * 2); for x in b { s.push(H[(x >> 4) as usize] as char); s.push(H[(x & 15) as usize] as char); } s }

async fn pay(Json(r): Json<PayRequest>) -> axum::response::Response {
    if let Some(reason) = validate(&r) {
        return (StatusCode::UNPROCESSABLE_ENTITY, Json(PayRejected { id: r.id, status: "rejected", reason })).into_response();
    }
    let mut mac = Hmac::<Sha256>::new_from_slice(KEY).unwrap();
    mac.update(format!("{}|{}|{}|{}", r.id, r.merchant, r.amount, r.currency).as_bytes());
    let signature = hex(&mac.finalize().into_bytes());
    let (c, t) = record(&r.merchant, r.amount).await;
    Json(PayResponse { id: r.id, status: "accepted", signature, merchant_count: c, merchant_total: t }).into_response()
}

fn main() {
    SHARDS.set((0..64).map(|_| Mutex::new(HashMap::new())).collect()).ok();
    let mut b = tokio::runtime::Builder::new_multi_thread();
    if let Some(n) = std::env::var("WORKERS").ok().and_then(|v| v.parse().ok()) { b.worker_threads(n); }
    b.enable_all().build().unwrap().block_on(async {
        let port = std::env::var("PORT").unwrap_or_else(|_| "8080".into());
        let app = Router::new().route("/health", get(|| async { "ok" })).route("/pay", post(pay));
        let l = tokio::net::TcpListener::bind(format!("127.0.0.1:{port}")).await.unwrap();
        axum::serve(l, app).await.unwrap();
    });
}
