package main

import (
	"syscall"
	"unsafe"
)

// Go's own clock on Windows advances in ~0.5 ms steps; read the high-resolution performance counter instead.
var (
	k32     = syscall.NewLazyDLL("kernel32.dll")
	qpc     = k32.NewProc("QueryPerformanceCounter")
	qpf     = k32.NewProc("QueryPerformanceFrequency")
	qpcFreq int64
)

func init() { qpf.Call(uintptr(unsafe.Pointer(&qpcFreq))) }

func now() int64 {
	var c int64
	qpc.Call(uintptr(unsafe.Pointer(&c)))
	return int64(float64(c) * 1e9 / float64(qpcFreq))
}
