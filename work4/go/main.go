// Production-shaped payment service — Go (net/http, pgx pool, go-redis, golang-jwt, slog JSON logs).
// Same contract as cs/Program.cs and rust/src/main.rs.
package main

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

type Payer struct {
	Msisdn string `json:"msisdn"`
	Name   string `json:"name"`
}
type Item struct {
	Sku   string `json:"sku"`
	Qty   int32  `json:"qty"`
	Price int64  `json:"price"`
}
type PayRequest struct {
	ID       string `json:"id"`
	Merchant string `json:"merchant"`
	Amount   int64  `json:"amount"`
	Currency string `json:"currency"`
	Payer    Payer  `json:"payer"`
	Items    []Item `json:"items"`
	Note     string `json:"note"`
}
type PayResponse struct {
	ID            string `json:"id"`
	Status        string `json:"status"`
	ProviderRef   string `json:"providerRef"`
	Signature     string `json:"signature"`
	MerchantCount int64  `json:"merchantCount"`
	MerchantTotal int64  `json:"merchantTotal"`
}

var (
	db        *pgxpool.Pool
	rdb       *redis.Client
	client    *http.Client
	provider  string
	jwtKey    []byte
	parser    = jwt.NewParser(jwt.WithValidMethods([]string{"HS256"}), jwt.WithIssuer("probes-test"), jwt.WithAudience("payments"), jwt.WithExpirationRequired())
	rateLimit int64
	signKey   = []byte("probes-demo-signing-key-0123456789")
	logger    = slog.New(slog.NewJSONHandler(os.Stdout, nil))
)

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func validate(r *PayRequest) string {
	if r.Amount <= 0 {
		return "amount"
	}
	if r.Currency != "ETB" && r.Currency != "USD" {
		return "currency"
	}
	m := r.Payer.Msisdn
	if len(m) != 12 || m[:3] != "251" {
		return "msisdn"
	}
	for i := 0; i < len(m); i++ {
		if m[i] < '0' || m[i] > '9' {
			return "msisdn"
		}
	}
	if len(r.Merchant) == 0 || len(r.Merchant) > 16 {
		return "merchant"
	}
	if len(r.Items) == 0 {
		return "items"
	}
	var sum int64
	for _, it := range r.Items {
		if it.Qty <= 0 || it.Price < 0 {
			return "item"
		}
		sum += int64(it.Qty) * it.Price
	}
	if sum != r.Amount {
		return "sum"
	}
	return ""
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(v)
}
func reject(w http.ResponseWriter, code int, id, reason string) {
	writeJSON(w, code, map[string]string{"id": id, "status": "rejected", "reason": reason})
}

func pay(w http.ResponseWriter, req *http.Request) {
	t0 := time.Now()
	ctx := req.Context()
	var r PayRequest
	if err := json.NewDecoder(req.Body).Decode(&r); err != nil {
		reject(w, 400, "", "json")
		return
	}
	// 1. authenticate
	tok, err := parser.Parse(strings.TrimPrefix(req.Header.Get("Authorization"), "Bearer "), func(*jwt.Token) (any, error) { return jwtKey, nil })
	if err != nil {
		reject(w, 401, r.ID, "token")
		return
	}
	if sub, _ := tok.Claims.GetSubject(); sub != r.Merchant {
		reject(w, 403, r.ID, "merchant")
		return
	}
	// 2. rate limit
	key := "rl:" + r.Merchant + ":" + strconv.FormatInt(time.Now().Unix(), 10)
	pipe := rdb.Pipeline()
	incr := pipe.Incr(ctx, key)
	pipe.Expire(ctx, key, 5*time.Second)
	if _, err := pipe.Exec(ctx); err != nil {
		reject(w, 503, r.ID, "redis")
		return
	}
	if incr.Val() > rateLimit {
		reject(w, 429, r.ID, "rate")
		return
	}
	// 3. validate
	if reason := validate(&r); reason != "" {
		reject(w, 422, r.ID, reason)
		return
	}
	// 4. record as pending; a repeated id is an idempotent replay
	tag, err := db.Exec(ctx, `INSERT INTO payments (id, merchant, amount, currency, status) VALUES ($1, $2, $3, $4, 'pending') ON CONFLICT (id) DO NOTHING`,
		r.ID, r.Merchant, r.Amount, r.Currency)
	if err != nil {
		reject(w, 503, r.ID, "db")
		return
	}
	if tag.RowsAffected() == 0 {
		var status, pref string
		db.QueryRow(ctx, `SELECT status, coalesce(provider_ref, '') FROM payments WHERE id = $1`, r.ID).Scan(&status, &pref)
		writeJSON(w, 200, map[string]string{"id": r.ID, "status": "duplicate", "original": status, "providerRef": pref})
		return
	}
	// 5. charge with the provider
	body, _ := json.Marshal(map[string]any{"id": r.ID, "amount": r.Amount, "currency": r.Currency})
	pref := ""
	if resp, err := client.Post(provider, "application/json", bytes.NewReader(body)); err == nil {
		var pr struct {
			Ref string `json:"ref"`
		}
		if resp.StatusCode == 200 && json.NewDecoder(resp.Body).Decode(&pr) == nil {
			pref = pr.Ref
		}
		resp.Body.Close()
	}
	if pref == "" {
		db.Exec(ctx, `UPDATE payments SET status = 'failed', updated_at = now() WHERE id = $1`, r.ID)
		logger.Warn("provider failed", "id", r.ID, "merchant", r.Merchant)
		reject(w, 502, r.ID, "provider")
		return
	}
	// 6. capture + balance in one transaction
	var total, count int64
	err = pgx.BeginFunc(ctx, db, func(tx pgx.Tx) error {
		if _, err := tx.Exec(ctx, `UPDATE payments SET status = 'captured', provider_ref = $2, updated_at = now() WHERE id = $1`, r.ID, pref); err != nil {
			return err
		}
		return tx.QueryRow(ctx, `INSERT INTO balances (merchant, total, count) VALUES ($1, $2, 1) ON CONFLICT (merchant) DO UPDATE SET total = balances.total + EXCLUDED.total, count = balances.count + 1 RETURNING total, count`,
			r.Merchant, r.Amount).Scan(&total, &count)
	})
	if err != nil {
		reject(w, 503, r.ID, "db")
		return
	}
	mac := hmac.New(sha256.New, signKey)
	fmt.Fprintf(mac, "%s|%s|%d|%s", r.ID, r.Merchant, r.Amount, r.Currency)
	logger.Info("captured", "id", r.ID, "merchant", r.Merchant, "amount", r.Amount, "ms", float64(time.Since(t0).Microseconds())/1e3)
	writeJSON(w, 200, PayResponse{r.ID, "captured", pref, hex.EncodeToString(mac.Sum(nil)), count, total})
}

func main() {
	ctx := context.Background()
	cfg, err := pgxpool.ParseConfig(fmt.Sprintf("host=%s user=%s password=%s dbname=%s pool_max_conns=%s",
		env("DB_HOST", "localhost"), env("DB_USER", "pay"), env("DB_PASS", "pay"), env("DB_NAME", "pay"), env("DB_POOL", "32")))
	if err != nil {
		panic(err)
	}
	if db, err = pgxpool.NewWithConfig(ctx, cfg); err != nil {
		panic(err)
	}
	rdb = redis.NewClient(&redis.Options{Addr: env("REDIS_HOST", "localhost") + ":6379"})
	to, _ := strconv.Atoi(env("PROVIDER_TIMEOUT_MS", "1000"))
	// the default Transport keeps only 2 idle connections per host, which churns connections under load; production code raises it
	tr := http.DefaultTransport.(*http.Transport).Clone()
	tr.MaxIdleConnsPerHost = 256
	client = &http.Client{Timeout: time.Duration(to) * time.Millisecond, Transport: tr}
	provider = env("PROVIDER_URL", "http://localhost:9000/charge")
	jwtKey = []byte(env("JWT_SECRET", "probes-test-jwt-secret-0123456789abcdef"))
	rateLimit, _ = strconv.ParseInt(env("RATE_LIMIT", "100000"), 10, 64)
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	mux.HandleFunc("POST /pay", pay)
	srv := &http.Server{Addr: ":" + env("PORT", "8080"), Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	if err := srv.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		panic(err)
	}
}
