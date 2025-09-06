#!/bin/bash

# Create concatenated code file for AI sync
OUTPUT_FILE="ALL_CODE_SYNC.py"

echo "# ================================================================" > $OUTPUT_FILE
echo "# NEW RELEASE WALL - ALL CODE CONCATENATED" >> $OUTPUT_FILE
echo "# Generated: $(date)" >> $OUTPUT_FILE
echo "# Purpose: Complete codebase for syncing with other AI systems" >> $OUTPUT_FILE
echo "# ================================================================" >> $OUTPUT_FILE
echo "" >> $OUTPUT_FILE

# List of files to include
FILES=(
    "./adapter.py"
    "./admin.py"
    "./concurrent_scraper.py"
    "./convert_tracking_to_vhs.py"
    "./diagnostics.py"
    "./enhanced_discovery.py"
    "./export_for_admin.py"
    "./find_all_indie_films.py"
    "./fix_tracking_dates.py"
    "./generate_from_tracker.py"
    "./generate_site.py"
    "./generate_substack.py"
    "./hybrid_site_restore.py"
    "./justwatch_collector.py"
    "./movie_tracker.py"
    "./movie_tracker_basic_backup.py"
    "./new_release_wall.py"
    "./new_release_wall_balanced.py"
    "./quick_rt_update.py"
    "./quick_site_update.py"
    "./restore_full_site.py"
    "./rt_fetcher.py"
    "./update_movie_providers.py"
)

# Process each file
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "# ================================================================" >> $OUTPUT_FILE
        echo "# FILE: $file" >> $OUTPUT_FILE
        echo "# ================================================================" >> $OUTPUT_FILE
        cat "$file" >> $OUTPUT_FILE
        echo "" >> $OUTPUT_FILE
        echo "" >> $OUTPUT_FILE
    else
        echo "# FILE NOT FOUND: $file" >> $OUTPUT_FILE
        echo "" >> $OUTPUT_FILE
    fi
done

# Get stats
TOTAL_LINES=$(wc -l < $OUTPUT_FILE)
TOTAL_SIZE=$(wc -c < $OUTPUT_FILE | numfmt --to=iec)
FILE_COUNT=${#FILES[@]}

echo "✅ Created $OUTPUT_FILE"
echo "📊 Stats: $FILE_COUNT files, $TOTAL_LINES lines, $TOTAL_SIZE"