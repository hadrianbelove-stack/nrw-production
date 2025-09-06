#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
: "${BATCH_SIZE:=10}"         # export BATCH_SIZE=15 to change
: "${INTERVAL:=3600}"         # seconds between batches
: "${PORT:=3001}"             # dev server port

mkdir -p logs
PIDFILE=logs/hybrid_runner.pid
echo $$ > "$PIDFILE"

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" ; }

while true; do
  # 1) Recompute missing list from current data.json
  MISSING=$(jq -r '.[] | select(.rt_score==null or .rt_score=="") | .title' output/data.json | head -n "${BATCH_SIZE}" || true)
  COUNT=$(printf "%s\n" "$MISSING" | sed '/^$/d' | wc -l | tr -d ' ')
  if [ "${COUNT}" -eq 0 ]; then
    log "no missing titles. sleeping ${INTERVAL}s"
    sleep "${INTERVAL}"; continue
  fi

  log "processing ${COUNT} titles via hybrid"
  # 2) Run hybrid filler (uses generate_site.get_rt_hybrid you pasted earlier)
  python3 - <<'PY'
import json, time, pathlib, sys
from generate_site import get_rt_hybrid  # must exist
DATA = pathlib.Path("output/data.json")
d = json.loads(DATA.read_text("utf-8"))
todo = set()
for line in sys.stdin.read().splitlines():
    line=line.strip()
    if line: todo.add(line)

updated = 0
for m in d:
    if m.get("title") in todo and (m.get("rt_score") in (None,"",0)):
        rt, url, method = get_rt_hybrid(m)
        if rt is not None:
            m["rt_score"]=rt
            m["rt_method"]=method
            if url: m["rt_url"]=url
            updated += 1
        time.sleep(0.2)  # small per-item pause
DATA.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")
print(f"updated {updated}")
PY
  # feed titles to the Python block
  <<< "$MISSING" | tee -a logs/hybrid_batch_titles.log >/dev/null

  # 3) Regenerate site once after each batch
  python3 generate_site.py --enhanced || true

  # 4) Ensure single dev server on $PORT (optional)
  lsof -ti :"${PORT}" -sTCP:LISTEN | xargs -r kill
  (cd output/site && python -m http.server "${PORT}") >/dev/null 2>&1 &

  # 5) Report and sleep
  WITH_RT=$(jq -r '.[] | select(.rt_score) | .title' output/data.json | wc -l | tr -d ' ')
  log "batch done. with RT: ${WITH_RT}. sleeping ${INTERVAL}s"
  sleep "${INTERVAL}"
done