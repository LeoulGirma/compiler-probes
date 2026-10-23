// Load generator for the payment services. Raw HTTP/1.1 over keep-alive TCP connections (no client library overhead).
//
//	loadgen -addr 127.0.0.1:8080 -conns 64 -dur 10s              closed loop: as fast as the server answers (max throughput)
//	loadgen -addr 127.0.0.1:8080 -conns 64 -dur 10s -rate 20000  open loop: fixed request rate; latency is measured from the
//	                                                              time each request was scheduled, so server stalls are not hidden
//
// Prints one JSON object: rps, latency percentiles (µs), status counts, errors.
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"net"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

func makeBodies(n int, invalidEvery int) [][]byte {
	out := make([][]byte, n)
	for i := 0; i < n; i++ {
		q1, q2, p1, p2 := int64(1+i%3), int64(1+i%2), int64(1000+(i%50)*25), int64(500+(i%20)*10)
		amount := q1*p1 + q2*p2
		if invalidEvery > 0 && i%invalidEvery == invalidEvery-1 {
			amount++ // fails the sum check -> 422
		}
		body := fmt.Sprintf(`{"id":"tx-%07d","merchant":"M%04d","amount":%d,"currency":"%s","payer":{"msisdn":"2519%08d","name":"Customer %d"},`+
			`"items":[{"sku":"SKU-%03d","qty":%d,"price":%d},{"sku":"SKU-%03d","qty":%d,"price":%d}],"note":"order %d from the load generator"}`,
			i, i%256, amount, []string{"ETB", "USD"}[i%7/6], 10000000+i, i, i%97, q1, p1, (i+13)%97, q2, p2, i)
		out[i] = []byte(fmt.Sprintf("POST /pay HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n%s", len(body), body))
	}
	return out
}

// readResponse reads one HTTP/1.1 response (Content-Length or chunked) and returns its status code.
func readResponse(r *bufio.Reader) (int, error) {
	line, err := r.ReadString('\n')
	if err != nil {
		return 0, err
	}
	if len(line) < 12 {
		return 0, fmt.Errorf("short status line %q", line)
	}
	code, _ := strconv.Atoi(line[9:12])
	clen, chunked := -1, false
	for {
		h, err := r.ReadString('\n')
		if err != nil {
			return 0, err
		}
		if h == "\r\n" {
			break
		}
		if i := strings.IndexByte(h, ':'); i > 0 {
			k := strings.ToLower(h[:i])
			v := strings.TrimSpace(h[i+1:])
			if k == "content-length" {
				clen, _ = strconv.Atoi(v)
			} else if k == "transfer-encoding" && strings.Contains(strings.ToLower(v), "chunked") {
				chunked = true
			}
		}
	}
	if chunked {
		for {
			sz, err := r.ReadString('\n')
			if err != nil {
				return 0, err
			}
			n, _ := strconv.ParseInt(strings.TrimSpace(strings.SplitN(sz, ";", 2)[0]), 16, 64)
			if _, err := r.Discard(int(n) + 2); err != nil {
				return 0, err
			}
			if n == 0 {
				return code, nil
			}
		}
	}
	if clen > 0 {
		if _, err := r.Discard(clen); err != nil {
			return 0, err
		}
	}
	return code, nil
}

type worker struct {
	lat    []int64
	lag    []int64
	codes  map[int]int
	errors int
}

func main() {
	addr := flag.String("addr", "127.0.0.1:8080", "")
	conns := flag.Int("conns", 64, "")
	dur := flag.Duration("dur", 10*time.Second, "")
	warm := flag.Duration("warm", 2*time.Second, "")
	rate := flag.Float64("rate", 0, "requests/s; 0 = closed loop")
	flag.Parse()
	reqs := makeBodies(1024, 50)

	var stop atomic.Bool
	var measuring atomic.Bool
	workers := make([]*worker, *conns)
	var wg sync.WaitGroup
	var start int64 // qpc ns when measuring starts (open loop schedule origin)
	interval := int64(0)
	if *rate > 0 {
		interval = int64(1e9 / *rate)
	}
	ready := make(chan struct{})
	slots := make(chan int64, 1<<20)
	start = now() + int64(50*time.Millisecond)
	for c := 0; c < *conns; c++ {
		w := &worker{codes: map[int]int{}, lat: make([]int64, 0, 1<<16)}
		workers[c] = w
		wg.Add(1)
		go func(c int, w *worker) {
			defer wg.Done()
			conn, err := net.Dial("tcp", *addr)
			if err != nil {
				w.errors++
				return
			}
			defer conn.Close()
			br := bufio.NewReaderSize(conn, 16<<10)
			<-ready
			i := c
			for !stop.Load() {
				var t0 int64
				if interval > 0 {
					var ok bool
					if t0, ok = <-slots; !ok { // parked until the pacer releases this request's scheduled time
						return
					}
				} else {
					t0 = now()
				}
				if _, err := conn.Write(reqs[i%len(reqs)]); err != nil {
					w.errors++
					return
				}
				sent := now()
				code, err := readResponse(br)
				if err != nil {
					w.errors++
					return
				}
				if measuring.Load() {
					w.lat = append(w.lat, now()-t0)
					w.lag = append(w.lag, sent-t0) // how late the client sent it (open loop); ~0 in closed loop
					w.codes[code]++
				}
				i += *conns
			}
		}(c, w)
	}
	// open loop: one pacer goroutine releases each request at its scheduled time. Workers stay parked on the channel,
	// so the Go scheduler keeps polling the network promptly (spinning workers would delay responses by up to 10 ms),
	// and a request that waits because every connection is busy still counts from its scheduled time.
	if interval > 0 {
		go func() {
			for k := int64(0); !stop.Load(); k++ {
				t := start + k*interval
				for now() < t {
				}
				slots <- t
			}
			close(slots)
		}()
	}
	// warm up, then measure
	close(ready)
	if *rate > 0 { // open loop: the schedule runs through warm-up too; restart it at the measuring point
		time.Sleep(*warm)
		measuring.Store(true)
	} else {
		time.Sleep(*warm)
		measuring.Store(true)
	}
	m0 := now()
	time.Sleep(*dur)
	measuring.Store(false)
	m1 := now()
	stop.Store(true)
	wg.Wait()

	var all, lags []int64
	codes := map[string]int{}
	errs := 0
	for _, w := range workers {
		all = append(all, w.lat...)
		lags = append(lags, w.lag...)
		for k, v := range w.codes {
			codes[strconv.Itoa(k)] += v
		}
		errs += w.errors
	}
	sort.Slice(all, func(a, b int) bool { return all[a] < all[b] })
	sort.Slice(lags, func(a, b int) bool { return lags[a] < lags[b] })
	lagp := func(p float64) float64 {
		if len(lags) == 0 {
			return 0
		}
		return float64(lags[int(p*float64(len(lags)-1))]) / 1e3
	}
	pct := func(p float64) float64 {
		if len(all) == 0 {
			return 0
		}
		i := int(p * float64(len(all)-1))
		return float64(all[i]) / 1e3
	}
	secs := float64(m1-m0) / 1e9
	out := map[string]any{
		"mode": map[bool]string{true: "open", false: "closed"}[*rate > 0], "target_rps": *rate, "conns": *conns,
		"requests": len(all), "rps": float64(len(all)) / secs,
		"p50_us": pct(0.50), "p90_us": pct(0.90), "p99_us": pct(0.99), "p999_us": pct(0.999), "max_us": pct(1.0),
		"codes": codes, "errors": errs, "send_lag_p50_us": lagp(0.5), "send_lag_p99_us": lagp(0.99),
	}
	json.NewEncoder(os.Stdout).Encode(out)
}
