# Compiler probes

Rust, Go and C# (.NET 10, .NET 11 RC2 and Native AOT) measured in four steps, from the machine code each
compiler emits to a payment service running in containers. This repository holds the harnesses, the raw
results and the scripts that turn them into the site and the video.

**Read the results:** https://leoulgirma.github.io/compiler-probes/ (start page, an eight-minute explainer video, and one page per set).

**Main finding:** the gap between the fastest and slowest language was 7.3× in a tight loop, 1.26× for an
in-memory HTTP API, and 1.05× on median latency once Postgres, Redis and a payment provider were in the path.
The ratios measure different things; that is the point.

| Set | Question | Folder | Raw results |
|---|---|---|---|
| 1 · Machine code | What does each compiler do with five small functions? | `probe.py`, `cs/`, `go/`, `rust/` | `results.json`, `results.laptop.json` |
| 2 · .NET 11 claims | Do the runtime changes listed for .NET 11 show up when measured? | `probe2.py`, `cs2/`, `go2/`, `rust2/` | `data2.json` |
| 3 · Under load | How close are the languages serving an in-memory API? | `work3/` | `work3/data3.json` |
| 4 · In containers | What changes with a database, a cache and a failing provider? | `work4/` | `work4/results/*.json` |

## Machine and versions

Intel Core i5-10300H laptop (4 cores, 8 threads), Windows 11, plugged in, turbo on, nothing else running.
Set 4 runs in Docker Desktop's Linux VM with 4 CPUs; each service is capped at 1 CPU and 512 MB.
.NET 10.0.12 (SDK 10.0.401) and .NET 11.0.0-rc.2.26504.105, Go 1.27.2, Rust 1.99.0, Postgres 17, Redis 7.
Out-of-the-box release settings everywhere: `cargo --release`, `go build`, C# Release with server GC and
tiered PGO. Opt-ins (runtime async, Native AOT, ReadyToRun, Go PGO) are separate, labelled builds.

## Reproduce

Each set is independent. Durations are for the laptop above.

### Set 1 · machine code (about 10 minutes)
```sh
rustup toolchain install 1.99.0
python probe.py --rust 1.99.0 --go go1.27.2 --dotnet 10
python probe.py --only cs --dotnet 11          # adds a .NET 11 column
python probe.py --only cs --dotnet 10 --aot    # adds ReadyToRun and Native AOT builds
```
Writes `results.json`: timings, warm-up curves, build times and the disassembly of every probe.
See `docs/set1-probe-reference.md` for what each probe isolates.

### Set 2 · .NET 11 claims (about 15 minutes)
```sh
# one round = all four commands writing to the same file; the site used three rounds
python probe2.py --only cs --dotnet 10 --aot --out round1.json
python probe2.py --only cs --dotnet 11 --aot --out round1.json   # JIT (runtime async off and on), ReadyToRun, Native AOT
python probe2.py --only rust --out round1.json ; python probe2.py --only go --out round1.json
python aggregate2.py round1.json round2.json round3.json data2.json   # medians (+min/max) per column
```

### Set 3 · under load (Windows, about 40 minutes per round)
Needs the .NET 10 and 11 RC2 SDKs side by side in one folder (set `DOTNET_LOCAL`), Go and Rust.
```sh
python work3/workload3.py build
python work3/workload3.py run --round 1        # repeat for rounds 2 and 3
python work3/aggregate3.py work3/w_round1.json work3/w_round2.json work3/w_round3.json work3/data3.json
```
Follow-up, the thread-pool spin limit (.NET 11 raised `DOTNET_ThreadPool_UnfairSemaphoreSpinLimit` from 70 to 1024):
`python work3/spin3.py build` then `python work3/spin3.py run --rounds 4` (about 25 minutes on a quiet machine; it waits
for background load to settle before each run). The published runs are `work3/spin3_run1.json` and `spin3_run2.json`.
The server is pinned to CPUs 0–3 and the load generator to 4–5; the load generator uses an open-loop schedule
so stalls are counted (see Concepts › open-loop load on the site).

### Set 4 · in containers (Docker, about 50 minutes per round)
```sh
python work4/build4.py                         # Linux binaries for Go, Rust and C# (JIT), then the images
docker compose -f work4/compose.yml --profile svc build cs10aot cs11aot   # Native AOT builds inside Linux
python work4/run4.py up
python work4/run4.py round --round 3 --tag _c --only cs10,cs11,cs11ra,go,rust
python work4/run4.py soak --minutes 8 --tag _c
```
Each round runs, per service: a cold start, 500 payments/s for 60 s after a 45 s warm-up, a closed-loop
throughput test, and a 90 s provider-degradation test (the middle 30 s: median 300 ms, 10% of calls hang).
After every phase it checks that each captured payment appears exactly once in a merchant balance.

The payment provider (`work4/mockpay`) is a mock with injected delays and failures. This is a realistic
simulation, not a deployed system.

**Which result files the site uses.** `r4_round1/2.json` and `r4_soak.json` were an early run with other
applications open and are kept for transparency only. The published numbers come from the clean rerun
(`r4_c_round3/4.json`, `r4_c_soak.json`, `r4_c2_soak.json`) and the Native AOT runs
(`r4_aot_round5/6.json`, `r4_aotx_round7–9.json`, `r4_aot_soak.json`).

## Known limits

- One machine. In sets 1–3, single runs varied by up to about 10%; smaller gaps there are noise. Set 4 counts a
  gap only when it is larger than the spread between repeated rounds.
- .NET 11 is a release candidate; numbers can change by the final release.
- One .NET 10 Native AOT round stalled during the provider outage (14,812 client timeouts); three repeats with
  database and log diagnostics were clean and the cause is unresolved. It is reported, not excluded.

## Site and video

`build_page.py`, `build_page2.py`, `work3/build_page3.py` and `work4/build_page4.py` bake the results into
`page/`; `build_guide.py` writes the start, concepts and takeaways pages; `build_site.py` assembles `site/`.
`video/explainer2.py` is the Manim source of the explainer; `video/lexicon.py` pins the pronunciation of every
technical term for the synthetic narrator (Kokoro-82M); `video/remix2.sh` renders, mixes and captions it.

Licence: MIT.
