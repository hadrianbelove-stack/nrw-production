#!/bin/bash
# NRW COO bootstrap
set -euo pipefail
cd "${REPO:-$PWD}"

mkdir -p scripts docs .github

# A. Single source of truth
cat > docs/WORKFLOW.md <<'MD'
NRW Workflow (concise)
1) Do not patch generated HTML. Edit only: templates/, assets/, scripts/, data/.
2) Runtime render: assets/data.json -> assets/nrw_render.js -> index.runtime.html/site.html.
3) Generators fold the same renderer into templates/site.html for handoffs.
4) Handoffs: use nrw-handoff.sh; package must include index.handoff.html + POSTVALIDATION.txt.
5) LLM usage: always include docs/LLM_PREAMBLE.md and a short task. Never "before the closing tag" directions.
6) PRs: include WHAT changed, WHY, TEST evidence (URL/screenshot), and RISK.
7) Versioned data contracts: docs/DATA_CONTRACT.md governs assets/data.json fields.
8) No silent schema changes. Any schema change updates docs/DATA_CONTRACT.md and bumps schema_version.
MD

# B. Data contract skeleton
cat > docs/DATA_CONTRACT.md <<'MD'
assets/data.json — required fields
[
  {
    "title": "string",
    "year": "YYYY",
    "release_date": "YYYY-MM-DD",
    "digital_date": "YYYY-MM-DD|null",
    "poster": "url-or-path",
    "overview": "string",
    "runtime": 95,
    "studio": "string",
    "providers": ["Netflix","Amazon"],
    "rt_url": "url|null",
    "rt_score": 82,
    "trailer": "url|null",
    "wiki": "url|null",
    "sale": "url|null"
  }
]
MD

# C. LLM preamble
mkdir -p docs
cat > docs/LLM_PREAMBLE.md <<'MD'
Style: concise, zero fluff. Output must be paste-ready for Claude Code or shell. No "place before </body>".
Principles: preserve data contract; renderer-only UI changes; propose pros/cons with scores; surface risks.
MD

# D. Verify script
mkdir -p scripts
cat > scripts/nrw-verify.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
err=0
for f in assets/data.json assets/nrw_render.js; do
  [ -f "$f" ] || { echo "MISSING: $f"; err=1; }
done
grep -qE '<div[^>]+id="cards"|class="cards|class="grid"' index.runtime.html 2>/dev/null || {
  echo "MISSING: cards container in index.runtime.html"; err=1; }
if [ $err -ne 0 ]; then exit 2; else echo "VERIFY: OK"; fi
SH
chmod +x scripts/nrw-verify.sh

# E. Basic .gitignore hardening
{ grep -qxF 'output/' .gitignore || echo 'output/'; } >> .gitignore || true
{ grep -qxF 'WORKING_SET_HANDOFF_*/' .gitignore || echo 'WORKING_SET_HANDOFF_*/'; } >> .gitignore || true
{ grep -qxF '.nrw_http_pid' .gitignore || echo '.nrw_http_pid'; } >> .gitignore || true

echo "COO bootstrap written. Run: scripts/nrw-verify.sh"