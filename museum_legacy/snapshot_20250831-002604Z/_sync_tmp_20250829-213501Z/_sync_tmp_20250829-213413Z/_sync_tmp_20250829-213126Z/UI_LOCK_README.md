# UI Lock System v1

## Overview
The UI Lock system protects the canonical flippable card interface from unintended modifications. It ensures the core user experience remains consistent while allowing safe development.

## Protected Interface
- **Front**: Movie poster with RT score badge
- **Back**: Trailer, RT score, and Wiki buttons with metadata
- **Interaction**: Click/hover to flip cards
- **Layout**: VHS-style card grid with date grouping

## Files
- `.ui_lock.json` - Configuration and protected file list
- `.ui_lock.sha256` - Checksums for protected templates
- `ui_lock.sh` - Verification and restore utilities
- `preflight.sh` - Automated preflight checks
- `templates_canonical/` - Backup copies for restoration

## Usage

### Verify Templates
```bash
./ui_lock.sh verify
```

### Restore Corrupted Templates
```bash
./ui_lock.sh restore
```

### Auto-Fix (verify + restore if needed)
```bash
./ui_lock.sh auto-fix
```

### Full Preflight Check
```bash
./preflight.sh
```

## Integration
The UI Lock is automatically checked by:
- `preflight.sh` - Before major operations
- Development workflows - Before deployments
- Sync restoration - After state changes

## Modifying Protected Templates
1. Create proposal in PROJECT_CHARTER.md
2. Get explicit approval for changes
3. Update checksums after approved modifications:
   ```bash
   # After making approved changes
   : > .ui_lock.sha256
   jq -r '.files[]' .ui_lock.json | while read f; do
     shasum -a 256 "$f" >> .ui_lock.sha256
   done
   ```

## Recovery
If templates are corrupted:
1. Auto-restore attempts canonical backup first
2. Falls back to snapshot restoration
3. Reports failure if neither works
4. Manual recovery: restore from `templates_canonical/` or latest snapshot

## Charter Amendment
See PROJECT_CHARTER.md Amendment: UI Lock v1 for governance details.
