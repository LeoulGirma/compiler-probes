# Compiler probes: Rust · Go · C#

Five small functions written the same way in all three languages, plus build time.
Each one isolates one thing a compiler or runtime does:

| Probe | Question it answers |
|---|---|
| `vec_sum` | Does the compiler auto-vectorise a plain loop (SIMD)? |
| `bounds_one` | Can it remove the bounds check when `i < a.length`? |
| `bounds_two` | …and when the bound only covers one of two arrays? |
| `dyn` | What does a call through an interface / trait object cost, with and without profile-guided optimisation? |
| `alloc` | Does a short-lived object that never escapes still hit the heap? |
| warm-up | How long until a fresh process runs at full speed? |
| build | How long does the toolchain take on this one file? |

`probe.py` builds everything, runs it, pulls out the machine code each compiler produced,
counts the telling instructions (vector adds, bounds-check exits, indirect calls, heap calls)
and writes `results.json`.

## Run

Requirements: Python 3.8+, and the toolchains. No cargo, NuGet or network needed.

```sh
# latest stable (as of Oct 2026)
rustup toolchain install 1.99.0
python3 probe.py --rust 1.99.0 --go go1.27.2 --dotnet 10

# add more C# columns to the same results.json
python3 probe.py --only cs --dotnet 11      # .NET 11 RC
python3 probe.py --only cs --dotnet 8

python3 build_page.py                       # writes compiler-probes.html with your numbers baked in
```

- `--rust X` uses `rustup run X rustc`; omit it to use `rustc` on PATH.
- `--go goX.Y.Z` sets `GOTOOLCHAIN`, so Go downloads that toolchain itself.
- `--dotnet N` picks the newest installed SDK and runtime with major version N (`dotnet --list-sdks`).

Or skip `build_page.py` and use **Load your results.json** on the published page.

## What "fair" means here

- Default, out-of-the-box builds: `rustc -C opt-level=3` (what `cargo build --release` does),
  plain `go build`, C# compiled with `-optimize+` and run on default runtime settings
  (tiered compilation and dynamic PGO on).
- Extra columns show the opt-in paths: Go with `-pgo=<profile>`, C# with `DOTNET_TieredPGO=0`, and Rust generics instead of `dyn`.
- Every steady-state number is the median of 15 timed batches, taken as the median across 3 processes.
- Rust's allocation count is read from the machine code (any allocator call left in `probe_alloc`).
  A counting allocator would stop LLVM from removing allocations, which is the thing being measured.
- Close the browser and other heavy apps first. On laptops, plug in power. Differences under ~1.5× are
  within normal run-to-run noise, and the page labels them "≈".

## Files

- `rust/probes.rs`, `go/main.go`, `cs/Probes.cs`: the probes (same semantics, same data).
- `probe.py`: driver. `build_page.py`: bakes results into the page. `page/template.html`: the page.
- `results.json`: the sample run (shared 2-vCPU cloud VM, Rust 1.97, Go 1.24.7, .NET 8 and 10).
