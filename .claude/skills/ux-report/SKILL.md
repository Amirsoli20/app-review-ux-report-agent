---
name: ux-report
description: Produce an App Store review UX report for an iOS app - give an app name, App Store link or numeric id, and optionally a two-letter country code. Runs the full 15-step pipeline with no questions and returns report.html, report.pdf and the data folder.
argument-hint: "<app name | App Store link | id> [--country cc] [--set key=value]"
---

# Run the App Review UX Report pipeline

Input: `$ARGUMENTS` (an app name, App Store link or id, then optional flags).

1. If `.venv/` is missing, run `./setup.sh` first (creates the Python environment, about 2 minutes).
2. Start the run in the background from the project root, so it can take as long as it needs:
   `./run.sh $ARGUMENTS`
   Do not ask the user anything; the pipeline resolves names, chooses countries and handles failures on its own.
3. While it runs, the log is in `runs/<app-id>_<date>/run.log` (before step 1 finishes the folder is
   `runs/_pending_<time>/`). Wait for the background command to finish instead of polling.
4. When it finishes, read `run.json` and `report/audit.json` in the run folder and tell the user:
   - where `report/report.html`, `report/report.pdf` and `data/` are;
   - which app was chosen (and the next match, when the input was a name), the countries and the review count;
   - every quality gate with status `flag`, and the summary findings from `report/report_data.json`.
5. If it stopped, say at which step and why, and give the resume command:
   `./run.sh --resume runs/<folder>`

Never edit `templates/`, `schemas/` or the report HTML, and never write report text yourself.
