#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ts="$(date -u +'%Y%m%dT%H%M%SZ')"
out="$root/reports/scraper_comparison_$ts.md"
mkdir -p "$root/reports"

echo "# Scraper comparison ($ts UTC)" > "$out"
echo >> "$out"
mapfile -t files < <(cd "$root" && ls -1 new_release_wall*.py 2>/dev/null | grep -v 'balanced\.py' || true)

if [ "${#files[@]}" -eq 0 ]; then
  echo "No legacy scrapers found." | tee -a "$out"
  exit 0
fi

bal="$root/new_release_wall_balanced.py"
echo "Baseline: new_release_wall_balanced.py" >> "$out"
echo >> "$out"

for f in "${files[@]}"; do
  abs="$root/$f"
  echo "## $f" >> "$out"
  echo "- lines: $(wc -l < "$abs")" >> "$out"
  echo "- imports: $(grep -E '^import |^from ' "$abs" | wc -l | tr -d ' ')" >> "$out"
  echo "- uses with_release_type in API params: $(grep -c 'with_release_type' "$abs")" >> "$out"
  echo "- checks type 4/6 after fetch: $(grep -Erc '\b(4|6)\b' "$abs")" >> "$out"
  echo "- provider endpoint usage: $(grep -irc 'watch/providers' "$abs")" >> "$out"
  echo "- max-pages logic: $(grep -irc 'max[-_ ]*pages' "$abs")" >> "$out"
  echo "- caching: $(grep -irc 'cache' "$abs")" >> "$out"
  echo >> "$out"
  echo "<details><summary>diff vs balanced</summary>" >> "$out"
  echo "" >> "$out"
  echo '```diff' >> "$out"
  diff -u "$bal" "$abs" || true >> "$out"
  echo '```' >> "$out"
  echo "" >> "$out"
  echo "</details>" >> "$out"
  echo >> "$out"
done

echo "Wrote $out"