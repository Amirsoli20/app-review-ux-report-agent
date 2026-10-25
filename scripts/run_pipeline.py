"""Orchestrator: run the 15 pipeline steps in a fixed order with no human input (FR-21).

    python scripts/run_pipeline.py "Duolingo"                       # name, link or numeric id
    python scripts/run_pipeline.py 570060128 --country de           # one country only
    python scripts/run_pipeline.py "Duolingo" --set reviews_per_country=200 --set ai_concurrency=6
    python scripts/run_pipeline.py --resume runs/570060128_2026-10-21  # continue an interrupted run

A step that raises is retried once; if it fails again the run stops only when later steps cannot work
without its output, and the failure is recorded in run.json. Every intermediate file stays in the run folder.
"""
import argparse
import datetime as dt
import shutil
import sys
import time
import traceback
from pathlib import Path

import appstore
import llm
from common import RUNS, TEMPLATES, Run, file_sha256, load_settings, parse_value, read_jsonl

STEPS = [
    (1, "resolve", "Resolve app and read listing"), (2, "countries", "Select countries"), (3, "collect", "Collect reviews"),
    (4, "clean", "Clean"), (5, "extract", "Extract statements"), (6, "quotes", "Check quotes"),
    (7, "group", "Group phrases"), (8, "name", "Name issues and build the app's structure"), (9, "assign", "Assign labels"),
    (10, "second_pass", "Second pass"), (11, "gate", "Quality gate"), (12, "stats", "Compute statistics"),
    (13, "write", "Write report text"), (14, "audit", "Audit report"), (15, "render", "Render"),
]


def parse_args(argv):
    ap = argparse.ArgumentParser(description="App Review UX Report Agent")
    ap.add_argument("app", nargs="?", help="App Store link, numeric app id, or app name")
    ap.add_argument("--country", help="two-letter country code; only that country is used")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a value in config/settings.yaml")
    ap.add_argument("--resume", metavar="RUN_DIR", help="continue a run folder, skipping finished steps")
    ap.add_argument("--from-step", type=int, default=None, help="with --resume: re-run from this step on")
    a = ap.parse_args(argv)
    if not a.app and not a.resume:
        ap.error("give an app (name, link or id) or --resume RUN_DIR")
    return a


def export_csv(run):
    import pandas as pd
    import yaml
    pd.DataFrame(read_jsonl(run.p("clean", "reviews.jsonl"))).to_csv(run.p("data", "reviews.csv"), index=False)
    sts = read_jsonl(run.p("labels", "final.jsonl"))
    for st in sts:
        sp = st.pop("second_pass", None) or {}
        for k, v in sp.items():
            st["second_" + k] = v
    pd.DataFrame(sts).to_csv(run.p("data", "statements.csv"), index=False)
    issues = yaml.safe_load(open(run.p("issues", "issues.yaml"), encoding="utf-8"))["issues"]
    pd.DataFrame([{**i, "team_secondary": "; ".join(i["team_secondary"]), "source_groups": "; ".join(i["source_groups"])} for i in issues]).to_csv(
        run.p("data", "issues.csv"), index=False)
    import json
    stats = json.load(open(run.p("stats", "stats.json"), encoding="utf-8"))
    rows = [{k: (v if not isinstance(v, (list, dict)) else json.dumps(v, ensure_ascii=False)) for k, v in i.items()} for i in stats["report"]["issues"]]
    pd.DataFrame(rows).to_csv(run.p("data", "issue_stats.csv"), index=False)


def elapsed(run):
    """Working time of the run: finished steps of earlier processes plus this process (a resume skips idle time)."""
    r = run.record()
    return r.get("seconds_before", 0) + time.time() - r.get("t_process", r.get("t0", time.time()))


def main(argv=None):
    a = parse_args(argv if argv is not None else sys.argv[1:])
    overrides = {}
    for kv in a.set:
        k, _, v = kv.partition("=")
        overrides[k.strip()] = parse_value(v)
    if a.resume:
        run = Run(a.resume)
        rec = run.record()
        settings = rec["settings"]
        settings.update(overrides)
        app_input, country = rec["input"]["app"], rec["input"].get("country")
        done = {int(k) for k, v in rec.get("steps", {}).items() if v.get("status") == "done"}
        if a.from_step:
            done = {n for n in done if n < a.from_step}
    else:
        settings = load_settings(overrides)
        app_input, country = a.app, a.country
        run = Run(RUNS / ("_pending_" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")))
        done = set()
    appstore.configure(settings)
    backend = llm.pick_backend(settings.get("ai_backend", "auto"))
    if not a.resume:
        run.update_record(input={"app": app_input, "country": country, "overrides": overrides}, settings=settings,
                          models={"fast": settings["models"]["fast"], "strong": settings["models"]["strong"], "backend": backend,
                                  "embedding": settings["embedding_model"]},
                          template={"version": settings["template_version"], "sha256": file_sha256(TEMPLATES / "report-template.html")},
                          started=dt.datetime.now().isoformat(timespec="seconds"), finished=None, t0=time.time(), steps={})
    else:
        run.update_record(settings=settings)
    prior = sum(v.get("seconds", 0) for k, v in run.record().get("steps", {}).items() if int(k) in done)
    run.update_record(t_process=time.time(), seconds_before=prior)
    run.log("Run folder: %s · AI backend: %s (fast %s, strong %s)" % (run.path, backend, settings["models"]["fast"], settings["models"]["strong"]))

    import assign_labels, check_numbers, check_quotes, clean, collect, extract, group_phrases, name_issues  # noqa: E401
    import quality_gate, render_report, resolve_app, second_pass, select_countries, stats, write_report  # noqa: E401
    state = {"retry": None}

    def coverage_then_pass():
        run.update_record(counts={"coverage_retry": None})  # a re-run of this step replaces any earlier retry
        share, _ = quality_gate.other_share(run)
        if share > settings["other_limit"]:
            run.log("Coverage gate: %.1f%% of statements are other (limit %.0f%%); retrying once." % (100 * share, 100 * settings["other_limit"]))
            state["retry"] = quality_gate.coverage_retry(run)
            run.update_record(counts={"coverage_retry": state["retry"]})
        second_pass.main(run)

    def render():
        render_report.main(run.p("report", "report_data.json"), TEMPLATES / "report-template.html", run.p("report", "report.html"))
        err = render_report.to_pdf(run.p("report", "report.html"), run.p("report", "report.pdf"))
        if err:
            run.log(err)
        export_csv(run)

    actions = {
        1: lambda: resolve_app.main(run, app_input, country), 2: lambda: select_countries.main(run, country),
        3: lambda: collect.main(run), 4: lambda: clean.main(run), 5: lambda: extract.main(run), 6: lambda: check_quotes.main(run),
        7: lambda: group_phrases.main(run), 8: lambda: name_issues.main(run), 9: lambda: assign_labels.main(run),
        10: coverage_then_pass, 11: lambda: quality_gate.main(run, state["retry"] or run.record().get("counts", {}).get("coverage_retry")),
        12: lambda: stats.main(run), 13: lambda: write_report.main(run), 14: lambda: check_numbers.main(run), 15: render,
    }
    for n, key, title in STEPS:
        if n in done:
            continue
        run.log("Step %d: %s" % (n, title))
        t0 = time.time()
        err = None
        for attempt in (1, 2):
            try:
                actions[n]()
                err = None
                break
            except llm.UsageLimit as e:
                err = "Claude usage limit reached (%s). Resume later: ./run.sh --resume %s --from-step %d" % (e, run.path, n)
                break
            except SystemExit as e:  # a clear stop condition (no app, no reviews): retrying cannot help
                err = str(e)
                break
            except Exception as e:  # noqa: BLE001
                err = "%s: %s" % (type(e).__name__, e)
                run.log("Step %d failed (attempt %d): %s" % (n, attempt, err))
                with open(run.p("run.log"), "a", encoding="utf-8") as f:
                    f.write(traceback.format_exc() + "\n")
        steps = run.record().get("steps", {})
        steps[str(n)] = {"name": key, "title": title, "seconds": round(time.time() - t0, 1), "status": "failed" if err else "done", "error": err}
        run.update_record(steps=steps, ai_usage=llm.usage_snapshot())
        if err:
            run.log("Stopped at step %d (%s): %s" % (n, title, err))
            run.update_record(finished=dt.datetime.now().isoformat(timespec="seconds"), status="failed")
            return run, 1
        if n == 1 and run.path.name.startswith("_pending_"):
            import json
            app = json.load(open(run.p("app.json"), encoding="utf-8"))
            dest = RUNS / ("%s_%s" % (app["app_id"], dt.date.today().isoformat()))
            k = 2
            while dest.exists():
                dest = RUNS / ("%s_%s_%d" % (app["app_id"], dt.date.today().isoformat(), k))
                k += 1
            shutil.move(str(run.path), str(dest))
            run = Run(dest)
            run.log("Run folder renamed to %s" % dest)
    secs = elapsed(run)
    run.update_record(finished=dt.datetime.now().isoformat(timespec="seconds"), status="done", seconds=round(secs, 1))
    run.log("Done in %d min %d s. Report: %s" % (secs // 60, secs % 60, run.p("report", "report.html")))
    return run, 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    _, code = main()
    sys.exit(code)
