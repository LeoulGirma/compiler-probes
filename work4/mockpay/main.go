// Mock payment provider. POST /charge waits a lognormal delay (median MEDIAN_MS, spread SIGMA) and returns a reference;
// a FAIL fraction of calls hangs for 3 s and then answers 503, so callers with a sane timeout see a timeout.
// POST /mode?median=300&sigma=0.8&fail=0.1 changes behaviour at run time (used for the degradation scenario).
package main

import (
	"encoding/json"
	"log"
	"math"
	"math/rand/v2"
	"net/http"
	"os"
	"strconv"
	"sync/atomic"
	"time"
)

type mode struct{ median, sigma, fail float64 }

var cur atomic.Pointer[mode]
var calls atomic.Int64

func envf(k string, d float64) float64 {
	if v, err := strconv.ParseFloat(os.Getenv(k), 64); err == nil {
		return v
	}
	return d
}

func main() {
	cur.Store(&mode{envf("MEDIAN_MS", 30), envf("SIGMA", 0.6), envf("FAIL", 0.01)})
	http.HandleFunc("POST /charge", func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			ID     string `json:"id"`
			Amount int64  `json:"amount"`
		}
		json.NewDecoder(r.Body).Decode(&req)
		calls.Add(1)
		m := cur.Load()
		if rand.Float64() < m.fail {
			time.Sleep(3 * time.Second)
			http.Error(w, `{"error":"unavailable"}`, http.StatusServiceUnavailable)
			return
		}
		d := m.median * math.Exp(m.sigma*rand.NormFloat64())
		time.Sleep(time.Duration(d * float64(time.Millisecond)))
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"ref":"pr-` + req.ID + `","status":"ok"}`))
	})
	http.HandleFunc("POST /mode", func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		m := *cur.Load()
		if v, err := strconv.ParseFloat(q.Get("median"), 64); err == nil {
			m.median = v
		}
		if v, err := strconv.ParseFloat(q.Get("sigma"), 64); err == nil {
			m.sigma = v
		}
		if v, err := strconv.ParseFloat(q.Get("fail"), 64); err == nil {
			m.fail = v
		}
		cur.Store(&m)
		json.NewEncoder(w).Encode(map[string]float64{"median": m.median, "sigma": m.sigma, "fail": m.fail})
	})
	http.HandleFunc("GET /stats", func(w http.ResponseWriter, _ *http.Request) {
		json.NewEncoder(w).Encode(map[string]int64{"calls": calls.Load()})
	})
	log.Fatal(http.ListenAndServe(":9000", nil))
}
