#!/usr/bin/env bash
# Set 4 warm-up follow-up on a Linux server: is .NET 11's rougher first minutes under load (JIT only) caused by
# dynamic PGO or by tiered compilation? Two 5-minute soaks at 250 payments/s of .NET 10, .NET 11, .NET 11 with
# DOTNET_TieredPGO=0 and .NET 11 with DOTNET_TieredCompilation=0, the order reversed in the second soak.
# Pauses every other running container (except names matching KEEP) and resumes them on exit.
# Usage: setsid nohup bash set4_warmup.sh > ~/bench/set4w.log 2>&1 < /dev/null &
B=$HOME/bench; OUT=$HOME/bench-results/set4w; KEEP='^(suq-|caddy$)'
mkdir -p $B $OUT; cd $B
log() { echo "== $(date -u +%H:%M:%S) $*"; }
PAUSED=0; WD=
cleanup() {
  [ -n "$WD" ] && kill $WD 2>/dev/null
  if [ -d $B/compiler-probes/work4 ]; then
    cd $B/compiler-probes/work4 && docker compose -f compose.yml --profile svc down -v >/dev/null 2>&1
    cp r4_w*.json $OUT/ 2>/dev/null
  fi
  cp $B/*.log $OUT/ 2>/dev/null
  [ $PAUSED = 1 ] && docker unpause $(cat $B/paused.txt) >/dev/null 2>&1 && log "unpaused $(wc -l < $B/paused.txt) containers"
  log "cleanup done, $(df -h / | awk 'NR==2{print $4}') free"
}
trap cleanup EXIT
guard() {
  while sleep 15; do
    d=$(df -m / | awk 'NR==2{print $4}'); m=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
    if [ "$d" -lt 2048 ] || [ "$m" -lt 400 ]; then
      log "GUARD: disk ${d} MB, memory ${m} MB: aborting"; pkill -f 'run4.py|build4.py'; kill -TERM $$; exit
    fi
  done
}
guard & WD=$!

log "phase A: toolchains ($(df -h / | awk 'NR==2{print $4}') free)"
export DOTNET_LOCAL=$B/dotnet NUGET_PACKAGES=$B/nuget DOTNET_CLI_HOME=$B/dotnethome DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
wget -qO $B/dotnet-install.sh https://dot.net/v1/dotnet-install.sh
for v in 10.0.401 11.0.100; do bash $B/dotnet-install.sh --version $v --install-dir $DOTNET_LOCAL >/dev/null || exit 1; done
export GOPATH=$B/gopath GOMODCACHE=$B/gopath/pkg/mod GOCACHE=$B/gocache GOTOOLCHAIN=go1.27.2
if ! command -v go >/dev/null; then
  wget -qO- https://go.dev/dl/go1.27.2.linux-amd64.tar.gz | tar -xz -C $B && export PATH=$B/go/bin:$PATH
fi
git clone -q --depth 1 https://github.com/LeoulGirma/compiler-probes.git || exit 1
cd compiler-probes/work4
python3 build4.py go cs > $B/build.log 2>&1 || { tail -20 $B/build.log; exit 1; }
docker pull -q postgres:17-alpine >/dev/null
docker compose -f compose.yml --profile svc build cs10 cs11 mockpay loadgen > $B/images.log 2>&1 || { tail -30 $B/images.log; exit 1; }
docker builder prune -af >/dev/null 2>&1
log "built: $(df -h / | awk 'NR==2{print $4}') free"

log "phase B: pause other containers"
docker ps --format '{{.Names}}' | grep -Ev "$KEEP" > $B/paused.txt
[ -s $B/paused.txt ] && docker pause $(cat $B/paused.txt) >/dev/null && PAUSED=1
log "paused $(wc -l < $B/paused.txt) containers"
sleep 20
python3 run4.py up || exit 1
log "soak A"
python3 run4.py soak --minutes 5 --rate 250 --keep-order --only cs10,cs11,cs11pgo0,cs11tc0 --tag _wA
log "soak B (reversed)"
python3 run4.py soak --minutes 5 --rate 250 --keep-order --only cs11tc0,cs11pgo0,cs11,cs10 --tag _wB
log "ALL DONE"
