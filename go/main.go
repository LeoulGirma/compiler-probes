// Compiler probes — Go. Same semantics as rust/probes.rs and cs/Probes.cs.
// Build: go build -o probes .        PGO: run "./probes prof cpu.pprof", then go build -pgo=cpu.pprof
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"runtime"
	"runtime/pprof"
	"sort"
	"time"
)

const N = 4096

// P1 vectorise
//
//go:noinline
func probeVecSum(a []int32) int32 {
	var s int32
	for _, x := range a {
		s += x
	}
	return s
}

// P2 bounds checks
//
//go:noinline
func probeBoundsOne(a []int32) int32 {
	var s int32
	for i := 0; i < len(a); i++ {
		s += a[i]
	}
	return s
}

//go:noinline
func probeBoundsTwo(a, b []int32) int32 {
	var s int32
	for i := 0; i < len(a); i++ {
		s += a[i] * b[i]
	}
	return s
}

// P3 devirtualisation
type Shape interface{ Area() int64 }
type Square struct{ side int64 }

func (q *Square) Area() int64 { return q.side * q.side }

//go:noinline
func probeDyn(xs []Shape) int64 {
	var s int64
	for _, x := range xs {
		s += x.Area()
	}
	return s
}

// P4 allocation
type Point struct{ x, y int64 }

//go:noinline
func probeAlloc(a []int32) int64 {
	var s int64
	for _, v := range a {
		p := &Point{int64(v), int64(v) * 2}
		s += p.x + p.y
	}
	return s
}

var sink int64

func bench(f func() int64, reps int) float64 {
	for i := 0; i < reps; i++ {
		sink += f()
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

func main() {
	mode := "bench"
	if len(os.Args) > 1 {
		mode = os.Args[1]
	}
	a := make([]int32, N)
	b := make([]int32, N)
	for i := range a {
		a[i] = int32((i * 7) % 1000)
		b[i] = int32((i * 13) % 1000)
	}
	shapes := make([]Shape, N)
	for i := range shapes {
		shapes[i] = &Square{int64(i % 100)}
	}
	switch mode {
	case "warmup":
		out := make([]int64, 0, 20000)
		for i := 0; i < 20000; i++ {
			t := time.Now()
			sink += int64(probeVecSum(a))
			out = append(out, time.Since(t).Nanoseconds())
		}
		j, _ := json.Marshal(map[string]any{"calls_ns": out})
		fmt.Println(string(j))
		return
	case "prof":
		f, _ := os.Create(os.Args[2])
		pprof.StartCPUProfile(f)
		end := time.Now().Add(3 * time.Second)
		for time.Now().Before(end) {
			sink += probeDyn(shapes)
		}
		pprof.StopCPUProfile()
		f.Close()
		return
	}
	r := map[string]any{"n": N}
	r["vec_sum"] = bench(func() int64 { return int64(probeVecSum(a)) }, 2000)
	r["bounds_one"] = bench(func() int64 { return int64(probeBoundsOne(a)) }, 2000)
	r["bounds_two"] = bench(func() int64 { return int64(probeBoundsTwo(a, b)) }, 1000)
	r["dyn"] = bench(func() int64 { return probeDyn(shapes) }, 500)
	var m0, m1 runtime.MemStats
	runtime.GC()
	runtime.ReadMemStats(&m0)
	sink += probeAlloc(a)
	runtime.ReadMemStats(&m1)
	r["alloc_per_elem"] = float64(m1.Mallocs-m0.Mallocs) / N
	r["alloc_bytes_per_elem"] = float64(m1.TotalAlloc-m0.TotalAlloc) / N
	r["alloc"] = bench(func() int64 { return probeAlloc(a) }, 300)
	r["check"] = int64(probeVecSum(a)) + probeDyn(shapes) + probeAlloc(a)
	j, _ := json.Marshal(r)
	fmt.Println(string(j))
}
