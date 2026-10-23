// .NET 11 feature probes — Rust counterparts. Same semantics as cs2/Probes2.cs and go2/main.go.
// Build: rustc -C opt-level=3 probes2.rs   (no crates; async uses a minimal hand-written executor)
//   gvm         generic method -> monomorphised static dispatch (Rust cannot put generic methods in a vtable)
//   dim         trait default method called through &dyn from a static (LLVM may devirtualise the constant vtable)
//   async_sync  DEPTH nested async fns, polled once; futures nest inline, no heap
//   async_yield the leaf returns Pending once; the executor re-polls (cheapest possible suspension, no threads)
use std::collections::{HashMap, HashSet};
use std::future::Future;
use std::hint::black_box;
use std::pin::{pin, Pin};
use std::task::{Context, Poll, Waker};
use std::time::Instant;

const N: usize = 4096;
const DEPTH: usize = 10;

// ---- devirtualisation ----
pub trait Op { fn apply<T: std::ops::Add<Output = T> + From<u8>>(&self, x: T) -> T; }
pub struct AddOne;
impl Op for AddOne { #[inline] fn apply<T: std::ops::Add<Output = T> + From<u8>>(&self, x: T) -> T { x + T::from(1u8) } }
static OP1: AddOne = AddOne;
#[no_mangle] #[inline(never)]
pub fn probe_gvm(a: &[i32]) -> i32 { let mut s = 0i32; for &x in a { s = s.wrapping_add(OP1.apply(x)); } s }

pub trait Scale { fn scale(&self, x: i32) -> i32 { x.wrapping_mul(3) } }
pub struct Tripler;
impl Scale for Tripler {}
static SC: &(dyn Scale + Sync) = &Tripler;
#[no_mangle] #[inline(never)]
pub fn probe_dim(a: &[i32]) -> i32 { let sc = black_box(SC); let mut s = 0i32; for &x in a { s = s.wrapping_add(sc.scale(x)); } s }

// ---- bounds checks ----
#[no_mangle] #[inline(never)]
pub fn probe_pairs(a: &[i32]) -> i32 { let mut s = 0i32; let mut i = 0; while i + 1 < a.len() { s = s.wrapping_add(a[i].wrapping_mul(a[i + 1])); i += 1; } s }
#[no_mangle] #[inline(never)]
pub fn probe_from_end(xs: &[Vec<i32>]) -> i32 { let mut s = 0i32; for x in xs { if x.len() > 0 { s = s.wrapping_add(x[x.len() - 1]); } } s }
#[no_mangle] #[inline(never)]
pub fn probe_guard(xs: &[Vec<i32>], v: i32) -> i32 { let mut c = 0; for x in xs { let sp: &[i32] = x; if !sp.is_empty() && sp[0] == v { c += 1; } } c }

// ---- 128-bit multiply ----
const KS: i64 = 0x5DEECE66D_i64 * 977; const KU: u64 = 0x9E3779B97F4A7C15;
#[no_mangle] #[inline(never)]
pub fn probe_bigmul_s(a: &[i64]) -> i64 { let mut acc = 0i64; for &x in a { let p = (x as i128) * (KS as i128); acc = acc.wrapping_add(((p >> 64) as i64) ^ (p as i64)); } acc }
#[no_mangle] #[inline(never)]
pub fn probe_bigmul_u(a: &[u64]) -> u64 { let mut acc = 0u64; for &x in a { let p = (x as u128) * (KU as u128); acc = acc.wrapping_add(((p >> 64) as u64) ^ (p as u64)); } acc }

// ---- async ----
struct YieldOnce(bool);
impl Future for YieldOnce {
    type Output = ();
    fn poll(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<()> {
        if self.0 { Poll::Ready(()) } else { self.0 = true; cx.waker().wake_by_ref(); Poll::Pending }
    }
}
macro_rules! chain { ($($name:ident => $next:ident),*) => { $(
    #[inline(never)] async fn $name(x: i32, y: bool) -> i32 { $next(x, y).await + 1 }
)* } }
#[inline(never)] async fn c0(x: i32, y: bool) -> i32 { if y { YieldOnce(false).await; } x + 1 }
chain!(c1 => c0, c2 => c1, c3 => c2, c4 => c3, c5 => c4, c6 => c5, c7 => c6, c8 => c7, c9 => c8, c10 => c9);
fn block_on<F: Future>(f: F) -> F::Output {
    let mut f = pin!(f); let mut cx = Context::from_waker(Waker::noop());
    loop { if let Poll::Ready(v) = f.as_mut().poll(&mut cx) { return v; } }
}
#[no_mangle] #[inline(never)]
pub fn probe_async(n: usize, y: bool) -> i64 { block_on(async move { let mut s = 0i64; for i in 0..n { s += c10(i as i32, y).await as i64; } s }) }

// ---- startup work ----
#[derive(Clone, Copy, PartialEq, Eq, Hash)] struct Key { a: i32, b: i32 }
fn startup(t0: Instant) -> String {
    let us = || t0.elapsed().as_nanos() as f64 / 1e3;
    let t_main = us();
    let mut d = HashMap::new(); for i in 0..20000i32 { d.insert(Key { a: i, b: i * 3 }, i); }
    let mut s = 0i64; for i in 0..20000i32 { s += d[&Key { a: i, b: i * 3 }] as i64; }
    let t_dict = us();
    let mut hs = HashSet::new(); for i in 0..20000i64 { hs.insert(i * 7919); } s += hs.len() as i64;
    let mut ds = HashMap::new(); for i in 0..2000 { ds.insert(format!("k{i}"), i); } s += ds["k1999"] as i64;
    let t_set = us();
    let mut l: Vec<i64> = (0..20000i64).map(|i| (i * 7919) % 20011).collect(); l.sort(); s += l[100];
    let keys: Vec<Key> = (0..2000).map(|i| Key { a: i % 97, b: i }).collect();
    s += keys.iter().position(|k| *k == Key { a: 5, b: 1999 }).map(|p| p as i64).unwrap_or(-1) + keys.contains(&Key { a: 1, b: 1 }) as i64;
    let t_sort = us();
    format!("{{\"main_us\":{:.0},\"dict_us\":{:.0},\"set_us\":{:.0},\"sort_us\":{:.0},\"total_us\":{:.0},\"check\":{}}}", t_main, t_dict - t_main, t_set - t_dict, t_sort - t_set, t_sort, s)
}

fn median(mut v: Vec<f64>) -> f64 { v.sort_by(|a, b| a.partial_cmp(b).unwrap()); v[v.len() / 2] }
fn bench<F: FnMut() -> i64>(mut f: F, reps: usize) -> f64 {
    for _ in 0..reps { black_box(f()); }
    let mut v = Vec::new();
    for _ in 0..15 { let t = Instant::now(); for _ in 0..reps { black_box(f()); } v.push(t.elapsed().as_nanos() as f64 / reps as f64); }
    median(v)
}

fn main() {
    let t0 = Instant::now();
    let mode = std::env::args().nth(1).unwrap_or_else(|| "bench".into());
    if mode == "startup" { println!("{}", startup(t0)); return; }
    let a: Vec<i32> = (0..N as i32).map(|i| (i * 7) % 1000).collect();
    let la: Vec<i64> = (0..N as i64).map(|i| i * 0x1F3D5B79 - 7_000_000_000).collect();
    let ua: Vec<u64> = (0..N as u64).map(|i| i * 0x9E3779B1 + 12345).collect();
    let xs: Vec<Vec<i32>> = (0..1024).map(|i| (0..i % 5).map(|j| ((i + j) % 7) as i32).collect()).collect();
    const AN: usize = 1000; const YN: usize = 200;
    let r_gvm = bench(|| probe_gvm(black_box(&a)) as i64, 1000);
    let r_dim = bench(|| probe_dim(black_box(&a)) as i64, 1000);
    let r_pairs = bench(|| probe_pairs(black_box(&a)) as i64, 2000);
    let r_end = bench(|| probe_from_end(black_box(&xs)) as i64, 4000);
    let r_guard = bench(|| probe_guard(black_box(&xs), black_box(3)) as i64, 4000);
    let r_bs = bench(|| probe_bigmul_s(black_box(&la)), 2000);
    let r_bu = bench(|| probe_bigmul_u(black_box(&ua)) as i64, 2000);
    let r_async = bench(|| probe_async(black_box(AN), false), 20) / (AN * (DEPTH + 1)) as f64;
    let r_yield = bench(|| probe_async(black_box(YN), true), 5) / YN as f64;
    let chk = probe_gvm(&a) as i64 + probe_dim(&a) as i64 + probe_pairs(&a) as i64 + probe_from_end(&xs) as i64 + probe_guard(&xs, 3) as i64
        + probe_bigmul_s(&la) + probe_bigmul_u(&ua) as i64 + probe_async(10, false);
    // allocation per await is 0 by construction (no Box, no executor queue); the driver confirms there is no allocator call in the asm
    println!("{{\"gvm\":{:.1},\"dim\":{:.1},\"pairs\":{:.1},\"from_end\":{:.1},\"guard\":{:.1},\"bigmul_s\":{:.1},\"bigmul_u\":{:.1},\"async_ns_per_await\":{:.2},\"async_bytes_per_await\":0,\"yield_ns_per_op\":{:.0},\"yield_bytes_per_op\":0,\"check\":{}}}",
        r_gvm, r_dim, r_pairs, r_end, r_guard, r_bs, r_bu, r_async, r_yield, chk);
}
