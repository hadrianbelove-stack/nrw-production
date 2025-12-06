#!/bin/bash
# Manual batch enrichment - runs enrichment and stops after N movies

BATCH_SIZE=${1:-20}
LOG_FILE="/tmp/enrich_batch_$(date +%s).log"

echo "Starting batch enrichment (max $BATCH_SIZE movies)"
echo "Log file: $LOG_FILE"

# Start enrichment in background
python3 generate_data.py > "$LOG_FILE" 2>&1 &
PID=$!

echo "Enrichment started (PID: $PID)"
echo "Monitoring progress..."

# Monitor progress
completed=0
while kill -0 $PID 2>/dev/null; do
    # Count completed movies
    new_completed=$(grep -c "✓.*- Links:" "$LOG_FILE" 2>/dev/null || echo 0)

    if [ "$new_completed" -gt "$completed" ]; then
        completed=$new_completed
        echo "  Progress: $completed/$BATCH_SIZE movies enriched"
    fi

    # Stop after batch size reached
    if [ "$completed" -ge "$BATCH_SIZE" ]; then
        echo "Batch size reached ($completed movies), stopping..."
        kill $PID 2>/dev/null
        sleep 2
        kill -9 $PID 2>/dev/null
        break
    fi

    sleep 5
done

echo ""
echo "Batch complete: $completed movies enriched"
echo "Log saved to: $LOG_FILE"
