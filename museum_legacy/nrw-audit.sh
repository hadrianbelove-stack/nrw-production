# nrw-audit.sh — B→C→A audit with strict determinism
#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C TZ=UTC PYTHONHASHSEED=0

REPO="${REPO:-$HOME/Downloads/new-release-wall}"
cd "$REPO"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUTDIR="output"
OUT="${OUTDIR}/nrw_audit_${STAMP}"
mkdir -p "${OUTDIR}"
: > "${OUT}.txt"

pass(){ echo "PASS  $1" | tee -a "${OUT}.txt"; }
fail(){ echo "FAIL  $1" | tee -a "${OUT}.txt"; exit 2; }
note(){ echo "NOTE  $1" | tee -a "${OUT}.txt"; }

# 0) Context
MODE="unknown"
grep -qiE '^offline:\s*true' config.yaml 2>/dev/null && MODE="offline"
[[ "${NRW_OFFLINE:-}" == "1" ]] && MODE="offline"
[[ "${MODE}" == "unknown" ]] && MODE="online-or-mixed"
note "Mode detected: ${MODE}"

# 1) Preflight
[[ -d .venv ]] && . .venv/bin/activate || note ".venv not found, using system Python"
for f in generate_from_tracker.py generate_site.py; do
  [[ -f "$f" ]] || fail "Missing ${f}"
done
python3 - <<'PY' || fail "Missing Python deps (requests,jinja2,yaml)"
import importlib
for m in ("requests","jinja2","yaml"): importlib.import_module(m)
PY
command -v jq >/dev/null 2>&1 || note "jq not found; Python fallback will be used"
pass "Preflight"

# 2) Pipeline (B) — deterministic site build
note "B: generator → site (first build)"
python3 generate_from_tracker.py 14 >/dev/null
python3 generate_site.py         >/dev/null

H1="$(shasum -a 256 output/data.json 2>/dev/null | awk '{print $1}')"
H1C="$(test -f output/data_core.json && shasum -a 256 output/data_core.json | awk '{print $1}' || echo 'NA')"
H1I="$(shasum -a 256 output/site/index.html | awk '{print $1}')"
[[ -n "${H1}" && -n "${H1I}" ]] || fail "Missing outputs after first build"

note "B: site build (second build, no generator)"
python3 generate_site.py >/dev/null

H2="$(shasum -a 256 output/data.json 2>/dev/null | awk '{print $1}')"
H2C="$(test -f output/data_core.json && shasum -a 256 output/data_core.json | awk '{print $1}' || echo 'NA')"
H2I="$(shasum -a 256 output/site/index.html | awk '{print $1}')"

if [[ "${H1}" == "${H2}" && "${H1I}" == "${H2I}" ]]; then
  pass "B: deterministic outputs (data.json,index.html)"
else
  fail "B: non-deterministic outputs (hash mismatch)"
fi
echo "HASHES data.json:${H1}→${H2}  data_core.json:${H1C}→${H2C}  index.html:${H1I}→${H2I}" | tee -a "${OUT}.txt"

# Size sanity
stat_bytes(){ python3 - "$1" <<'PY'
import os,sys; p=sys.argv[1]; print(os.path.getsize(p) if os.path.exists(p) else 0)
PY
}
DATA_SZ=$(stat_bytes output/data.json)
CORE_SZ=$(stat_bytes output/data_core.json)
IDX_SZ=$(stat_bytes output/site/index.html)
echo "SIZES data.json=${DATA_SZ}  data_core.json=${CORE_SZ}  index.html=${IDX_SZ}" | tee -a "${OUT}.txt"
[[ "${DATA_SZ}" -le $((2*1024*1024)) ]] || fail "B: data.json too large (>2MB)"
[[ "${IDX_SZ}"  -le $((1*1024*1024)) ]] || fail "B: index.html too large (>1MB)"
pass "B: size sanity"

# 3) Data (C) — dups, schema, dates
python3 - <<'PY' > /tmp/nrw_data_audit.json
import json, os
def load(p):
  if not os.path.exists(p): return []
  d=json.load(open(p,'r',encoding='utf-8'))
  return d if isinstance(d,list) else d.get("items",[]) if isinstance(d,dict) else []
items = load("output/data.json")
seen=set(); dups=0; bad_dates=0; miss=[]

def year_ok(y):
  try: y=int(str(y)[:4]); return 1900<=y<=2100
  except: return False

for x in items:
  tid=str(x.get("tmdb_id") or x.get("id") or "")
  k=(tid, x.get("title",""), str(x.get("year") or x.get("release_year") or ""))
  if k in seen: dups+=1
  else: seen.add(k)
  req=("title","providers")
  missing=[r for r in req if (r not in x) or (x.get(r) in (None,"",[]))]
  if missing: miss.append({"id":tid,"missing":missing})
  y=x.get("year") or x.get("release_year")
  if y and not year_ok(y): bad_dates+=1

print(json.dumps({"items":len(items),"dups":dups,"bad_dates":bad_dates,"missing_fields":miss[:10]}, ensure_ascii=False))
PY

ITEMS=$(python3 -c 'import json;print(json.load(open("/tmp/nrw_data_audit.json"))["items"])')
DUPS=$(python3 -c 'import json;print(json.load(open("/tmp/nrw_data_audit.json"))["dups"])')
BADS=$(python3 -c 'import json;print(json.load(open("/tmp/nrw_data_audit.json"))["bad_dates"])')

[[ "${DUPS}" -eq 0 && "${BADS}" -eq 0 ]] \
  && pass "C: no duplicates and dates sane (items=${ITEMS})" \
  || fail "C: issues found (see /tmp/nrw_data_audit.json)"

# 4) Frontend (A) — no server loops, guard, fetch path
grep -q '{%[[:space:]]*for[[:space:]]' output/site/index.html 2>/dev/null \
  && fail "A: server-side Jinja loop still present in index.html" || pass "A: no server loops in index.html"

if [[ -f render_approved.js ]]; then
  grep -q 'window.__NRW_RENDERED__' render_approved.js \
    && pass "A: global render guard present" \
    || note "A: add window.__NRW_RENDERED__ guard"
  grep -Eo "fetch\(['\"][^'\"]+['\"]\)" render_approved.js | grep -q "output/data.json" \
    && pass "A: data fetch path is relative to output/data.json" \
    || note "A: verify data fetch path uses relative URL"
else
  note "A: render_approved.js not found; verify JS entry manually"
fi

# 5) Summary + log
STATUS="PASS"; grep -q '^FAIL' "${OUT}.txt" && STATUS="FAIL"
{
  echo "- ${STAMP}: Audit ${STATUS}"
  echo "  Mode: ${MODE}"
  echo "  Determinism: $(grep -q 'B: deterministic outputs' ${OUT}.txt && echo OK || echo FAIL)"
  echo "  Sizes: data.json=${DATA_SZ}, data_core.json=${CORE_SZ}, index.html=${IDX_SZ}"
  echo "  Data: items=${ITEMS}; dups=${DUPS}; bad_dates=${BADS}"
  echo "  Report: ${OUT}.txt"
} >> PROJECT_LOG.md || true

echo "==== AUDIT ${STATUS} ===="
cat "${OUT}.txt"
[[ "${STATUS}" == "PASS" ]]