"""Steps 12 to 15 on a fixed synthetic run (no AI): known shares, the over-time test, and a valid rendered report."""
import datetime as dt
import json
import random
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_numbers  # noqa: E402
import render_report  # noqa: E402
import stats  # noqa: E402
import write_report  # noqa: E402
from common import Run, load_settings, validate, write_json, write_jsonl, write_yaml  # noqa: E402

COUNTRIES = [("US", 600000, 0.6), ("GB", 300000, 0.3), ("DE", 100000, 0.1)]
ISSUES = [  # id, type, stage, base rate, recent rate, star
    ("crash", "Bug report", "open", 0.06, 0.20, 1),
    ("slow", "Complaint", "browse", 0.08, 0.08, 2),
    ("fee", "Complaint", "pay", 0.05, 0.05, 2),
    ("dark", "Feature request", None, 0.04, 0.04, 4),
    ("easy", "Praise", "browse", 0.20, 0.20, 5),
    ("fast", "Praise", "pay", 0.10, 0.10, 5),
]


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    rng = random.Random(7)
    path = tmp_path_factory.mktemp("run")
    run = Run(path)
    s = load_settings({"reviews_per_country": 500})
    last = dt.date(2026, 10, 18)
    reviews, sts = [], []
    for cc, _, _ in COUNTRIES:
        for k in range(300 if cc != "DE" else 120):
            d = last - dt.timedelta(days=rng.randrange(84))
            recent = (last - d).days < 28
            rid = "%s-%d" % (cc, k)
            mine = [i for i in ISSUES if rng.random() < (i[4] if recent else i[3])]
            star = min([i[5] for i in mine if i[1] != "Praise"] or [rng.choice([4, 5])])
            reviews.append({"review_id": rid, "country": cc, "rating": star, "title": "t", "body": "b", "language": "en",
                            "app_version": "2.0" if d >= dt.date(2026, 9, 21) else "1.9", "version_inferred": True,
                            "date": d.isoformat(), "author_hash": rid})
            for j, i in enumerate(mine):
                typ = i[1]
                sts.append({"statement_id": "%s_s%d" % (rid, j + 1), "review_id": rid, "text_span": "%s statement" % i[0],
                            "translation": None, "issue_phrase": i[0] + " phrase", "location_phrase": "general",
                            "issue_id": i[0], "stage_id": i[2] or "none", "statement_type": typ,
                            "sentiment": "Positive" if typ == "Praise" else "Neutral" if typ == "Feature request" else "Negative",
                            "severity": "Blocker" if typ == "Bug report" else "Minor" if typ == "Complaint" else None,
                            "ux_dimension": "Reliability", "confidence": 0.9, "group_id": "g" + i[0],
                            "proposed_issue": i[0], "second_pass": None})
    write_jsonl(run.p("clean", "reviews.jsonl"), reviews, "review")
    write_jsonl(run.p("labels", "final.jsonl"), sts, "statement")
    tot = sum(c[1] for c in COUNTRIES)
    write_json(run.p("countries.json"), {"countries": [{"code": c, "name": c, "ratings": r, "weight": r / tot, "store_rating": 4.1} for c, r, _ in COUNTRIES],
                                         "candidates": 50, "coverage": 0.85, "target": 0.8})
    write_json(run.p("clean", "windows.json"), {c: {"label": "Jul 27 to Oct 18", "days": 84, "n": 300, "languages": {"en": 300}} for c, _, _ in COUNTRIES})
    app = {"app_id": "1", "name": "Testapp: Shop", "app_short": "Testapp", "developer": "Dev", "category": "Shopping", "price": 0.0,
           "price_label": "Free, no in-app purchases", "in_app_purchases": [], "description": "A test app.\n\nSecond paragraph.",
           "listed_features": ["Search"], "languages": ["English"], "listing_country": "US",
           "versions": [{"version": "2.0", "date": "2026-09-21", "notes": "New."}, {"version": "1.9", "date": "2026-07-01", "notes": "Old."}],
           "store_rating": {"US": 4.1}, "store_rating_count": {"US": 600000}, "resolution": {"method": "id"}}
    write_json(run.p("app.json"), app, "app")
    write_yaml(run.p("issues", "issues.yaml"), {"issues": [
        {"issue_id": i[0], "name": i[0].title() + " issue name", "short_name": i[0] + " short", "definition": "d", "category_id": "c%d" % (k % 5),
         "dominant_type": i[1], "stage_id": i[2], "ux_dimension": "Reliability", "team_primary": "UX design",
         "team_secondary": [], "source_groups": ["g" + i[0]]} for k, i in enumerate(ISSUES)]})
    write_yaml(run.p("issues", "structure.yaml"), {
        "listed_features": ["Search"], "fallback": False,
        "categories": [{"id": "c%d" % k, "name": "Area %d" % k, "issue_ids": [i[0] for j, i in enumerate(ISSUES) if j % 5 == k]} for k in range(5)],
        "stages": [{"id": x, "order": n + 1, "name": x.title(), "desc": "covers " + x, "source": "reviews_only", "listing_words": []}
                   for n, x in enumerate(["open", "browse", "pay", "track"])]})
    keys = sorted({st["issue_phrase"] for st in sts})
    np.savez_compressed(run.p("issues", "phrase_vectors.npz"), keys=np.array(keys, dtype=object),
                        vectors=np.stack([np.eye(len(keys))[k] for k in range(len(keys))]).astype(np.float32))
    write_json(run.p("validation", "validation.json"), {"n": 100, "kappa": {"issue_id": 0.82}, "per_issue": {"crash": {"kappa": 0.6}}})
    write_json(run.p("validation", "gate.json"), {"repetition_threshold": 5, "gates": [{"id": "coverage", "status": "pass", "text": "ok"}]})
    run.update_record(input={"app": "1", "country": None}, settings=s, counts={"extract": {"statements": len(sts)}}, steps={}, t0=0)
    return run


def test_stats_numbers(run):
    rep = stats.main(run)
    validate_ok = {i["id"]: i for i in rep["issues"]}
    assert set(validate_ok) == {i[0] for i in ISSUES}
    reviews = [json.loads(l) for l in open(run.p("clean", "reviews.jsonl"))]
    sts = [json.loads(l) for l in open(run.p("labels", "final.jsonl"))]
    # stratified share equals the weighted mean of the per-country shares
    crash = validate_ok["crash"]
    n = {c: sum(r["country"] == c for r in reviews) for c, _, _ in COUNTRIES}
    k = {c: len({st["review_id"] for st in sts if st["issue_id"] == "crash" and st["review_id"].startswith(c)}) for c, _, _ in COUNTRIES}
    w = {c: wt for c, _, wt in COUNTRIES}
    assert crash["wshare"] == pytest.approx(100 * sum(w[c] * k[c] / n[c] for c in n), abs=0.01)
    assert crash["counts"] == [k[c] for c, _, _ in COUNTRIES]
    assert crash["kappa"] == 0.6 and validate_ok["slow"]["kappa"] == 0.82
    assert crash["severity"][0] == sum(1 for st in sts if st["issue_id"] == "crash")
    assert validate_ok["easy"]["type"] == "Praise" and "n_high" in validate_ok["easy"]
    assert validate_ok["dark"]["type"] == "Request" and validate_ok["dark"]["severity"] is None
    # the over-time section exists and the planted rise of "crash" is the only significant change
    t = rep["time"]
    assert len(t["weeks"]) >= 12 and t["recent_from"] == len(t["weeks"]) - 4
    by = {sr["id"]: sr for sr in t["series"]}
    assert by["crash"]["recent"] > by["crash"]["earlier"] and by["crash"]["p_adj"] < 0.001
    assert by["fee"]["p_adj"] > 0.05
    assert any(r["label"].startswith("v2.0") for r in t["releases"])
    mix_total = sum(sum(v) for v in rep["mix"].values())
    assert mix_total == len(reviews)


def test_report_data_valid_and_renders(run):
    st = json.load(open(run.p("stats", "stats.json")))
    slots = write_report.fallback_slots(st)
    assert not write_report.check_slots(slots, write_report.measures_used(st["report"]))
    write_json(run.p("report", "slots.draft.json"), {"source": "fallback", "slots": slots})

    class NoAI:  # the audit must pass the code-written text without calling the auditor
        def __init__(self, *a, **k):
            self.name, self.version = "report-auditor", "x"
    check_numbers.llm.Agent = NoAI
    out = check_numbers.main(run)
    assert out["mismatches"] == 0 and out["voice_matches"] == 0
    d = json.load(open(run.p("report", "report_data.json")))
    validate(d, "report-data")
    assert not render_report.check_refs(d)
    render_report.main(run.p("report", "report_data.json"), render_report.TEMPLATE, run.p("report", "report.html"))
    assert "<meta charset=utf8>" in run.p("report", "report.html").read_text(encoding="utf-8")
