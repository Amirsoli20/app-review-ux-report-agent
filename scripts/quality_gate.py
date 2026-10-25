"""Step 11 (and the coverage retry). Quality gates of section 13 -> validation/gate.json.

No gate stops the run. Each gate records pass or flag; the coverage gate triggers one automatic retry
(regroup the "other" statements with a smaller minimum cluster size, add issues, re-assign them).
"""
import collections
import math
import sys

import llm
from common import Run, read_json, read_jsonl, read_yaml, run_settings, write_json, write_jsonl, write_yaml


def other_share(run):
    sts = read_jsonl(run.p("labels", "final.jsonl"))
    return sum(st["issue_id"] == "other" for st in sts) / max(1, len(sts)), sts


def coverage_retry(run):
    """Regroup the 'other' statements once with min_cluster_size_retry and add the issues found (gate 3)."""
    import assign_labels
    import group_phrases
    from name_issues import build_payload, apply_routing_rules
    s = run_settings(run)
    share, sts = other_share(run)
    others = [st for st in sts if st["issue_id"] == "other"]
    groups, _ = group_phrases.group(run, others, int(s["min_cluster_size_retry"]), prefix="r")
    clustered = [g for g in groups if g["clustered"]]
    run.log("Coverage retry: %d other statements (%.1f%%) regrouped with minimum cluster size %d: %d clusters." % (
        len(others), 100 * share, s["min_cluster_size_retry"], len(clustered)))
    if not clustered:
        return {"added": 0, "before": share, "after": share}
    issues = read_yaml(run.p("issues", "issues.yaml"))["issues"]
    structure = read_yaml(run.p("issues", "structure.yaml"))
    app = read_json(run.p("app.json"))
    n_reviews = len(read_jsonl(run.p("clean", "reviews.jsonl")))
    existing = {"issues": [{k: i[k] for k in ("issue_id", "name", "definition", "category_id")} for i in issues],
                "categories": [{"id": c["id"], "name": c["name"]} for c in structure["categories"]],
                "stages": [{"id": st["id"], "name": st["name"]} for st in structure["stages"]]}
    payload = build_payload(app, clustered, others, n_reviews, s, existing=existing)
    payload["single_phrases"] = []
    agent = llm.Agent("issue-namer", s)

    def check(obj):
        from name_issues import check_output
        return check_output(obj, payload, s, extend=True)
    try:
        out = llm.call(agent, payload, run, None, check, tag="extend issues")
    except RuntimeError as e:
        run.log("Coverage retry: issue-namer failed (%s)." % str(e)[:200])
        return {"added": 0, "before": share, "after": share, "error": str(e)[:300]}
    new = out["issues"]
    by_group = {g: i["issue_id"] for i in new for g in i["source_groups"]}
    by_issue = collections.defaultdict(list)
    for st in others:
        st["proposed_issue"] = by_group.get(st["group_id"], "other")
        by_issue[st["proposed_issue"]].append(st)
    for i in new:
        apply_routing_rules(i, by_issue.get(i["issue_id"], []))
        i["added_in_retry"] = True
    cats = {c["id"]: c for c in structure["categories"]}
    for i in new:
        cats[i["category_id"]]["issue_ids"].append(i["issue_id"])
    write_yaml(run.p("issues", "issues.yaml"), {"issues": issues + new})
    write_yaml(run.p("issues", "structure.yaml"), structure)
    by_id = {st["statement_id"]: st for st in others}
    for st in sts:
        if st["statement_id"] in by_id:
            st.update(proposed_issue=by_id[st["statement_id"]]["proposed_issue"], group_id=by_id[st["statement_id"]]["group_id"])
    write_jsonl(run.p("labels", "final.jsonl"), sts, "statement")
    assign_labels.main(run, subset_ids={st["statement_id"] for st in others})
    after, _ = other_share(run)
    run.log("Coverage retry added %d issues; other is now %.1f%% of statements." % (len(new), 100 * after))
    return {"added": len(new), "before": share, "after": after}


def main(run, retry_info=None):
    s = run_settings(run)
    rec = run.record()
    counts = rec.get("counts", {})
    sts = read_jsonl(run.p("labels", "final.jsonl"))
    reviews = read_jsonl(run.p("clean", "reviews.jsonl"))
    val = read_json(run.p("validation", "validation.json"))
    issues = read_yaml(run.p("issues", "issues.yaml"))["issues"]
    gates = []
    ex = counts.get("extract", {})
    gates.append({"id": "schema", "status": "flag" if ex.get("failed_batches") else "pass",
                  "text": "Schema check: %d records failed after one resend and were dropped%s" % (
                      ex.get("dropped_records", 0), "; %d batches failed" % ex["failed_batches"] if ex.get("failed_batches") else ""),
                  "detail": ex})
    q = counts.get("quotes", {})
    gates.append({"id": "quote", "status": "pass",
                  "text": "Quotes not found in review: %d; %d fixed on retry, %d removed" % (q.get("failed", 0), q.get("fixed", 0), q.get("removed", 0)),
                  "detail": q})
    share = sum(st["issue_id"] == "other" for st in sts) / max(1, len(sts))
    gates.append({"id": "coverage", "status": "pass" if share <= s["other_limit"] else "flag",
                  "text": "Statements with no issue: %.1f%% (limit %.0f%%)%s" % (
                      100 * share, 100 * s["other_limit"],
                      "; regrouped once, %d issues added" % retry_info["added"] if retry_info else ""),
                  "detail": {"other_share": share, "retry": retry_info}})
    k = val["kappa"]["issue_id"]
    gates.append({"id": "agreement_overall", "status": "pass" if (k or 0) >= s["kappa_flag"] else "flag",
                  "text": "Overall κ = %s (limit %.2f)" % ("n/a" if k is None else "%.2f" % k, s["kappa_flag"]), "detail": val["kappa"]})
    thr = max(int(s["repetition_min_reviews"]), math.ceil(float(s["repetition_min_share"]) * len(reviews)))
    rv = collections.defaultdict(set)
    for st in sts:
        rv[st["issue_id"]].add(st["review_id"])
    names = {i["issue_id"]: i["name"] for i in issues}
    recurring = [i for i in names if len(rv.get(i, ())) >= thr]
    low = [(i, val["per_issue"].get(i, {}).get("kappa")) for i in recurring]
    low = [(i, x) for i, x in low if x is not None and x < s["kappa_flag"]]
    gates.append({"id": "agreement_issue", "status": "flag" if low else "pass",
                  "text": ("%d issue%s below κ %.2f: %s" % (len(low), "" if len(low) == 1 else "s", s["kappa_flag"],
                                                            ", ".join("%s (%.2f)" % (names[i], x) for i, x in low)))
                  if low else "Every recurring issue has κ of at least %.2f" % s["kappa_flag"],
                  "detail": {i: x for i, x in low}})
    per_c = collections.Counter(r["country"] for r in reviews)
    per_v = collections.Counter(r["app_version"] for r in reviews)
    small_c = sorted(c for c, n in per_c.items() if n < s["min_reviews_country"])
    countries = read_json(run.p("countries.json"))["countries"]
    small_c += sorted(c["code"] for c in countries if c["code"] not in per_c)
    gates.append({"id": "sample_size", "status": "flag" if small_c and len(countries) > 1 else "pass",
                  "text": ("Countries under %d reviews, left out of separate display and tests: %s" % (s["min_reviews_country"], ", ".join(small_c)))
                  if small_c and len(countries) > 1 else "Every country has at least %d reviews" % s["min_reviews_country"],
                  "detail": {"small_countries": small_c, "versions_below_min": sorted(v for v, n in per_v.items() if n < s["min_reviews_version"])}})
    out = {"gates": gates, "repetition_threshold": thr, "other_share": share}
    write_json(run.p("validation", "gate.json"), out)
    run.log("Quality gate: " + "; ".join("%s %s" % (g["id"], g["status"]) for g in gates))
    run.update_record(gates={g["id"]: g["status"] for g in gates})
    return out


if __name__ == "__main__":
    main(Run(sys.argv[1]))
