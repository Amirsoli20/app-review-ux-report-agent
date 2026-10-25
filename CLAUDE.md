# App Review UX Report Agent

Turns the public App Store reviews of an iOS app into a descriptive, statistically grounded UX report.
The spec is `App Review UX Report Agent PRD.md`. One input (app name, App Store link or numeric id,
optional country) produces one finished report with no human steps.

## Run
- `/ux-report <app> [--country cc]`, or `claude --agent orchestrator "<app>"`, or directly `./run.sh "<app>"`.
- Options: `--set key=value` overrides any value in `config/settings.yaml`
  (for a quick test: `--set reviews_per_country=100`); `--resume runs/<folder>` continues a run.
- First time: `./setup.sh` (Python 3.10 to 3.13 venv in `.venv/`). Tests: `.venv/bin/python -m pytest tests`.

## Layout
- `scripts/run_pipeline.py` runs the 15 steps of PRD section 5 in order; each step is one script
  (`resolve_app`, `select_countries`, `collect`, `clean`, `extract`, `check_quotes`, `group_phrases`,
  `name_issues`, `assign_labels`, `second_pass`, `quality_gate`, `stats`, `write_report`, `check_numbers`,
  `render_report`). Each takes the run folder as its first argument and can be run alone.
- AI steps call the sub-agents in `.claude/agents/` through `scripts/llm.py`: the agent body plus the
  skills named in its frontmatter form the system prompt. Backend is headless `claude -p` (this machine's
  Claude Code login) or the Anthropic API when `ANTHROPIC_API_KEY` is set. Answers are cached per run in `ai/`.
- `scripts/appstore.py` is the App Store client (also served as the `app-store` MCP server, `.mcp.json`).
  Apple's old review RSS feed is empty now; reviews come from the App Store web catalog API (20 per page).
- `scripts/statlib.py` holds every statistical formula (unit-tested in `tests/`); `stats.py` applies them.
- Runs go to `runs/<app-id>_<date>/` (raw, clean, labels, issues, validation, stats, report, data, run.json).

## Rules
- Never edit `templates/report-template.html` during a run; its hash is checked at render
  (`templates/report-template.sha256`). A design change is a new template version.
- Every number in the report comes from `stats/stats.json`; AI writes only the text slots of PRD 12.4.
- Report text describes; it never advises ("should", "recommend", "priority", "fix" are rejected) and
  says "reviews"/"reviewers", never "users".
- No category or journey-stage names in any prompt or skill: they are derived per app (AC-6).
- Reviewer names are hashed at collection and never written anywhere.
