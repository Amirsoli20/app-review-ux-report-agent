"""Code-composed report sections: reliability (from gate.json and the audit) and workflow (from run.json)."""
import time

from common import read_json, read_yaml


def fmt(n):
    return f"{int(n):,}"


def reliability(run, stats, audit):
    gate = read_json(run.p("validation", "gate.json"))
    det = stats["detail"]
    rep = stats["report"]
    order = ["coverage", "agreement_overall", "quote", "schema", "agreement_issue", "sample_size"]
    gates = [{"status": g["status"], "text": g["text"]} for k in order for g in gate["gates"] if g["id"] == k]
    gates.append({"status": "pass" if audit["unresolved"] == 0 else "flag",
                  "text": "Report audit: %s numbers checked against the data, %d mismatches%s" % (
                      fmt(audit["numbers_checked"]), audit["mismatches"],
                      ("; %d rewritten, %d replaced by code text" % (audit["rewritten"], audit["replaced_by_code_text"])) if audit["mismatches"] or audit["replaced_by_code_text"] else "")})
    gates.append({"status": "pass" if audit["unresolved"] == 0 else "flag",
                  "text": "Voice audit: %d prescriptive words found%s" % (audit["voice_matches"], ", all rewritten" if audit["voice_matches"] and not audit["unresolved"] else "")})
    if det["category_size_flags"]:
        gates.append({"status": "flag", "text": "Categories below 2 issues and 2%% of reviews: %s" % ", ".join(det["category_size_flags"])})
    struct = read_yaml(run.p("issues", "structure.yaml"))
    if struct.get("fallback"):
        gates.append({"status": "flag", "text": "Issue naming failed twice; issues, categories and stages come from the code fallback"})
    cs = [c for c in rep["countries"]]
    limits = []
    if cs:
        lo, hi = min(cs, key=lambda c: c["days"]), max(cs, key=lambda c: c["days"])
        per = run.record()["settings"]["reviews_per_country"]
        if len(cs) > 1:
            limits.append("At most %s reviews per country: %s covers %d days, %s %d days." % (fmt(per), lo["name"], lo["days"], hi["name"], hi["days"]))
        else:
            limits.append("At most %s reviews per country: %s covers %d days." % (fmt(per), lo["name"], lo["days"]))
    limits.append("Labels are an AI's reading of the text. Interval widths do not include labeling error.")
    limits.append("Ratings without a written review are not included.")
    limits.append("Apple's review data does not record the app version; each review's version is the one released most recently before its date.")
    if det["hidden_countries"]:
        limits.append("Countries with fewer than 50 reviews (%s) count in weighted shares but are not shown on their own." % ", ".join(det["hidden_countries"]))
    if det["low_blocker_stages"]:
        limits.append("Blocker shares for %s rest on fewer than 30 problem statements." % ", ".join(det["low_blocker_stages"]))
    if det["time"].get("hidden"):
        limits.append("Issues over time is hidden: fewer than 6 weeks have at least 50 reviews.")
    return {"gates": gates, "limits": limits}


def workflow(run, stats, audit):
    rec = run.record()
    c = rec.get("counts", {})
    app = read_json(run.p("app.json"))
    res = app.get("resolution", {})
    rep, det = stats["report"], stats["detail"]
    groups = c.get("group", {})
    nm = c.get("name", {})
    ex = c.get("extract", {})
    q = c.get("quotes", {})
    asg = c.get("assign", {})
    sp = c.get("second_pass", {})
    steps = []
    if res.get("method") == "search":
        alts = res.get("alternatives") or []
        nxt = ("; the next match has %s" % fmt(alts[0]["rating_count"])) if alts else ""
        t = 'Searched "%s": %d matches. Picked id%s (%s ratings%s).' % (res["term"], res["n_matches"], app["app_id"], fmt(res["chosen"]["rating_count"]), nxt)
    else:
        t = "Used App Store id%s from the input." % app["app_id"]
    t += " Read the listing: %s category, %d features named in the description, notes for %d releases." % (
        app["category"], len(app.get("listed_features") or []), len(app["versions"]))
    steps.append({"actor": "code", "title": "Found the app and read its listing", "text": t})
    cs = read_json(run.p("countries.json"))
    if rec["input"].get("country"):
        t = "Country given in the input: %s." % rec["input"]["country"].upper()
    else:
        t = "Looked up rating counts in %d countries. Kept %s: %.1f%% of all ratings." % (
            cs["candidates"], ", ".join(x["code"] for x in cs["countries"]), 100 * cs["coverage"])
    steps.append({"actor": "code", "title": "Chose countries", "text": t})
    cl, co = c.get("clean", {}), c.get("collect", {})
    dups = cl.get("dup_id", 0) + cl.get("dup_text", 0)
    steps.append({"actor": "code", "title": "Collected reviews",
                  "text": "%s review pages, %s reviews. %d duplicates removed, %s kept.%s" % (
                      fmt(co.get("pages", 0)), fmt(co.get("reviews", 0)), dups, fmt(cl.get("kept", 0)),
                      (" Failed: %s." % ", ".join(co["failed_countries"])) if co.get("failed_countries") else "")})
    steps.append({"actor": "ai", "title": "Split into statements",
                  "text": "%s reviews became %s statements in %d batches. Each got an issue phrase, a where-in-the-app phrase, type, feeling and severity. %d reviews had no meaningful text." % (
                      fmt(ex.get("reviews", 0)), fmt(ex.get("statements", 0)), ex.get("batches", 0), ex.get("excluded_reviews", 0))})
    steps.append({"actor": "code", "title": "Checked quotes",
                  "text": "%d statements quoted words not in the review. %d fixed on retry, %d removed: %s kept." % (
                      q.get("failed", 0), q.get("fixed", 0), q.get("removed", 0), fmt(q.get("kept", 0)))})
    steps.append({"actor": "code", "title": "Grouped phrases",
                  "text": "%s phrases, %s distinct. Embeddings and clustering formed %s clusters and %s single-phrase groups." % (
                      fmt(groups.get("n_phrases", 0)), fmt(groups.get("n_distinct", 0)), fmt(groups.get("n_clusters", 0)),
                      fmt(groups.get("n_groups", 0) - groups.get("n_clusters", 0)))})
    steps.append({"actor": "ai", "title": "Named issues and built the app's structure",
                  "text": "%s groups became %d issues. From the issues, the where-in-the-app phrases and the listing, the agent formed %d categories and a %d-stage journey; %d stages match the listing. Each issue got a likely owning team." % (
                      fmt(nm.get("groups", 0)), nm.get("issues", 0), nm.get("categories", 0), nm.get("stages", 0), nm.get("stages_from_listing", 0))})
    retry = c.get("assign_retry")
    steps.append({"actor": "ai", "title": "Confirmed labels",
                  "text": "Every statement checked against the issue list and the journey. %s moved to a better issue, %s set to other.%s" % (
                      fmt(asg.get("moved", 0)), fmt(asg.get("set_to_other", 0)),
                      (" Coverage retry re-assigned %s other statements." % fmt(retry["assigned"])) if retry else "")})
    steps.append({"actor": "ai", "title": "Second pass",
                  "text": "%s statements (%.0f%%) labeled again with a different prompt. κ = %.2f." % (
                      fmt(sp.get("n", 0)), 100 * sp.get("n", 0) / max(1, rep["meta"]["n_statements_kept"]), rep["meta"]["kappa"])})
    steps.append({"actor": "code", "title": "Computed statistics",
                  "text": "Stratified shares, intervals and tests for %d issues, %d categories, %d stages%s and %d countries." % (
                      len(rep["issues"]), len(rep["sentiment"]["categories"]), len(rep["journey"]["stages"]),
                      (", %d weeks" % len(rep["time"]["weeks"])) if "time" in rep else "", len(rep["countries"]))})
    secs = int(rec.get("seconds_before", 0) + time.time() - rec.get("t_process", rec.get("t0", time.time())))
    steps.append({"actor": "ai", "title": "Wrote and audited",
                  "text": "Text written around the numbers. %s numbers checked against the data, %d mismatches. Run time %d min %d s." % (
                      fmt(audit["numbers_checked"]), audit["unresolved"], secs // 60, secs % 60)})
    funnel = [{"label": "Issue phrases written", "n": rep["meta"]["n_statements_kept"]},
              {"label": "Distinct phrases", "n": groups.get("n_distinct", 0)},
              {"label": "Clusters", "n": groups.get("n_clusters", 0)},
              {"label": "Named issues", "n": det["issues_defined"]},
              {"label": "Recurring issues", "n": len(rep["issues"])}]
    return {"steps": steps, "funnel": funnel}
