// GC stress — Go. Same workload as gc/cs/Program.cs and gc/rust/main.rs.
package main

import (
	"encoding/json"
	"fmt"
	"math/rand"
	"os"
	"runtime"
	"sort"
	"strconv"
)

type Order struct {
	ID     string
	Amount int64
	Tags   []int32
}

func newOrder(i int, a int64) *Order {
	return &Order{ID: fmt.Sprintf("ord-%09d", i), Amount: a, Tags: []int32{int32(i & 7), int32(i & 15), int32(i & 31), int32(i & 63)}}
}

//go:noinline
func use(o *Order) int64 { return o.Amount + int64(len(o.ID)) + int64(o.Tags[3]) }

func main() {
	live, seconds := 1_000_000, 10.0
	if len(os.Args) > 1 {
		live, _ = strconv.Atoi(os.Args[1])
	}
	if len(os.Args) > 2 {
		seconds, _ = strconv.ParseFloat(os.Args[2], 64)
	}
	b0 := now()
	set := make([]*Order, live)
	for i := range set {
		set[i] = newOrder(i, int64(i)*3)
	}
	buildMs := float64(now()-b0) / 1e6
	runtime.GC()
	var m0, m1 runtime.MemStats
	runtime.ReadMemStats(&m0)
	rng := rand.New(rand.NewSource(42))
	lat := make([]int64, 0, 1<<20)
	var sink int64
	next := live
	end := now() + int64(seconds*1e9)
	for {
		t := now()
		if t >= end {
			break
		}
		for k := 0; k < 200; k++ {
			sink += use(newOrder(next+k, int64(k)))
		}
		for k := 0; k < 20; k++ {
			set[rng.Intn(live)] = newOrder(next, int64(k))
			next++
		}
		lat = append(lat, now()-t)
	}
	runtime.ReadMemStats(&m1)
	us := make([]float64, len(lat))
	var total float64
	for i, v := range lat {
		us[i] = float64(v) / 1e3
		total += us[i]
	}
	sort.Float64s(us)
	p := func(q float64) float64 { return us[int(q*float64(len(us)-1))] }
	over := func(lim float64) int {
		n := 0
		for _, v := range us {
			if v > lim {
				n++
			}
		}
		return n
	}
	var maxPause uint64
	for _, v := range m1.PauseNs {
		if v > maxPause {
			maxPause = v
		}
	}
	json.NewEncoder(os.Stdout).Encode(map[string]any{
		"iterations": len(us), "iter_per_s": float64(len(us)) / (total / 1e6), "p50_us": p(.5), "p99_us": p(.99), "p999_us": p(.999), "max_us": us[len(us)-1],
		"over_1ms": over(1000), "over_10ms": over(10000), "build_ms": buildMs, "sink": (sink + set[live/2].Amount) % 1000,
		"gc_cycles": m1.NumGC - m0.NumGC, "gc_pause_ms": float64(m1.PauseTotalNs-m0.PauseTotalNs) / 1e6, "gc_max_stw_ms": float64(maxPause) / 1e6,
		"heap_mb": float64(m1.HeapAlloc) / 1048576, "runtime": runtime.Version(),
	})
}
