#!/usr/bin/env bash
# Frontend audit: index.html, render_approved.js, CSS
set -euo pipefail
ROOT="${ROOT:-$HOME/Downloads/new-release-wall}"
cd "$ROOT"

pass() { printf "PASS  %s\n" "$1"; }
note() { printf "NOTE  %s\n" "$1"; }
warn() { printf "WARN  %s\n" "$1"; }
fail() { printf "FAIL  %s\n" "$1"; }

HTML="output/site/index.html"
JS="output/site/assets/render_approved.js"
CSS="output/site/assets/style_overrides.css"

[[ -f "$HTML" ]] || { fail "Missing $HTML"; exit 2; }
[[ -f "$JS"   ]] || { fail "Missing $JS"; exit 2; }
[[ -f "$CSS"  ]] || note "No $CSS (ok if styles are elsewhere)"

# 1) index.html: single renderer include, relative data path present
inc_js=$(grep -nE '<script[^>]+render_approved\.js' "$HTML" | wc -l | tr -d ' ')
[[ "$inc_js" -eq 1 ]] && pass "index.html includes render_approved.js once" \
                     || warn "index.html has $inc_js includes of render_approved.js"

grep -nE 'assets/data\.json' "$HTML" >/dev/null && pass "index.html references assets/data.json (relative)" \
                                                 || note "No direct data.json ref in HTML (ok if JS fetches)"

# 2) JS: guard, relative fetch, duplicate render protection
grep -n 'window.__NRW_RENDERED__' "$JS" >/dev/null && pass "JS uses window.__NRW_RENDERED__ guard" \
                                                    || warn "Add idempotency guard window.__NRW_RENDERED__"

grep -nE "fetch\(['\"]assets/data\.json['\"]\)" "$JS" >/dev/null && pass "JS fetches via relative assets/data.json" \
                                                                   || note "Fetch path not found (may read inline data)"

# 3) JS: basic quality checks
grep -nE '\.innerHTML\s*\+=' "$JS" >/dev/null && warn "innerHTML += used (risk of reflow/XSS); prefer DOM create/append" || pass "No innerHTML += hot loop"
grep -nE 'for\s*\(.*of.*\)\s*{[^}]{0,200}for\s*\(' "$JS" >/dev/null && note "Nested loops present; check performance" || pass "No obvious nested hot loops"

# 4) CSS: card sizing & flip styles hints
if [[ -f "$CSS" ]]; then
  grep -nE 'card|flip|grid' "$CSS" >/dev/null && pass "CSS contains expected selectors (card/flip/grid)" \
                                                   || note "CSS lacks expected selectors (may live in base CSS)"
fi

# 5) Data presence quick check
DATA="output/site/assets/data.json"
if [[ -f "$DATA" ]]; then
  count=$(python3 - <<PY 2>/dev/null || true
import json,sys
try:
  d=json.load(open("$DATA"))
  m=d if isinstance(d,list) else d.get("movies",[])
  print(len(m))
except Exception: print(0)
PY
)
  [[ "$count" -gt 0 ]] && pass "data.json has $count movies" || warn "data.json empty or unreadable"
else
  note "No assets/data.json found; JS may load different source"
fi

# 6) Report summary of includes in HTML
note "index.html <script> summary:"
grep -n '<script ' "$HTML" | sed 's/^/  /'

# Exit code 0 even on WARN so it's CI-friendly
exit 0
