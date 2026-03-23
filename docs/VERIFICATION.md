# NRW Verification Commands

## After Pipeline Operations
```bash
python3 ops/health_check.py
```
Run this BEFORE telling user "done." If it fails, report the failure.

## After Data Changes
```bash
cat metrics/discovery_run.json | jq '.status'
cat metrics/newly_available.json | jq 'length'
```

## After Any Code Changes
Show the user:
1. What file(s) changed
2. Run health_check.py
3. Suggest how to manually verify (e.g., "open index.html to see the change")

## Before Saying "Task Complete"
Ask yourself: "How would the user verify this worked?" If you can run that verification, do it first.
