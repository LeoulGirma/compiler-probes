// .NET 11 feature probes — Go counterparts. Same semantics as cs2/Probes2.cs and rust2/probes2.rs.
// Go has no generic methods, no default methods and no async/await, so each probe uses Go's nearest idiom:
//
//	gvm         a generic function whose type parameter has a method (Go's GC-shape stenciling + dictionaries)
//	dim         an interface call to a method promoted from an embedded struct (Go's "default implementation")
//	async_sync  a plain call chain: goroutines have growable stacks, so Go needs no async transform at all
//	async_yield one goroutine hand-off per operation (send request, worker runs the chain, sends reply)
package main

import (
	"encoding/json"
	"fmt"
	"math/bits"
	"os"
	"runtime"
	"slices"
	"sort"
	"strconv"
	"time"
)

const N, DEPTH = 4096, 10

// ---- devirtualisation ----
type Applier interface{ Apply(x int32) int32 }
type AddOne struct{}

func (AddOne) Apply(x int32) int32 { return x + 1 }

//go:noinline
func gvmLoop[O Applier](op O, a []int32) int32 {
	var s int32
	for i := 0; i < len(a); i++ {
		s += op.Apply(a[i])
	}
	return s
}

var op1 = AddOne{}

//go:noinline
func probeGvm(a []int32) int32 { return gvmLoop(op1, a) }

type Scaler interface{ Scale(x int32) int32 }
type ScaleBase struct{}

func (ScaleBase) Scale(x int32) int32 { return x * 3 }

type Tripler struct{ ScaleBase }

var sc Scaler = Tripler{}

//go:noinline
func probeDim(a []int32) int32 {
	var s int32
	for i := 0; i < len(a); i++ {
		s += sc.Scale(a[i])
	}
	return s
}

// ---- bounds checks ----
//
//go:noinline
func probePairs(a []int32) int32 {
	var s int32
	for i := 0; i+1 < len(a); i++ {
		s += a[i] * a[i+1]
	}
	return s
}

//go:noinline
func probeFromEnd(xs [][]int32) int32 {
	var s int32
	for _, x := range xs {
		if len(x) > 0 {
			s += x[len(x)-1]
		}
	}
	return s
}

//go:noinline
func probeGuard(xs [][]int32, v int32) int32 {
	var c int32
	for _, x := range xs {
		if len(x) > 0 && x[0] == v {
			c++
		}
	}
	return c
}

// ---- 128-bit multiply (Go has only the unsigned form: bits.Mul64) ----
const KU uint64 = 0x9E3779B97F4A7C15

//go:noinline
func probeBigMulU(a []uint64) uint64 {
	var acc uint64
	for i := 0; i < len(a); i++ {
		hi, lo := bits.Mul64(a[i], KU)
		acc += hi ^ lo
	}
	return acc
}

// ---- "async" ----
//
//go:noinline
func chain(depth int, x int32) int32 {
	if depth == 0 {
		return x + 1
	}
	return chain(depth-1, x) + 1
}

//go:noinline
func probeAsync(n int) int64 {
	var s int64
	for i := 0; i < n; i++ {
		s += int64(chain(DEPTH, int32(i)))
	}
	return s
}

var req, rep = make(chan int32), make(chan int32)

func worker() {
	for x := range req {
		rep <- chain(DEPTH, x)
	}
}

//go:noinline
func probeAsyncYield(n int) int64 {
	var s int64
	for i := 0; i < n; i++ {
		req <- int32(i)
		s += int64(<-rep)
	}
	return s
}

// ---- startup work ----
type Key struct{ A, B int32 }

func startup(t0 time.Time) map[string]float64 {
	us := func() float64 { return float64(time.Since(t0).Nanoseconds()) / 1e3 }
	tMain := us()
	d := map[Key]int32{}
	for i := int32(0); i < 20000; i++ {
		d[Key{i, i * 3}] = i
	}
	var s int64
	for i := int32(0); i < 20000; i++ {
		s += int64(d[Key{i, i * 3}])
	}
	tDict := us()
	hs := map[int64]struct{}{}
	for i := int64(0); i < 20000; i++ {
		hs[i*7919] = struct{}{}
	}
	s += int64(len(hs))
	ds := map[string]int{}
	for i := 0; i < 2000; i++ {
		ds["k"+strconv.Itoa(i)] = i
	}
	s += int64(ds["k1999"])
	tSet := us()
	l := make([]int64, 0, 20000)
	for i := int64(0); i < 20000; i++ {
		l = append(l, (i*7919)%20011)
	}
	slices.Sort(l)
	s += l[100]
	keys := make([]Key, 0, 2000)
	for i := int32(0); i < 2000; i++ {
		keys = append(keys, Key{i % 97, i})
	}
	s += int64(slices.Index(keys, Key{5, 1999}))
	if slices.Contains(keys, Key{1, 1}) {
		s++
	}
	tSort := us()
	return map[string]float64{"main_us": tMain, "dict_us": tDict - tMain, "set_us": tSet - tDict, "sort_us": tSort - tSet, "total_us": tSort, "check": float64(s)}
}

var sink int64

func bench(f func() int64, reps int) float64 {
	// Windows' monotonic clock ticks every ~0.5 ms, so grow each batch until it lasts at least 20 ms
	for {
		t := time.Now()
		for i := 0; i < reps; i++ {
			sink += f()
		}
		if time.Since(t) >= 20*time.Millisecond {
			break
		}
		reps *= 2
	}
	v := make([]float64, 0, 15)
	for k := 0; k < 15; k++ {
		t := time.Now()
		for i := 0; i < reps; i++ {
			sink += f()
		}
		v = append(v, float64(time.Since(t).Nanoseconds())/float64(reps))
	}
	sort.Float64s(v)
	return v[len(v)/2]
}

func allocBytes(f func()) float64 {
	var m0, m1 runtime.MemStats
	runtime.ReadMemStats(&m0)
	f()
	runtime.ReadMemStats(&m1)
	return float64(m1.TotalAlloc - m0.TotalAlloc)
}

func main() {
	t0 := time.Now() // Go's runtime is initialised before main; process start time is measured by the driver
	mode := "bench"
	if len(os.Args) > 1 {
		mode = os.Args[1]
	}
	if mode == "startup" {
		b, _ := json.Marshal(startup(t0))
		fmt.Println(string(b))
		return
	}
	a := make([]int32, N)
	ua := make([]uint64, N)
	for i := 0; i < N; i++ {
		a[i] = int32((i * 7) % 1000)
		ua[i] = uint64(i)*0x9E3779B1 + 12345
	}
	xs := make([][]int32, 1024)
	for i := range xs {
		xs[i] = make([]int32, i%5)
		for j := range xs[i] {
			xs[i][j] = int32((i + j) % 7)
		}
	}
	go worker()
	const AN, YN = 1000, 200
	r := map[string]any{}
	r["gvm"] = bench(func() int64 { return int64(probeGvm(a)) }, 1000)
	r["dim"] = bench(func() int64 { return int64(probeDim(a)) }, 1000)
	r["pairs"] = bench(func() int64 { return int64(probePairs(a)) }, 2000)
	r["from_end"] = bench(func() int64 { return int64(probeFromEnd(xs)) }, 4000)
	r["guard"] = bench(func() int64 { return int64(probeGuard(xs, 3)) }, 4000)
	r["bigmul_u"] = bench(func() int64 { return int64(probeBigMulU(ua)) }, 2000)
	r["async_ns_per_await"] = bench(func() int64 { return probeAsync(AN) }, 20) / (AN * (DEPTH + 1))
	r["async_bytes_per_await"] = allocBytes(func() { sink += probeAsync(AN) }) / (AN * (DEPTH + 1))
	r["yield_ns_per_op"] = bench(func() int64 { return probeAsyncYield(YN) }, 5) / YN
	r["yield_bytes_per_op"] = allocBytes(func() { sink += probeAsyncYield(YN) }) / YN
	r["check"] = int64(probeGvm(a)) + int64(probeDim(a)) + int64(probePairs(a)) + int64(probeFromEnd(xs)) + int64(probeGuard(xs, 3)) + int64(probeBigMulU(ua)) + probeAsync(10)
	r["runtime"] = runtime.Version()
	b, _ := json.Marshal(r)
	fmt.Println(string(b))
}
