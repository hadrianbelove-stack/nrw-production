NRW Workflow (concise)
1) Do not patch generated HTML. Edit only: templates/, assets/, scripts/, data/.
2) Runtime render: assets/data.json -> assets/nrw_render.js -> index.runtime.html/site.html.
3) Generators fold the same renderer into templates/site.html for handoffs.
4) Handoffs: use nrw-handoff.sh; package must include index.handoff.html + POSTVALIDATION.txt.
5) LLM usage: always include docs/LLM_PREAMBLE.md and a short task. Never "before the closing tag" directions.
6) PRs: include WHAT changed, WHY, TEST evidence (URL/screenshot), and RISK.
7) Versioned data contracts: docs/DATA_CONTRACT.md governs assets/data.json fields.
8) No silent schema changes. Any schema change updates docs/DATA_CONTRACT.md and bumps schema_version.
