#!/usr/bin/env bash
set -euo pipefail
cd ~/Downloads/new-release-wall

LOCK=".code_lock.sha256"

# Globs to include/exclude
INCLUDE=( "*.py" "templates/**" "static/**" "config.yaml" "config.yml" "config.example.yaml" "*.css" "*.js" "scripts/*.sh" "sync_package.sh" )
# LEGACY_NRW_SYNC_REMOVED EXCLUDE=( ".git/**" ".venv/**" "node_modules/**" "web/.next/**" "output/**" "cache/**" "logs/**" "snapshots/**" "NRW_SYNC_*.zip" "AUDIT_*.tgz" )

match_exclude() {
  local p="$1"
  for e in "${EXCLUDE[@]}"; do
    case "$p" in $e) return 0;; esac
  done
  return 1
}

build_list() {
  shopt -s globstar nullglob dotglob
  for g in "${INCLUDE[@]}"; do
    for p in $g; do
      if ! match_exclude "$p"; then
        if [[ -d "$p" ]]; then
          for f in "$p"/**/*; do
            [[ -f "$f" ]] && ! match_exclude "$f" && printf '%s\0' "$f"
          done
        elif [[ -f "$p" ]]; then
          printf '%s\0' "$p"
        fi
      fi
    done
  done | sort -z -u
}

lock() {
  : > "$LOCK"
  while IFS= read -r -d '' f; do
    shasum -a 256 "$f" >> "$LOCK"
  done < <(build_list)
  echo "CODE-LOCK: hashes written to $LOCK"
}

verify() {
  [[ -f "$LOCK" ]] || { echo "CODE-LOCK: no $LOCK; run: ./code_lock.sh lock"; exit 2; }
  offenders=()
  while read -r sum path; do
    if [[ ! -f "$path" ]]; then
      offenders+=( "MISSING  $path" )
    else
      cur=$(shasum -a 256 "$path" | awk '{print $1}')
      [[ "$cur" != "$sum" ]] && offenders+=( "CHANGED $path" )
    fi
  done < "$LOCK"
  if (( ${#offenders[@]} )); then
    {
      echo "# DRIFT BLOCKED"
      printf '%s\n' "${offenders[@]}"
      echo
      echo "Apply approved patch, then run: ./code_lock.sh lock"
    } > DRIFT_BLOCKED.md
    printf '%s\n' "${offenders[@]}"
    exit 3
  fi
  echo "CODE-LOCK: OK"
}

case "${1:-verify}" in
  lock) lock ;;
  verify) verify ;;
  *) echo "Usage: code_lock.sh {lock|verify}"; exit 1 ;;
esac
