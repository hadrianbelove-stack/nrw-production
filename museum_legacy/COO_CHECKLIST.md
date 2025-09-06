# COO Daily/Weekly Checklist (New Release Wall)

## Daily (15–30 min)
- **Inbox Zero (Decisions)**: Triage Slack/Email/Docs. Label items as: `Decision`, `Question`, `FYI`, `Blocked`.
- **Change Log**: Append any approved tweaks to `/ops/change_log.md` (see template). One line per change.
- **Data Freshness**: Run `scripts/convert_current_to_data.py` to regenerate `assets/data.json`. Open `prototype.html` and spot‑check a few titles.
- **UI Review**: Capture any UI nits in `/ops/ui_feedback.md` with a screenshot and a “what/why/priority” note.
- **Release Gate**: If we intend to publish today, ensure a green check on the 4 gates: Content ✅ / Design ✅ / QA ✅ / Deploy ✅.

## Weekly (45–60 min)
- **Creative Brief Refresh**: Update `/ops/briefs/weekly_brief.md` (vision, tone, examples, acceptance criteria).
- **Backlog Grooming**: Sort `/ops/backlog.md` by priority. Tag each item with `data`, `ui`, `copy`, or `ops`.
- **Milestone Plan**: Confirm the next 1–2 milestones and who/what is needed from AI vs human.
- **Retrospective**: 3 bullets: What worked / What didn’t / What we’ll do differently.

## Release Playbook (fast path)
1. Convert data → `assets/data.json` (script below).
2. Open `prototype.html` → verify target titles/dates render.
3. Sanity QA: hover/click, date groupings, empty states.
4. If good: copy `prototype.html` to your hosting as `index.html` (or integrate into the real template).
