//go:build !windows

package main

import "time"

var t0 = time.Now()

func now() int64 { return int64(time.Since(t0)) }
