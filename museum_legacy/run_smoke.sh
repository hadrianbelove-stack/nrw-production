#!/usr/bin/env bash
set -euo pipefail
python3 new_release_wall_balanced.py --region US --days 14 --max-pages 2
python3 new_release_wall_balanced.py --region US --days 14 --max-pages 2 --use-core --core-limit 10 || true
python3 tests/smoke_test.py