// Payment-style HTTP service — Go (net/http + encoding/json). Same contract as cs/Program.cs and rust/src/main.rs.
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"os"
	"strconv"
	"sync"
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
	Signature     string `json:"signature"`
	MerchantCount int64  `json:"merchantCount"`
	MerchantTotal int64  `json:"merchantTotal"`
}
type PayRejected struct {
	ID     string `json:"id"`
	Status string `json:"status"`
	Reason string `json:"reason"`
}

type entry struct{ count, total int64 }
type shard struct {
	mu sync.Mutex
	m  map[string]entry
}

var shards [64]shard
var key = []byte("probes-demo-signing-key-0123456789")

func fnv(s string) uint32 {
	h := uint32(2166136261)
	for _, c := range s { // UTF-16 code units in C#; inputs are ASCII so runes == code units
		h = (h ^ uint32(c)) * 16777619
	}
	return h
}

func record(merchant string, amount int64) entry {
	s := &shards[fnv(merchant)%64]
	s.mu.Lock()
	e := s.m[merchant]
	e.count++
	e.total += amount
	s.m[merchant] = e
	s.mu.Unlock()
	return e
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

func pay(w http.ResponseWriter, req *http.Request) {
	var r PayRequest
	if err := json.NewDecoder(req.Body).Decode(&r); err != nil {
		http.Error(w, "bad json", http.StatusBadRequest)
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	if reason := validate(&r); reason != "" {
		w.WriteHeader(http.StatusUnprocessableEntity)
		json.NewEncoder(w).Encode(PayRejected{r.ID, "rejected", reason})
		return
	}
	mac := hmac.New(sha256.New, key)
	mac.Write([]byte(r.ID + "|" + r.Merchant + "|" + strconv.FormatInt(r.Amount, 10) + "|" + r.Currency))
	sig := hex.EncodeToString(mac.Sum(nil))
	e := record(r.Merchant, r.Amount)
	json.NewEncoder(w).Encode(PayResponse{r.ID, "accepted", sig, e.count, e.total})
}

func main() {
	for i := range shards {
		shards[i].m = map[string]entry{}
	}
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	mux.HandleFunc("POST /pay", pay)
	if err := http.ListenAndServe("127.0.0.1:"+port, mux); err != nil {
		panic(err)
	}
}
