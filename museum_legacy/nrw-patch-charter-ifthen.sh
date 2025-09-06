#!/usr/bin/env bash
set -euo pipefail
cd "${REPO:-$PWD}"

STAMP="$(date -u +%Y%m%d-%H%M%SZ)"
cp -n PROJECT_CHARTER.md "charter_history/PROJECT_CHARTER_before_IFTHEN_${STAMP}.md" 2>/dev/null || true

awk '
  BEGIN{done=0}
  /^### AMENDMENT-011/ {print; next}
  /^### AMENDMENT-012/ && !done {
    print ""
    print "### AMENDMENT-IFTHEN: Conditional & Parallel Command Flow"
    print ""
    print "- Assistants must not provide compound command blocks that assume contingent results."
    print "  - When later commands depend on prior outputs, assistants must **wait** for the user to paste results before issuing the next executable block."
    print "  - Assistants may describe the contingency in plain language, but executable code must only be shown once prerequisites are confirmed."
    print ""
    print "- When multiple commands are safe to run in parallel, assistants should bundle them into a single copy/paste block, labeled clearly as **safe parallel execution**."
    print "  - This avoids unnecessary back-and-forth while still complying with run-semantics rules."
    print ""
    print "- This amendment clarifies and strengthens AMENDMENT-003 (Run Semantics) and AMENDMENT-011 (Summary Queue), making explicit:"
    print "  - **Sequential** = wait for results before providing next code block."
    print "  - **Parallel** = bundle into a single labeled block where possible."
    print ""
    done=1
  }
  {print}
' PROJECT_CHARTER.md > .tmp && mv .tmp PROJECT_CHARTER.md

echo "- ${STAMP}: Added AMENDMENT-IFTHEN (Conditional & Parallel Command Flow)" >> PROJECT_LOG.md

echo "AMENDMENT-IFTHEN applied and logged."