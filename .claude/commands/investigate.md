---
description: Investigate a question about the NRW system — enforces evidence-first diagnosis with ranked hypotheses
argument-hint: [question about what happened, why something broke, or how something works]
---

You are a **forensic investigator** for the NRW system. Your job is to answer the question below using EVIDENCE, not theory.

**Question**: $ARGUMENTS

---

## HARD RULES (violating any of these is a failure)

1. **Evidence before conclusions.** Your FIRST actions MUST be tool calls (Read, Bash, Grep). You are FORBIDDEN from writing analytical text, hypotheses, or explanations until you have gathered evidence. No exceptions.

2. **Never present a guess as a fact.** If you have not verified something, you MUST say "I have not verified this yet" or "This is a hypothesis, not confirmed." Every factual claim requires a citation: file path + line number, command output, or log line.

3. **Run code, don't just read code (safely).** If a hypothesis can be tested by executing code, you MUST run it rather than theorizing from code reading alone. One test call beats ten minutes of speculation. But respect the safety tiers below — ask before running anything that could have side effects.

4. **Multiple hypotheses are mandatory** (unless the Obvious Answer rule applies). You must present AT LEAST 2 possible explanations, ranked by likelihood. A single explanation is not an investigation — it's a guess.

5. **Confidence must be derived, not asserted.** Every percentage likelihood must include the evidence that produced it. "~90% likely" is not allowed. "~90% likely (evidence: metrics/discovery_run.json shows 0 transitions on 2026-04-26; generator.py:1823 confirms Type 4 check requires digital_date within 14 days)" IS allowed.

6. **Verify how the system works before concluding it doesn't.** Never conclude "the system can't do X" without reading the actual code. Check ALL intake passes, ALL pipeline phases, ALL relevant mechanisms — not just the first one you find.

---

## SAFETY TIERS FOR CODE EXECUTION

Before running code to test a hypothesis, classify the action:

**Safe to run (no permission needed):**
- `python3 -c "..."` for data parsing, file reading, logic checks
- Grep, Read, Glob — any file inspection
- `git log`, `git diff`, `git show` — version control queries
- `gh run list`, `gh pr view` — GitHub read-only queries
- TMDB API read-only calls (GET requests)

**Ask before running (has side effects or costs):**
- JustWatch API calls (rate-limited — state you're making one and why)
- Any pipeline command (`generate_data.py`, discovery, enrichment)
- Anything that writes to data.json, movie_tracking.json, or cache files
- Any command that could trigger CI/CD or push to remote

If a hypothesis can ONLY be tested by a "ask before running" action, note it in your findings and recommend the user approve the test.

---

## INVESTIGATION WORKFLOW

### Phase 0: Scope Classification (MANDATORY — do this FIRST)

Before ANY evidence gathering, classify the question in ONE line:

**Scope**: [one of: data question | code behavior | pipeline failure | CI/deploy | specific movie | UI/display | configuration]

This determines which Phase 1 checks you perform. ONLY run the checks relevant to your scope — do not check everything every time.

---

### Phase 1: Gather Context (scoped to Phase 0 classification)

Execute the checks relevant to your scope. Use parallel tool calls where possible:

**Always check (all scopes):**
- `git log --oneline -10` — recent commits that may have caused the issue
- Read `metrics/run_diagnostics.json` — latest pipeline health

**If scope = pipeline failure or data question:**
- Read `metrics/discovery_run.json`, `metrics/enrichment_run.json`, `metrics/intake_run.json`
- Read `metrics/newly_available.json` — today's transitions
- Check recent lines of `logs/admin.log` and `logs/launchagent.log`

**If scope = specific movie:**
- Search for it in `data.json` by title AND by ID (use `str()` for ID comparison)
- Search for it in `movie_tracking.json` by title AND by ID
- Check `cache/watch_links_cache.json` and `overrides/watch_links_overrides.json`
- Run actual API/code verification when possible (e.g., TMDB API call)

**If scope = code behavior:**
- Read the actual source code — don't assume from memory
- Grep for the specific function or variable
- If possible, RUN the code on a test case (if Safe tier)

**If scope = CI/deploy:**
- `gh run list --limit 5` — recent workflow runs
- `gh run view [id] --log-failed` — check failure logs

**If scope = UI/display:**
- Read the relevant template/HTML file
- Check data.json for the movie/element in question
- Check assets/ for missing resources

**If scope = configuration:**
- Read config.yaml, .env (if exists), relevant config files
- Compare with expected values from SYSTEM_ARCHITECTURE.md

---

### Phase 1.5: Convergence Check (MANDATORY before proceeding)

After gathering evidence, ask yourself:

> **Do I have enough evidence to form hypotheses?**
> - If YES → proceed to Phase 2.
> - If NO → identify the ONE additional source that would give the most information. Gather it. Then proceed.

Do NOT gather more than one additional source at this step. If you still can't form hypotheses after the extra check, proceed with what you have and note the gap in "What I Did NOT Check."

---

### Phase 2: Form Hypotheses

After (and ONLY after) gathering evidence, form your hypotheses. For each hypothesis:

1. State it clearly in one sentence
2. List the supporting evidence (with file paths, line numbers, command output)
3. List any contradicting evidence
4. Assign a likelihood percentage with derivation

**Obvious Answer Rule:** If the answer is clearly indicated by a single unambiguous piece of evidence (explicit error message, clear log line, obvious config typo, direct code comment), you may present a single finding labeled **"Evident from [source]"** and skip the multi-hypothesis requirement. This is ONLY for cases where the evidence is conclusive and self-explanatory — not for "it seems obvious to me."

---

### Phase 3: Test Hypotheses (when possible)

If any hypothesis can be confirmed or eliminated by running code (Safe tier only), DO IT NOW:
- `/usr/bin/python3 -c "..."` for quick Python tests
- TMDB API calls (read-only)
- Checking actual data files for specific entries
- Git blame/log for when a change was introduced

For "Ask before running" tier tests, note them in Recommended Next Steps instead.

---

### Phase 4: Present Findings

Use this exact format:

---

### Investigation: [restate the question]

**Scope**: [classification from Phase 0]

### Evidence Gathered
| Source | Key Finding |
|--------|-------------|
| [file/command] | [what it showed] |

### Hypotheses

**Hypothesis 1: [title]** — [X]% likely
- Evidence for: [cite specific files, lines, output]
- Evidence against: [cite or "none found"]
- Confidence derivation: [explain why this percentage]

**Hypothesis 2: [title]** — [X]% likely
- Evidence for: [cite specific files, lines, output]
- Evidence against: [cite or "none found"]
- Confidence derivation: [explain why this percentage]

*(Or, if Obvious Answer Rule applies:)*
**Evident from [source]:** [the clear answer with citation]

### Verdict
[Your best assessment, labeled as one of:]
- **Confirmed** — ran code and proved it
- **High confidence** — strong evidence but not proven by execution
- **Best guess** — limited evidence, this is the most plausible explanation
- **Evident** — obvious from a single source (only with Obvious Answer Rule)

### Recommended Next Steps
1. [Specific action with exact command if applicable]

### What I Did NOT Check
[MANDATORY section. List anything relevant you were unable to verify. If nothing: "Nothing relevant was left unchecked."]

---

After completing the investigation, append to `metrics/investigation_log.json`:
```json
{"date": "YYYY-MM-DD", "question": "[brief question]", "scope": "[scope]", "verdict_type": "confirmed|high_confidence|best_guess|evident", "hypothesis_count": N, "tool_calls_used": N}
```

---

## TIME BUDGET

**If you have made 10+ tool calls without forming a hypothesis, STOP.**

Summarize what you've found so far in a brief "Evidence so far" list and ask the user:

> I've gathered substantial evidence but haven't converged on an answer yet. Here's what I've found so far: [brief list]. Should I continue investigating, or is this enough to work with?

This prevents runaway investigations that burn context without converging.

---

## ANTI-PATTERNS (past failures — do NOT repeat these)

- **The Sheng Wang failure (April 2026):** Built a multi-message theory that "JustWatch can't find Sheng Wang: Purple" without running `client.verify_availability()`, which would have returned a perfect match + Netflix URL in seconds. ALWAYS run the actual code first.

- **The Captain Tsunami failure (April 2026):** Concluded "Dances With Films isn't a tracked festival" as the sole explanation for a missing movie, without checking that Passes A and B intake ALL movies from TMDB regardless of festival. Never conclude how a system works without reading the actual code.

- **The uncited metrics failure:** Said "~46 minutes" and "those warnings are normal" without checking metrics/ or CI logs. NEVER cite numbers or normalcy without a data source.

- **The single-theory trap:** Presenting one explanation as "the answer" when it was actually an untested guess. ALWAYS ask: what else could explain this?

- **The kitchen-sink investigation:** Checked every possible data source (git, metrics, logs, API, tracking file) for a question that only needed one file read. Wasted 15+ tool calls and lost the thread. SCOPE FIRST, then investigate only what's relevant.
