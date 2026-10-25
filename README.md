# App Review UX Report Agent

Give it an iOS app; get back a descriptive, statistically grounded UX report built from the app's public
App Store reviews. It names the specific problems and strengths reviewers raise, says how often each
occurs (stratified by country, with 95% intervals), how reviewers feel about it, where in the journey it
happens, which team likely owns it, and how reliable each label is. It describes; it never recommends.

Spec: [App Review UX Report Agent PRD.md](App%20Review%20UX%20Report%20Agent%20PRD.md).
Example of the finished page (made-up data): [docs/ShopNest Review Report.html](docs/ShopNest%20Review%20Report.html).

## Quick start

```bash
./setup.sh
```

```bash
./run.sh "Duolingo"
```

Other inputs: an App Store link (`./run.sh "https://apps.apple.com/us/app/duolingo/id570060128"`), a numeric
id (`./run.sh 570060128`), one country only (`--country de`), or any setting (`--set reviews_per_country=200`).
In Claude Code: `/ux-report Duolingo`, or `claude --agent orchestrator "Duolingo"`.

The run writes `runs/<app-id>_<date>/`:

| Path | Content |
| --- | --- |
| `report/report.html`, `report/report.pdf` | The finished report |
| `data/*.csv` | Reviews, statements, issues and issue statistics |
| `raw/`, `clean/`, `labels/`, `issues/`, `validation/`, `stats/` | Every intermediate file (JSON, JSONL, YAML) |
| `run.json`, `run.log` | Run record: input, chosen app, countries and weights, settings, models, prompt versions, step timings, counts, gates |
| `ai/` | Every AI answer, cached; re-running with the same inputs reuses them |

An interrupted run continues with `./run.sh --resume runs/<folder>` (add `--from-step N` to redo from a step).

## Requirements
- macOS or Linux, Python 3.10 to 3.13, internet access.
- **AI**: Claude Code installed and signed in (the AI steps run as headless `claude -p` calls on your
  login), or `ANTHROPIC_API_KEY` set with `pip install anthropic`. Models: `claude-haiku-5-5` for
  extraction, assignment and the second pass; `claude-opus-5-5` for issue naming and report text
  (`config/settings.yaml` → `models`).
- Google Chrome, Chromium, Edge or Brave for the PDF export (the HTML is produced without one).

## How it works
Fifteen steps in a fixed order (PRD section 5). Code collects, checks, computes and renders; AI sub-agents
read, label and name.

| # | Step | Actor | Script |
| --- | --- | --- | --- |
| 1 | Resolve app, read listing | code | `resolve_app.py` |
| 2 | Select countries (80% of ratings, 3 to 10) | code | `select_countries.py` |
| 3 | Collect up to 500 newest reviews per country | code | `collect.py` |
| 4 | Clean: duplicates, language, version, date windows | code | `clean.py` |
| 5 | Split reviews into statements | AI: statement-extractor | `extract.py` |
| 6 | Check every quote is verbatim | code (+ one AI retry) | `check_quotes.py` |
| 7 | Embed and cluster issue phrases (HDBSCAN) | code | `group_phrases.py` |
| 8 | Name issues; derive categories, journey, teams | AI: issue-namer | `name_issues.py` |
| 9 | Assign each statement an issue and a stage | AI: issue-assigner | `assign_labels.py` |
| 10 | Independent second pass on 10% | AI: second-rater | `second_pass.py` |
| 11 | Quality gates | code | `quality_gate.py` |
| 12 | Statistics | code | `stats.py`, `statlib.py` |
| 13 | Write text slots | AI: report-writer | `write_report.py` |
| 14 | Audit numbers and wording | code + AI: report-auditor | `check_numbers.py` |
| 15 | Render HTML from the fixed template, print PDF | code | `render_report.py` |

Claude Code pieces: sub-agents in `.claude/agents/`, skills in `.claude/skills/` (codebook, phrasing,
naming, app structure, team routing, statistics definitions, report slots, descriptive voice, and the
`/ux-report` entry point), and the `app-store` MCP server in `.mcp.json` (`search_apps`, `lookup_app`,
`get_reviews`, `get_listing`).

## Differences from the PRD
- **Review source.** Apple's customer-review RSS feed (PRD section 3) now returns no entries. Reviews
  come from the App Store web catalog API that apps.apple.com uses: newest first, 20 per page. The
  500-per-country cap is kept as a setting.
- **App version per review.** That API does not return the version a review was written on. Each review
  gets the version released most recently before its date (`version_inferred: true`), and the report
  states this as a limit.
- **Coverage retry.** When more than 15% of statements fit no issue, only those statements are regrouped
  with a smaller minimum cluster size, the issue-namer adds issues for them, and they are re-assigned.
  Issues already named stay frozen.
- **Reproducibility.** The `claude -p` backend has no temperature setting; cached answers make re-runs
  identical. With the API backend, temperature is 0.

- **Models on older Claude Code.** If the installed `claude` rejects a configured model id (Claude Code
  2.1.169 cannot run `claude-opus-5-5`; 2.1.280 or newer is required), `llm.py` falls back to the CLI's
  own `opus` / `haiku` alias and records the model that answered in `run.json` → `ai_usage.models_used`.
  Run `claude update` to use the configured models.
- **Reasoning effort.** Headless calls use `--effort low` for the fast tier and `medium` for the strong
  tier (`ai_effort`); at the CLI default, issue naming took more than 15 minutes for 100 reviews.

## Token use
The AI steps exchange compact rows instead of keyed JSON: the extractor writes one 10-value row per
statement with short codes for type, sentiment, severity and UX dimension (expanded by code, see
`common.py`); the assigner returns only the statements it changes; the second rater gets each review
once with its sampled statements. Batches are larger (40 reviews, 150 statements), so each system prompt is
sent fewer times. On the same 100-review test this cut output tokens by about 62% for extraction, 84% for
assignment and 69% per statement for the second pass, with κ 0.89 against 0.85 before.
`run.json` → `ai_usage.tokens` records input, cached and output tokens per agent.

## Known limits
- Template v1.0 divides by the review count of each star level in the review-mix chart, so a run with no
  reviews at some star level logs `NaN` SVG attribute errors (the chart still draws). Fixing it needs a
  new template version.
- Each country's 500 newest reviews often cover only days for large apps, so "Issues over time" is hidden
  unless six weeks have at least 50 reviews each.

## Verified runs (2026-10-21)
| Run | Reviews | Time | Result |
| --- | --- | --- | --- |
| Duolingo, GB only, 100 per country | 100 | about 6 min of work | 9 recurring issues, 5 categories, 6 stages; κ 0.77; audit 46 numbers, 0 mismatches |
| Revolut, 9 countries chosen automatically, 150 per country | 1,350 | 18 min 40 s | 20 recurring issues, 8 categories, 8 stages; κ 0.79; audit 63 numbers, 0 mismatches |

## Tests

```bash
.venv/bin/python -m pytest tests
```

`tests/test_statlib.py` checks every formula against reference values (AC-3). `tests/test_render.py`
renders the sample data and checks the template contract.
`tests/test_stats_pipeline.py` runs steps 12 to 15 on a fixed synthetic run (known shares, a planted
rise found by the over-time test, a valid rendered report) without AI calls.
