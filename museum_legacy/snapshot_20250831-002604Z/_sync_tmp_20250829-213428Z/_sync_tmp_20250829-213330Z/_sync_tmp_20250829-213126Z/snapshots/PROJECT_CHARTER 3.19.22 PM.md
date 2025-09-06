# PROJECT_CHARTER.md

## Core Rules
1. **Immutable Charter** — Updated only via explicit amendments.
2. **Golden Snapshots** — Capture code state with tags for anti-drift.
3. **Session Workflow**
   - Numbered steps (e.g. 7a, 7b).
   - Every block states run condition:
     - "Run now" = safe in parallel
     - "Wait" = must finish before next
     - "Run now and report results" = must paste output
   - No vague phrases (e.g. "after it prints").
   - Optional steps: always list pros/cons before execution.
   - End of each instruction batch: **⚡ To keep moving** summary with parallel/sequential guidance.

## Current Config
- **Port**: 3001 locked  
- **Mode**: offline (no TMDB/RT/trailer API calls live)  
- **Cache**: `.cache/rt/`, `.cache/tmdb/`, `.cache/trailers/`  
- **Frontend**:
  - Renderer: `render_approved.js` (guarded, poster resolver, provider chips, RT, filtering)
  - Templates: single `#cards` container, clean head, deferred assets
  - Styling: VHS flip-card CSS + modern grid overrides (220x330 cards, provider chips)

## Amendments
- **A3**: Numbered labels locked
- **A4**: No assumptions — explicit confirmation required
- **A6**: Run condition must be stated in every code block
- **A7**: Removed vague phrasing — explicit sequencing only
- **A8**: Optional steps require pros/cons
- **A9**: Always include **⚡ To keep moving** summary

## AMENDMENT: SINGLE SOURCE OF TRUTH
RULE-004: No creation of duplicate output files or directories.
- All site builds must overwrite `output/site/index.html` (never `site2/`, `index2.html`, etc.).
- All normalized data must overwrite `output/data.json` and `output/data_core.json`.
- All tracking data must reside in `movie_tracking.json` only.
- Any proposal to generate alternative paths requires explicit APPROVED: NEW_OUTPUT.

## AMENDMENT: ORDERED EXECUTION
RULE-005: Certain workflows must always run in sequence, never parallel.
- Daily Update: (`movie_tracker.py daily` → `generate_from_tracker.py` → `generate_site.py`).
- Session Handoff: smoke tests → verify outputs → sync packaging.
- Parallel processes allowed only after ordered build is complete (e.g., site server, admin panel).

## AMENDMENT: SCRIPT CANONICALIZATION
RULE-006: Automation scripts (e.g., `nrw-daily.sh`, `nrw-handoff.sh`) are the canonical implementation of ordered workflows.
- Assistants must call or modify these scripts instead of re-inventing sequences.
- If workflow changes, update the script once, then always reuse.
- Scripts are binding over freeform instructions.

## AMENDMENT: USER INTERACTION SAFEGUARD
RULE-007: Assume user cannot read or interpret raw code without context.
- Always explain what a command or code snippet does in plain English.
- Never assume prior coding knowledge when presenting steps.
- Any change proposals must describe **why it matters** in 1–2 sentences.

## AMENDMENT: GOLDEN SNAPSHOT
RULE-008: Every session ends with a golden snapshot.
- Run smoke tests and package sync.
- Commit changes.
- Create and push tag `golden-YYYYMMDD-HHMM`.
- Record tag in PROJECT_LOG.md.

## AMENDMENT: DATE-STAMPED ARTIFACTS
RULE-009: All sync artifacts must be uniquely date-stamped.
- `sync_package.sh` must always produce outputs in the format:
  - `NRW_SYNC_YYYYMMDD-HHMM.zip`
  - `NRW_SYNC_YYYYMMDD-HHMM.manifest.txt`
  - `NRW_SYNC_YYYYMMDD-HHMM.sha256`
- Filenames must include both date and 24-hour time for uniqueness.
- `nrw-handoff.sh` must log the exact artifact filename and associated golden tag into `PROJECT_LOG.md`.
- This rule ensures every session handoff can be traced and drift can be diagnosed by inspecting dated artifacts.

## AMENDMENT: EXECUTION CONFIRMATION
RULE-010: No amendment, change, or update is considered binding until applied via an executable patch script and confirmed by the user.
- Fenced code blocks are the only valid medium for patch scripts.
- Plain text instructions, proposals, or drafts are non-binding until codified into a patch and executed.
- Assistants must never assume completion unless the user explicitly states that the patch has been run.

## AMENDMENT: RUN CATEGORIZATION
RULE-011: Every executable block must declare run semantics.
- Each code block must state: run now, run after <step>, or run in parallel with <step>.
- Use step labels like 7c, 7d for cross-reference.

## AMENDMENT: SEQUENTIAL VS PARALLEL
RULE-012: All instructions must declare dependencies.
- If steps depend, mark them sequential.
- If independent, mark them as safe to run in parallel.

## AMENDMENT: NO ASSUMPTIONS
RULE-013: Assistants must never assume the user knows concurrency safety.
- Always state explicitly whether a block can run concurrently.

## AMENDMENT: IDLE TIME RULE
RULE-014: During long-running steps, assistants must propose safe parallel tasks.
- Only non-writing, low-risk actions (config edits, checks, backups).

## AMENDMENT: SUMMARY QUEUEING
RULE-015: After each step group, provide a concise next-steps queue.
- Example: run 7c now; run 7e in parallel; after 7c finishes, run 7d.

## AMENDMENT: ALWAYS BUNDLE AT END OF SESSION
RULE-016: End-of-session procedure is mandatory.
- Update PROJECT_LOG.md, update PROJECT_CHARTER.md (new rules), update complete_project_context.md.
- Package NRW_SYNC_YYYYMMDD-HHMM.zip + .sha256.

## AMENDMENT: NAMING & NUMBERING
RULE-017: Always label steps with numbers and letters (e.g., 7a, 7b, 7c).

## AMENDMENT: MODE AWARENESS
RULE-018: All code blocks must state whether they require online mode or are safe in offline mode.
- Online = requires TMDB/OMDb access and valid credentials.
- Offline = runs entirely on cached/local data.
- Assistants must check current mode (config.yaml or env) before giving blocks, and must not propose online-only code while offline.

## AMENDMENT: BUNDLES OUT OF GIT
RULE-019: Bundles are never committed to Git.
- Do not add NRW_SYNC_*.zip/.sha256/.manifest to the repository.
- Store bundles in external archive (default: ~/NRW_BUNDLES) or a release store.
- Git tracks only code and docs; PROJECT_LOG records artifact names and tags.

## AMENDMENT: COLLABORATION POLICY
RULE-020: Fresh clones required after history rewrites.
- After any history rewrite (e.g., bundle purges), collaborators MUST re-clone. Stale clones must not push.
- Handoffs must state current mode (offline/online) and the latest golden tag.
- Assistants must not provide instructions that assume an out-of-date clone.

## AMENDMENT: SESSION START VISIBILITY
RULE-022: Always unpack latest NRW_SYNC at session start.
- Assistants must detect the latest `NRW_SYNC_*.zip` provided in the session and immediately unpack and read all code, HTML, JS, CSS, templates, and configs.
- If multiple bundles exist, use the lexicographically newest timestamp (NRW_SYNC_YYYYMMDD-HHMM.zip).
- Within the same session, assistants must remember that the code is available and must not claim lack of access.
- If the bundle is absent, corrupted, or too large to parse efficiently, assistants must request a lightweight code snapshot (`NRW_CODE_SNAPSHOT_*.zip`) as fallback, but this does not replace the full bundle in handoffs.

## AMENDMENT: SNAPSHOT POLICY
RULE-023: Snapshot Policy.
- At session start, assistants must unpack the latest NRW_SYNC bundle (RULE-022) and, if provided, prefer the latest code snapshot.
- During active coding, assistants must request a fresh code snapshot at least every 2 hours or before proposing structural changes.
- Snapshots are lightweight and include: source code (.py/.js/.html/.css), templates, configs, and docs; they may optionally include output/site/index.html. They exclude data caches and media.
- Snapshots are a convenience for visibility; full sync bundles remain the canonical archive.

Operational Notes:
- Use the standard snapshot maker `./nrw-make-code-snapshot.sh [--with-index]`.
- Use the session wrapper `./nrw-session-open.sh` at session start, and `./nrw-session-refresh.sh` during long sessions.

## CLARIFICATION: MODE AWARENESS IS ASSISTANT-INTERNAL
This clarifies RULE-018. Mode checks are performed by assistants. Do not burden the user with mode classification language in instructions. Assistants must silently ensure code blocks match the current mode and only surface mode when it affects outcomes or credentials.

## CLARIFICATION: SNAPSHOT POLICY IS FOR VISIBILITY, NOT USER BURDEN
This clarifies RULE-023. The user's action is simple: provide a snapshot at session start and during long sessions when asked. All categorization, parsing, and timing logic is handled by assistants and scripts. Assistants must not include internal checks (like mode notes) in user-facing run instructions.

## AMENDMENT: VISIBILITY GUARANTEE
RULE-021: Visibility Guarantee.
- Every working session must provide a code snapshot to the assistant (or the latest NRW_SYNC bundle).
- Assistants must base all recommendations on the most recent provided code snapshot or unpacked NRW_SYNC.
- Handoffs must embed the snapshot filenames in PROJECT_LOG.md for traceability.

## AMENDMENT: CHARTER CANONICAL SOURCE
RULE-024: Charter Canonical Source.
- The authoritative PROJECT_CHARTER.md is always the copy included in the latest NRW_SYNC or CODE_SNAP archive.
- Standalone uploads of PROJECT_CHARTER.md are ignored unless explicitly marked **APPROVED: CHARTER-REPLACE**.
- All assistant recommendations, workflows, and audits must reference the canonical Charter from the current sync/snapshot.
- This prevents drift caused by stale or partial charter copies.
