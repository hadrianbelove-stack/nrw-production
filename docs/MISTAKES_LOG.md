# NRW Mistakes Log

When adding entries, consider: should this become a Critical Rule in CLAUDE.md? If the mistake could cause data loss or require significant recovery, promote it.

## Template

```
### [Date] - Brief description
**What went wrong:**
**Correct approach:**
**Rule added:** (if promoted to Critical Rules in CLAUDE.md)
```

---

### 2026-02-02 - Manually launched servers instead of using launch_all.sh
**What went wrong:** Repeatedly launched servers manually with `python3 -m http.server` and `python3 admin.py`, causing stale process issues. Assumed servers were running based on lsof output without verifying they responded.
**Correct approach:** ALWAYS use `./launch_all.sh` - it handles killing stale processes, port conflicts, and verifies servers respond before reporting success.
**Rule added:** Never manually launch servers. The script exists for a reason. Quick reference: Site = 3000, Admin = 5556
