// GC stress — Rust. Same workload as gc/cs/Program.cs and gc/go/main.go. Rust has no GC: each object is freed when it is
// replaced or goes out of scope, so this measures the cost of the system allocator doing the same churn.
// Build: rustc -C opt-level=3 main.rs
use std::hint::black_box;
use std::time::Instant;

struct Order { id: String, amount: i64, tags: Box<[i32]> }
fn new_order(i: usize, a: i64) -> Box<Order> {
    let i32_ = i as i32;
    Box::new(Order { id: format!("ord-{:09}", i), amount: a, tags: vec![i32_ & 7, i32_ & 15, i32_ & 31, i32_ & 63].into_boxed_slice() })
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let live: usize = a.get(1).and_then(|s| s.parse().ok()).unwrap_or(1_000_000);
    let seconds: f64 = a.get(2).and_then(|s| s.parse().ok()).unwrap_or(10.0);
    let b0 = Instant::now();
    let mut set: Vec<Box<Order>> = (0..live).map(|i| new_order(i, i as i64 * 3)).collect();
    let build_ms = b0.elapsed().as_secs_f64() * 1e3;
    let mut rng: u64 = 42;
    let mut lat: Vec<f64> = Vec::with_capacity(1 << 20);
    let mut sink: i64 = 0; let mut next = live;
    let start = Instant::now();
    loop {
        let t = Instant::now();
        if (t - start).as_secs_f64() >= seconds { break; }
        for k in 0..200 { let o = black_box(new_order(next + k, k as i64)); sink += o.amount + o.id.len() as i64 + o.tags[3] as i64; }
        for k in 0..20 {
            rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
            set[(rng % live as u64) as usize] = new_order(next, k); next += 1;
        }
        lat.push(t.elapsed().as_secs_f64() * 1e6);
    }
    let total: f64 = lat.iter().sum();
    lat.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let p = |q: f64| lat[(q * (lat.len() - 1) as f64) as usize];
    let over = |lim: f64| lat.iter().filter(|&&v| v > lim).count();
    println!("{{\"iterations\":{},\"iter_per_s\":{:.0},\"p50_us\":{:.1},\"p99_us\":{:.1},\"p999_us\":{:.1},\"max_us\":{:.1},\"over_1ms\":{},\"over_10ms\":{},\"build_ms\":{:.0},\"sink\":{},\"gc_pause_ms\":0,\"runtime\":\"no GC (system allocator)\"}}",
        lat.len(), lat.len() as f64 / (total / 1e6), p(0.5), p(0.99), p(0.999), lat[lat.len() - 1], over(1000.0), over(10000.0), build_ms,
        (sink + set[live / 2].amount) % 1000);
}
