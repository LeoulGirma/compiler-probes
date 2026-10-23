// In-network load generator for the production-shaped payment services. Go standard library only.
//
//	-mode open   -rate 1000 -dur 60s     fixed request rate; latency counted from each request's scheduled time
//	-mode closed -conns 128 -dur 30s     as fast as the service answers
//	-mode wait                            poll until /health and then one /pay succeed; print both times (unix ns)
//
// Every request carries an HS256 JWT for its merchant and a unique payment id; -dupe resends an earlier id
// (an idempotent replay) and -invalid sends a body whose items do not add up (422). Prints one JSON object with
// totals, latency percentiles, status counts and, with -series, a per-second time line.
package main

import (
	"bufio"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"math/rand/v2"
	"net"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

var (
	addr    = flag.String("addr", "svc:8080", "")
	modeF   = flag.String("mode", "open", "open | closed | wait")
	rate    = flag.Float64("rate", 1000, "")
	conns   = flag.Int("conns", 512, "")
	dur     = flag.Duration("dur", 30*time.Second, "")
	warm    = flag.Duration("warm", 5*time.Second, "")
	secret  = flag.String("secret", "probes-test-jwt-secret-0123456789abcdef", "")
	runID   = flag.String("run", strconv.FormatInt(time.Now().UnixNano()%1e9, 36), "id prefix, unique per run")
	timeout = flag.Duration("timeout", 5*time.Second, "client gives up after this")
	dupe    = flag.Float64("dupe", 0.01, "")
	invalid = flag.Int("invalid", 50, "every Nth payment is invalid")
	series  = flag.Bool("series", false, "")
)

var tokens [256]string

func makeTokens() {
	b64 := base64.RawURLEncoding
	h := b64.EncodeToString([]byte(`{"alg":"HS256","typ":"JWT"}`))
	exp := time.Now().Add(24 * time.Hour).Unix()
	for i := range tokens {
		p := b64.EncodeToString([]byte(fmt.Sprintf(`{"sub":"M%04d","iss":"probes-test","aud":"payments","exp":%d}`, i, exp)))
		mac := hmac.New(sha256.New, []byte(*secret))
		mac.Write([]byte(h + "." + p))
		tokens[i] = h + "." + p + "." + b64.EncodeToString(mac.Sum(nil))
	}
}

// request bytes for payment number n (deterministic, so a duplicate resends exactly the same body)
func request(n int64) []byte {
	i := int(n)
	m := i % 256
	q1, q2, p1, p2 := int64(1+i%3), int64(1+i%2), int64(1000+(i%50)*25), int64(500+(i%20)*10)
	amount := q1*p1 + q2*p2
	if *invalid > 0 && i%*invalid == *invalid-1 {
		amount++
	}
	body := fmt.Sprintf(`{"id":"tx-%s-%09d","merchant":"M%04d","amount":%d,"currency":"ETB","payer":{"msisdn":"2519%08d","name":"Customer %d"},`+
		`"items":[{"sku":"SKU-%03d","qty":%d,"price":%d},{"sku":"SKU-%03d","qty":%d,"price":%d}],"note":"order %d"}`,
		*runID, n, m, amount, 10000000+i%9999999, i, i%97, q1, p1, (i+13)%97, q2, p2, i)
	return []byte(fmt.Sprintf("POST /pay HTTP/1.1\r\nHost: svc\r\nAuthorization: Bearer %s\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n%s",
		tokens[m], len(body), body))
}

func readResponse(r *bufio.Reader) (int, error) {
	line, err := r.ReadString('\n')
	if err != nil {
		return 0, err
	}
	if len(line) < 12 {
		return 0, fmt.Errorf("short status line")
	}
	code, _ := strconv.Atoi(line[9:12])
	clen, chunked, closeConn := -1, false, false
	for {
		h, err := r.ReadString('\n')
		if err != nil {
			return 0, err
		}
		if h == "\r\n" {
			break
		}
		if i := strings.IndexByte(h, ':'); i > 0 {
			k, v := strings.ToLower(h[:i]), strings.TrimSpace(h[i+1:])
			switch k {
			case "content-length":
				clen, _ = strconv.Atoi(v)
			case "transfer-encoding":
				chunked = strings.Contains(strings.ToLower(v), "chunked")
			case "connection":
				closeConn = strings.EqualFold(v, "close")
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
				break
			}
		}
	} else if clen > 0 {
		if _, err := r.Discard(clen); err != nil {
			return 0, err
		}
	}
	if closeConn {
		return code, errClose
	}
	return code, nil
}

var errClose = fmt.Errorf("server closed connection")

type sample struct {
	due  int64 // ns since measuring started
	lat  int64
	code int // 0 = client timeout / connection error
}

type conn struct {
	c  net.Conn
	br *bufio.Reader
}

func (k *conn) do(req []byte) (int, error) {
	if k.c == nil {
		c, err := net.DialTimeout("tcp", *addr, 2*time.Second)
		if err != nil {
			return 0, err
		}
		k.c, k.br = c, bufio.NewReaderSize(c, 16<<10)
	}
	k.c.SetDeadline(time.Now().Add(*timeout))
	if _, err := k.c.Write(req); err != nil {
		k.c.Close()
		k.c = nil
		return 0, err
	}
	code, err := readResponse(k.br)
	if err != nil {
		k.c.Close()
		k.c = nil
		if err == errClose {
			return code, nil
		}
		return 0, err
	}
	return code, nil
}

func waitMode() {
	k := &conn{}
	for {
		c, err := net.DialTimeout("tcp", *addr, 200*time.Millisecond)
		if err == nil {
			c.SetDeadline(time.Now().Add(time.Second))
			fmt.Fprintf(c, "GET /health HTTP/1.1\r\nHost: svc\r\nConnection: close\r\n\r\n")
			line, _ := bufio.NewReader(c).ReadString('\n')
			c.Close()
			if strings.Contains(line, " 200 ") {
				break
			}
		}
		time.Sleep(2 * time.Millisecond)
	}
	health := time.Now().UnixNano()
	for n := int64(0); ; n++ {
		if code, _ := k.do(request(n)); code == 200 {
			break
		}
		time.Sleep(2 * time.Millisecond)
	}
	json.NewEncoder(os.Stdout).Encode(map[string]int64{"health_unix_ns": health, "first_pay_unix_ns": time.Now().UnixNano()})
}

func main() {
	flag.Parse()
	makeTokens()
	if *modeF == "wait" {
		waitMode()
		return
	}
	open := *modeF == "open"
	var seq atomic.Int64
	var stop atomic.Bool
	slots := make(chan int64, 1<<20)
	start := time.Now().Add(100 * time.Millisecond)
	measureFrom := start.Add(*warm)
	end := measureFrom.Add(*dur)
	results := make([][]sample, *conns)
	var wg sync.WaitGroup
	if open {
		interval := time.Duration(float64(time.Second) / *rate)
		go func() {
			for k := int64(0); ; k++ {
				t := start.Add(time.Duration(k) * interval)
				if t.After(end) {
					close(slots)
					return
				}
				for time.Now().Before(t) {
					if d := time.Until(t); d > 2*time.Millisecond {
						time.Sleep(d - time.Millisecond)
					}
				}
				slots <- t.UnixNano()
			}
		}()
	}
	for w := 0; w < *conns; w++ {
		wg.Add(1)
		go func(w int) {
			defer wg.Done()
			k := &conn{}
			rng := rand.New(rand.NewPCG(uint64(w), 7))
			for !stop.Load() {
				var due int64
				if open {
					t, ok := <-slots
					if !ok {
						return
					}
					due = t
				} else {
					due = time.Now().UnixNano()
					if due > end.UnixNano() {
						return
					}
				}
				n := seq.Add(1) - 1
				if n > 2000 && rng.Float64() < *dupe {
					n = n - 1000 - int64(rng.IntN(500)) // replay an earlier payment
				}
				code, err := k.do(request(n))
				if err != nil {
					code = 0
				}
				done := time.Now().UnixNano()
				if due >= measureFrom.UnixNano() {
					results[w] = append(results[w], sample{due - measureFrom.UnixNano(), done - due, code})
				}
			}
		}(w)
	}
	if !open {
		time.Sleep(time.Until(end))
		stop.Store(true)
	}
	wg.Wait()

	var all []sample
	for _, r := range results {
		all = append(all, r...)
	}
	codes := map[string]int{}
	lat := make([]int64, 0, len(all))
	for _, s := range all {
		codes[strconv.Itoa(s.code)]++
		lat = append(lat, s.lat)
	}
	out := map[string]any{"mode": *modeF, "rate": *rate, "conns": *conns, "requests": len(all),
		"rps": float64(len(all)) / dur.Seconds(), "codes": codes}
	for k, v := range pcts(lat) {
		out[k] = v
	}
	// latency of answered payments only (200 and 422): injected provider failures all take exactly the timeout,
	// so they would pin the overall p99 to that number
	okLat := make([]int64, 0, len(all))
	for _, s := range all {
		if s.code == 200 || s.code == 422 {
			okLat = append(okLat, s.lat)
		}
	}
	for k, v := range pcts(okLat) {
		out["ok_"+k] = v
	}
	good := 0
	for _, s := range all {
		if s.code == 200 || s.code == 422 {
			good++
		}
	}
	out["good_rps"] = float64(good) / dur.Seconds()
	if *series {
		secs := int(dur.Seconds()) + 1
		buckets := make([][]sample, secs)
		for _, s := range all {
			i := int(s.due / 1e9)
			if i >= 0 && i < secs {
				buckets[i] = append(buckets[i], s)
			}
		}
		var tl []map[string]any
		for i, b := range buckets {
			l := make([]int64, 0, len(b))
			errs, ok := 0, 0
			for _, s := range b {
				l = append(l, s.lat)
				if s.code == 200 || s.code == 422 {
					ok++
				} else if s.code == 0 || s.code >= 500 {
					errs++
				}
			}
			p := pcts(l)
			tl = append(tl, map[string]any{"t": i, "n": len(b), "ok": ok, "errors": errs, "p50_ms": p["p50_ms"], "p99_ms": p["p99_ms"]})
		}
		out["series"] = tl
	}
	json.NewEncoder(os.Stdout).Encode(out)
}

func pcts(l []int64) map[string]float64 {
	if len(l) == 0 {
		return map[string]float64{"p50_ms": 0, "p90_ms": 0, "p99_ms": 0, "p999_ms": 0, "max_ms": 0}
	}
	sort.Slice(l, func(a, b int) bool { return l[a] < l[b] })
	p := func(q float64) float64 { return float64(l[int(q*float64(len(l)-1))]) / 1e6 }
	return map[string]float64{"p50_ms": p(.5), "p90_ms": p(.9), "p99_ms": p(.99), "p999_ms": p(.999), "max_ms": p(1)}
}
