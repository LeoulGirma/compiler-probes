// Compiler probes — Rust. Same semantics as go/main.go and cs/Probes.cs.
// Build: rustc -C opt-level=3 probes.rs   (what `cargo build --release` uses)
use std::alloc::{GlobalAlloc, Layout, System};
use std::hint::black_box;
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
use std::time::Instant;

struct Counting;
static ALLOCS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);
unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 { ALLOCS.fetch_add(1, Relaxed); BYTES.fetch_add(l.size(), Relaxed); System.alloc(l) }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) { System.dealloc(p, l) }
}
#[cfg(count_allocs)]
#[global_allocator]
static GA: Counting = Counting;

const N: usize = 4096;

// P1 vectorise: plain sum of an array
#[no_mangle] #[inline(never)]
pub fn probe_vec_sum(a: &[i32]) -> i32 { let mut s = 0i32; for &x in a { s = s.wrapping_add(x); } s }

// P2 bounds checks: one array indexed by its own length / two arrays indexed by the first's length
#[no_mangle] #[inline(never)]
pub fn probe_bounds_one(a: &[i32]) -> i32 { let mut s = 0i32; for i in 0..a.len() { s = s.wrapping_add(a[i]); } s }
#[no_mangle] #[inline(never)]
pub fn probe_bounds_two(a: &[i32], b: &[i32]) -> i32 { let mut s = 0i32; for i in 0..a.len() { s = s.wrapping_add(a[i].wrapping_mul(b[i])); } s }

// P3 devirtualisation: calls through a trait object (Go/C# interface equivalent), all the same concrete type
pub trait Shape { fn area(&self) -> i64; }
pub struct Square { side: i64 }
impl Shape for Square { fn area(&self) -> i64 { self.side * self.side } }
#[no_mangle] #[inline(never)]
pub fn probe_dyn(xs: &[Box<dyn Shape>]) -> i64 { let mut s = 0i64; for x in xs { s = s.wrapping_add(x.area()); } s }
#[inline(never)]
fn generic_total<T: Shape>(xs: &[T]) -> i64 { let mut s = 0i64; for x in xs { s = s.wrapping_add(x.area()); } s }
#[no_mangle] #[inline(never)]
pub fn probe_generic(xs: &[Square]) -> i64 { generic_total(xs) }

// P4 allocation: a short-lived heap object per element that never escapes
pub struct Point { x: i64, y: i64 }
#[no_mangle] #[inline(never)]
pub fn probe_alloc(a: &[i32]) -> i64 {
    let mut s = 0i64;
    for &v in a { let p = Box::new(Point { x: v as i64, y: (v as i64) * 2 }); s = s.wrapping_add(p.x + p.y); }
    s
}

fn median(mut v: Vec<f64>) -> f64 { v.sort_by(|a, b| a.partial_cmp(b).unwrap()); v[v.len() / 2] }
fn bench<F: FnMut() -> i64>(mut f: F, reps: usize) -> f64 {
    for _ in 0..reps { black_box(f()); }
    let mut v = Vec::new();
    for _ in 0..15 { let t = Instant::now(); for _ in 0..reps { black_box(f()); } v.push(t.elapsed().as_nanos() as f64 / reps as f64); }
    median(v)
}

fn main() {
    let mode = std::env::args().nth(1).unwrap_or_else(|| "bench".into());
    let a: Vec<i32> = (0..N as i32).map(|i| (i * 7) % 1000).collect();
    let b: Vec<i32> = (0..N as i32).map(|i| (i * 13) % 1000).collect();
    if mode == "warmup" {
        let mut out = Vec::new();
        for _ in 0..20000 { let t = Instant::now(); black_box(probe_vec_sum(black_box(&a))); out.push(t.elapsed().as_nanos() as u64); }
        println!("{{\"calls_ns\":{:?}}}", out);
        return;
    }
    let shapes: Vec<Box<dyn Shape>> = (0..N as i64).map(|i| Box::new(Square { side: i % 100 }) as Box<dyn Shape>).collect();
    let squares: Vec<Square> = (0..N as i64).map(|i| Square { side: i % 100 }).collect();
    let r_vec = bench(|| probe_vec_sum(black_box(&a)) as i64, 2000);
    let r_b1 = bench(|| probe_bounds_one(black_box(&a)) as i64, 2000);
    let r_b2 = bench(|| probe_bounds_two(black_box(&a), black_box(&b)) as i64, 1000);
    let r_dyn = bench(|| probe_dyn(black_box(&shapes)), 500);
    let r_gen = bench(|| probe_generic(black_box(&squares)), 500);
    let a0 = ALLOCS.load(Relaxed); let by0 = BYTES.load(Relaxed);
    black_box(probe_alloc(black_box(&a)));
    let allocs = (ALLOCS.load(Relaxed) - a0) as f64 / N as f64; let bytes = (BYTES.load(Relaxed) - by0) as f64 / N as f64;
    let counted = cfg!(count_allocs);
    let r_alloc = bench(|| probe_alloc(black_box(&a)), 300);
    let chk = probe_vec_sum(&a) as i64 + probe_dyn(&shapes) + probe_alloc(&a);
    println!("{{\"n\":{},\"vec_sum\":{:.1},\"bounds_one\":{:.1},\"bounds_two\":{:.1},\"dyn\":{:.1},\"generic\":{:.1},\"alloc\":{:.1},\"alloc_per_elem\":{:.3},\"alloc_bytes_per_elem\":{:.1},\"alloc_counted\":{},\"check\":{}}}",
        N, r_vec, r_b1, r_b2, r_dyn, r_gen, r_alloc, allocs, bytes, counted, chk);
}
