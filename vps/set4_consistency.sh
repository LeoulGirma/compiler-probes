#!/usr/bin/env bash
# Set 4 consistency run on a Linux server (.NET 10.0.x vs 11.0.0, Go, Rust), 250 payments/s:
#   3 rounds of every service (order rotates each round), then two 8-minute soaks of the JIT builds with the
#   order flipped between them. Every measurement records CPU-quota throttling and host CPU steal.
# Pauses every other running container for the duration (except names matching KEEP) and resumes them on exit.
# Usage: setsid nohup bash set4_consistency.sh > ~/bench/set4c.log 2>&1 < /dev/null &
B=$HOME/bench; OUT=$HOME/bench-results/set4c; KEEP='^(suq-|caddy$)'
mkdir -p $B $OUT; cd $B
log() { echo "== $(date -u +%H:%M:%S) $*"; }
PAUSED=0; WD=
cleanup() {
  [ -n "$WD" ] && kill $WD 2>/dev/null
  if [ -d $B/compiler-probes/work4 ]; then
    cd $B/compiler-probes/work4 && docker compose -f compose.yml --profile svc down -v >/dev/null 2>&1
    cp r4_c*.json $OUT/ 2>/dev/null
  fi
  cp $B/*.log $OUT/ 2>/dev/null
  [ $PAUSED = 1 ] && docker unpause $(cat $B/paused.txt) >/dev/null 2>&1 && log "unpaused $(wc -l < $B/paused.txt) containers"
  log "cleanup done, $(df -h / | awk 'NR==2{print $4}') free"
}
trap cleanup EXIT
guard() {   # stop everything if the disk or memory runs low
  while sleep 15; do
    d=$(df -m / | awk 'NR==2{print $4}'); m=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
    if [ "$d" -lt 2048 ] || [ "$m" -lt 400 ]; then
      log "GUARD: disk ${d} MB, memory ${m} MB: aborting"; pkill -f 'run4.py|build4.py'; kill -TERM $$; exit
    fi
  done
}
guard & WD=$!

log "phase A: toolchains ($(df -h / | awk 'NR==2{print $4}') free)"
export DEBIAN_FRONTEND=noninteractive
dpkg -s build-essential >/dev/null 2>&1 || sudo -E apt-get install -y -qq build-essential >/dev/null
export DOTNET_LOCAL=$B/dotnet NUGET_PACKAGES=$B/nuget DOTNET_CLI_HOME=$B/dotnethome DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
wget -qO $B/dotnet-install.sh https://dot.net/v1/dotnet-install.sh
for v in 10.0.401 11.0.100; do bash $B/dotnet-install.sh --version $v --install-dir $DOTNET_LOCAL >/dev/null || exit 1; done
export RUSTUP_HOME=$B/rustup CARGO_HOME=$B/cargo PATH=$B/cargo/bin:$PATH
curl -sSf https://sh.rustup.rs | sh -s -- -y -q --no-modify-path --profile minimal --default-toolchain 1.99.0 >/dev/null 2>&1 || exit 1
export GOPATH=$B/gopath GOMODCACHE=$B/gopath/pkg/mod GOCACHE=$B/gocache GOTOOLCHAIN=go1.27.2
if ! command -v go >/dev/null; then
  wget -qO- https://go.dev/dl/go1.27.2.linux-amd64.tar.gz | tar -xz -C $B && export PATH=$B/go/bin:$PATH
fi
git clone -q --depth 1 https://github.com/LeoulGirma/compiler-probes.git || exit 1
cd compiler-probes/work4
python3 build4.py go rust cs > $B/build.log 2>&1 || { tail -20 $B/build.log; exit 1; }
docker pull -q postgres:17-alpine >/dev/null
docker compose -f compose.yml --profile svc build cs10 cs11 cs10aot cs11aot go rust mockpay loadgen > $B/images.log 2>&1 || { tail -30 $B/images.log; exit 1; }
docker builder prune -af >/dev/null 2>&1
log "built: $(df -h / | awk 'NR==2{print $4}') free, $(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo) MB memory available"

log "phase B: pause other containers"
docker ps --format '{{.Names}}' | grep -Ev "$KEEP" > $B/paused.txt
[ -s $B/paused.txt ] && docker pause $(cat $B/paused.txt) >/dev/null && PAUSED=1
log "paused $(wc -l < $B/paused.txt) containers; still running: $(docker ps --filter status=running --format '{{.Names}}' | tr '\n' ' ')"
sleep 20
python3 run4.py up || exit 1
for r in 1 2 3; do
  log "round $r at 250 rps"
  python3 run4.py round --round $r --rate 250 --only cs10,cs11,cs11s70,cs10aot,cs11aot,go,rust --tag _c250
done
log "soak A: .NET 10 first"
python3 run4.py soak --minutes 8 --rate 250 --keep-order --only cs10,cs11s70,cs11 --tag _cA
log "soak B: .NET 11 first"
python3 run4.py soak --minutes 8 --rate 250 --keep-order --only cs11,cs11s70,cs10 --tag _cB
log "ALL DONE"
