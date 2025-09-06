#!/usr/bin/env bash
set -euo pipefail
cd ~/Downloads/new-release-wall

CMD="${1:-verify}"

verify() {
  local mismatch=0
  if [[ ! -f .ui_lock.sha256 ]]; then
    echo "UI-LOCK: missing .ui_lock.sha256"; exit 4
  fi
  while read -r sum path; do
    [[ -f "$path" ]] || { echo "UI-LOCK: missing $path"; mismatch=1; continue; }
    cur="$(shasum -a 256 "$path" | awk '{print $1}')"
    [[ "$cur" == "$sum" ]] || { echo "UI-LOCK: hash mismatch $path"; mismatch=1; }
  done < .ui_lock.sha256
  return $mismatch
}

restore_from_canonical() {
  echo "UI-LOCK: Restoring from templates_canonical/"
  while IFS= read -r f; do
    canonical="templates_canonical/$(basename "$f")"
    [[ -f "$canonical" ]] && cp "$canonical" "$f" || echo "WARN: No canonical backup for $f"
  done < <(jq -r '.files[]' .ui_lock.json)
}

restore_from_snapshot() {
  local prev
  prev="$(ls -1dt snapshots/SNAP_* 2>/dev/null | sed -n 2p || true)"
  [[ -n "$prev" && -f "$prev/TREE.tgz" ]] || return 1
  echo "UI-LOCK: Restoring templates from snapshot $prev"
  
  # Extract templates from snapshot
  local temp_dir=$(mktemp -d)
  tar -xzf "$prev/TREE.tgz" -C "$temp_dir" 2>/dev/null || return 1
  
  # Find the templates directory in extracted content
  local templates_path=$(find "$temp_dir" -name "templates" -type d | head -1)
  [[ -n "$templates_path" ]] || { rm -rf "$temp_dir"; return 1; }
  
  # Restore locked files
  while IFS= read -r f; do
    local source="$templates_path/$(basename "$f")"
    [[ -f "$source" ]] && cp "$source" "$f" || echo "WARN: Could not restore $f from snapshot"
  done < <(jq -r '.files[]' .ui_lock.json)
  
  rm -rf "$temp_dir"
  return 0
}

case "$CMD" in
  verify)
    if verify; then
      echo "UI-LOCK: ✓ All templates verified"
      exit 0
    else
      echo "UI-LOCK: ✗ Template integrity compromised"
      exit 1
    fi
    ;;
  restore)
    restore_from_canonical || restore_from_snapshot || {
      echo "UI-LOCK: ✗ Could not restore templates"
      exit 2
    }
    echo "UI-LOCK: ✓ Templates restored"
    ;;
  auto-fix)
    if ! verify; then
      echo "UI-LOCK: Attempting auto-restore..."
      restore_from_canonical || restore_from_snapshot || {
        echo "UI-LOCK: ✗ Auto-restore failed"
        exit 3
      }
      echo "UI-LOCK: ✓ Auto-restore completed"
    else
      echo "UI-LOCK: ✓ No restore needed"
    fi
    ;;
  *)
    echo "Usage: $0 {verify|restore|auto-fix}"
    exit 1
    ;;
esac
