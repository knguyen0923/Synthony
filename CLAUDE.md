# Synthony — Claude Code instructions

- At the start of a session, read `RESUME.md` first to pick up where the last session left off before doing anything else.
- Be efficient with subagents: don't dispatch an Agent/Task for something you can just do directly (a single file read, a quick grep, a small edit). Reserve subagents for work that genuinely benefits from it — parallelizable fan-out, isolating a large/noisy exploration from context, or an independent second opinion (e.g. code review before merge). When in doubt, do it inline.
- Cap concurrent agents at 3 — don't fan out wider than that in one batch.
- Avoid dispatching a single agent task expected to burn ~100k+ tokens; break it into smaller, more targeted asks instead.
- If overall session usage hits ~90% of the limit, stop current work and update `RESUME.md` with where things stand before continuing.
- Avoid letting files grow past ~400 lines where possible — split out helper functions/modules instead of endlessly appending to one file.
- Keep `README.md` and `TAKEAWAYS.md` up to date as work progresses — don't let them go stale.
