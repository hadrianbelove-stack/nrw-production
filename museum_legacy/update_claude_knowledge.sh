#!/bin/bash
echo "# New Release Wall - Complete Codebase" > ALL_CODE.md
echo "Updated: $(date)" >> ALL_CODE.md
echo "Total: $(ls *.py | wc -l) Python files" >> ALL_CODE.md
echo "" >> ALL_CODE.md

for file in *.py; do
    echo "## $file" >> ALL_CODE.md
    echo '```python' >> ALL_CODE.md
    cat "$file" >> ALL_CODE.md
    echo '```' >> ALL_CODE.md
    echo "" >> ALL_CODE.md
done

echo "✅ Created ALL_CODE.md with all $(ls *.py | wc -l) files ($(du -h ALL_CODE.md | cut -f1))"
echo "📋 Next: Upload ALL_CODE.md to Claude Project Knowledge"
