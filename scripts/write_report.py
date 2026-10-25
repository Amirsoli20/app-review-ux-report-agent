"""Step 13. Build report_data.json: numbers from stats.json, text slots from the report-writer sub-agent.

The report-writer fills only the text slots of section 12.4 (summary, patterns, glossary_examples).
Short names and stage descriptions come from step 8. Every other value is copied from stats.json.
-> report/report_data.draft.json
"""
import copy
import re
import sys

import llm
from common import Run, read_json, run_settings, words, write_json

CAPTION_OPEN = "One review can mention several problems, so the bars add up to more than the number of reviews."
BANNED = re.compile(r"\b(should|recommend\w*|priorit\w*|fix|fixes|fixing|must|ought|we suggest|users?|customers?|need to)\b", re.I)


def f1(x):
    return "%.1f" % x


def measures_used(rep):
    multi = len(rep["countries"]) > 1
    has_time = "time" in rep
    m = ["stratified_share", "ci", "mean_median_mode", "sd", "rating_gap", "cohens_d", "net_sentiment", "blocker_share", "kappa"]
    if multi:
        m[4:4] = ["cv"]
        m.append("chi_square")
    if has_time:
        m.append("cmh")
    if multi or has_time:
        m.append("holm")
    return m


def facts(stats):
    rep, det = stats["report"], stats["detail"]
    byid = {i["id"]: i for i in rep["issues"]}
    cn = [c["code"] for c in rep["countries"]]

    def issue_facts(i):
        d = det["issues"][i["id"]]
        top = max(range(len(cn)), key=lambda k: i["per_country"][k]) if cn else 0
        f = {"id": i["id"], "name": i["name"], "type": i["type"], "category": i["category"], "stage": i["stage"],
             "reviews": i["n"], "weighted_share_pct": i["wshare"], "ci_pct": i["wci"], "pooled_share_pct": round(d["pooled_share"], 1),
             "stars_mean": i["stars"]["mean"], "stars_sd": i["stars"]["sd"], "stars_median": i["stars"]["median"],
             "stars_mode": i["stars"]["mode"], "mean_stars_without": round(d["mean_without"], 2), "rating_gap": i["gap"],
             "gap_ci": i["gap_ci"], "cohen_d": i["cohen_d"], "kappa": i["kappa"]}
        if len(cn) > 1:
            f.update(highest_country=cn[top], highest_country_share_pct=i["per_country"][top], cv_pct=i["cv"],
                     country_p_holm=i["p"], cramers_v=i["cramer"])
        if i["type"] == "Praise":
            f["reviews_4_5_stars"] = i["n_high"]
        else:
            f["reviews_1_2_stars"] = i["n_low"]
            if i["severity"]:
                f["severity_blocker_major_minor_cosmetic"] = i["severity"]
        return f
    probs = [i for i in rep["issues"] if i["type"] != "Praise"]
    strs = [i for i in rep["issues"] if i["type"] == "Praise"]
    out = {"app": rep["meta"]["app_short"], "reviews": rep["meta"]["n_reviews"], "statements": rep["meta"]["n_statements_kept"],
           "countries": [{"code": c["code"], "name": c["name"], "reviews": c["n"], "weight_pct": c["weight"]} for c in rep["countries"]],
           "period": [rep["meta"]["period_start"], rep["meta"]["period_end"]], "mean_stars": rep["meta"]["mean_stars"],
           "store_rating": rep["about"]["store_rating"], "overall_kappa": rep["meta"]["kappa"],
           "problems": [issue_facts(i) for i in probs[:8]], "strengths": [issue_facts(i) for i in strs[:5]],
           "review_mix": {"high_star_reviews_with_problem_pct": round(det["high_star_with_problem"]["p"], 1),
                          "ci": [round(det["high_star_with_problem"]["lo"], 1), round(det["high_star_with_problem"]["hi"], 1)],
                          "low_star_reviews_with_praise_pct": round(det["low_star_with_praise"]["p"], 1)},
           "journey": [{"stage": s["name"], "net_sentiment": s["net"], "statements": s["total"], "blocker_share_pct": s["blocker"],
                        "top_problem": byid[s["top_problem"]]["name"] if s["top_problem"] else None,
                        "top_strength": byid[s["top_strength"]]["name"] if s["top_strength"] else None} for s in rep["journey"]["stages"]],
           "categories": [{"name": c["name"], "net_sentiment": c["net"], "statements": c["total"]} for c in rep["sentiment"]["categories"]],
           "kappa_lowest": sorted([{"name": i["name"], "kappa": i["kappa"]} for i in rep["issues"]], key=lambda x: x["kappa"])[:3],
           "measures_to_explain": measures_used(rep)}
    if "time" in rep:
        out["over_time"] = {"recent_weeks": len(rep["time"]["weeks"]) - rep["time"]["recent_from"],
                            "tests": [{"name": byid[s["id"]]["name"], "earlier_pct": s["earlier"], "recent_pct": s["recent"],
                                       "diff_pp": s["diff"], "p_holm": s["p_adj"]} for s in rep["time"]["series"]],
                            "releases": [r["label"] for r in rep["time"]["releases"]]}
    if len(rep["countries"]) > 1:
        out["country_tests"] = len(probs)
    return out


def check_slots(obj, required_measures):
    probs = []
    sm = obj.get("summary")
    if not isinstance(sm, list) or not 4 <= len(sm) <= 6:
        probs.append("summary must have 4 to 6 items")
    else:
        for t in sm:
            if not isinstance(t, str) or words(t) > 45 or len(t) > 330:
                probs.append("summary item over 45 words or 330 characters: %s" % str(t)[:60])
    pt = obj.get("patterns") or {}
    for k in ("problems_title", "strengths_title"):
        t = pt.get(k)
        if not isinstance(t, str) or not t or words(t) > 14 or len(t) > 90:
            probs.append("patterns.%s must be at most 14 words and 90 characters" % k)
    cap = pt.get("caption")
    if not isinstance(cap, str) or not cap.startswith(CAPTION_OPEN) or words(cap) > 70 or len(cap) > 480:
        probs.append("patterns.caption must open with the fixed sentence and be at most 70 words and 480 characters")
    ge = obj.get("glossary_examples") or {}
    if set(ge) != set(required_measures):
        probs.append("glossary_examples keys must be exactly: %s" % ", ".join(required_measures))
    for k, t in ge.items():
        if not isinstance(t, str) or words(t) > 25 or len(t) > 180:
            probs.append("glossary_examples.%s over 25 words or 180 characters" % k)
    for t in slot_texts(obj):
        m = BANNED.search(t)
        if m:
            probs.append("banned wording %r in: %s" % (m.group(0), t[:60]))
    return probs


def slot_texts(obj):
    out = list(obj.get("summary") or [])
    pt = obj.get("patterns") or {}
    out += [pt.get("problems_title") or "", pt.get("strengths_title") or "", pt.get("caption") or ""]
    out += list((obj.get("glossary_examples") or {}).values())
    return [t for t in out if isinstance(t, str)]


# ---------- deterministic fallback text (used when the writer or the audit cannot produce a valid slot) ----------

def fallback_slots(stats):
    rep, det = stats["report"], stats["detail"]
    probs = [i for i in rep["issues"] if i["type"] != "Praise"]
    strs = [i for i in rep["issues"] if i["type"] == "Praise"]
    byid = {i["id"]: i for i in rep["issues"]}
    sm = []
    if probs:
        p = probs[0]
        sm.append("The most raised problem is **%s**: %s%% of reviews (95%% CI %s to %s%%). Reviews that raise it average %.2f stars, against %.2f for the rest." % (
            p["name"], f1(p["wshare"]), f1(p["wci"][0]), f1(p["wci"][1]), p["stars"]["mean"], det["issues"][p["id"]]["mean_without"]))
    if "time" in rep:
        sig = [s for s in rep["time"]["series"] if s["p_adj"] < 0.05]
        if sig:
            s = max(sig, key=lambda x: abs(x["diff"]))
            sm.append("**%s** went from %s%% of reviews in earlier weeks to %s%% in the last four (compared within countries, adjusted p %s)." % (
                byid[s["id"]]["name"], f1(s["earlier"]), f1(s["recent"]), "< 0.001" if s["p_adj"] < 0.001 else "= %.3f" % s["p_adj"]))
        else:
            sm.append("None of the %d most raised problems changed significantly between earlier weeks and the last four (adjusted p of 0.05 or more)." % len(rep["time"]["series"]))
    if strs:
        s = strs[0]
        sm.append("The most raised strength is **%s**: %s%% of reviews (95%% CI %s to %s%%)." % (s["name"], f1(s["wshare"]), f1(s["wci"][0]), f1(s["wci"][1])))
    h = det["high_star_with_problem"]
    sm.append("%s%% of 4 and 5 star reviews still report at least one problem (95%% CI %s to %s%%)." % (f1(h["p"]), f1(h["lo"]), f1(h["hi"])))
    st = rep["journey"]["stages"]
    if st:
        lo, hi = min(st, key=lambda x: x["net"]), max(st, key=lambda x: x["net"])
        sm.append("Along the journey, **%s** is the most negative stage (net sentiment %+.0f) and **%s** the most positive (%+.0f)." % (
            lo["name"], lo["net"], hi["name"], hi["net"]))
    if len(rep["countries"]) > 1 and probs:
        strong = [i for i in probs if i["p"] < 0.05 and i["cramer"] >= 0.1]
        if strong:
            i = max(strong, key=lambda x: x["cramer"])
            sm.append("**%s** differs most between countries (Cramér's V = %.2f, adjusted p %s)." % (
                i["name"], i["cramer"], "< 0.001" if i["p"] < 0.001 else "= %.3f" % i["p"]))
        else:
            sm.append("No problem differs meaningfully between countries (every Cramér's V under 0.1 or adjusted p of 0.05 or more).")
    while len(sm) < 4:
        sm.append("The report covers %s reviews and %s statements from %d countries." % (
            f"{rep['meta']['n_reviews']:,}", f"{rep['meta']['n_statements_kept']:,}", len(rep["meta"]["countries"])))
    sm = sm[:6]
    pt = {"problems_title": ("%s is the most raised problem" % probs[0]["name"]) if probs else "No recurring problems",
          "strengths_title": ("%s is the most raised strength" % strs[0]["name"]) if strs else "No recurring strengths"}
    for k in ("problems_title", "strengths_title"):
        if words(pt[k]) > 14 or len(pt[k]) > 90:
            pt[k] = ("Most raised problems, by number of reviews" if k == "problems_title" else "Most raised strengths, by number of reviews")
    lowstar = sorted(probs, key=lambda i: -i["n_low"] / max(1, i["n"]))
    cap = CAPTION_OPEN
    if lowstar:
        a = lowstar[0]
        cap += " %s: %d of %d reviews give 1 or 2 stars." % (a["name"], a["n_low"], a["n"])
        if len(lowstar) > 1:
            b = lowstar[-1]
            cap += " %s: %d of %d." % (b["name"], b["n_low"], b["n"])
    if words(cap) > 70 or len(cap) > 480:
        cap = CAPTION_OPEN
    ge = {}
    p = probs[0] if probs else (rep["issues"][0] if rep["issues"] else None)
    if p:
        d = det["issues"][p["id"]]
        ge["stratified_share"] = "%s: %s%% of reviews weighted by country; %s%% (%d of %s) unweighted." % (
            p["name"], f1(p["wshare"]), f1(d["pooled_share"]), p["n"], f"{rep['meta']['n_reviews']:,}")
        ge["ci"] = "%s: %s%% of reviews, 95%% CI %s to %s%%." % (p["name"], f1(p["wshare"]), f1(p["wci"][0]), f1(p["wci"][1]))
        ge["mean_median_mode"] = "Reviews raising %s: mean %.2f stars, median %d, mode %d." % (p["name"], p["stars"]["mean"], p["stars"]["median"], p["stars"]["mode"])
        ge["sd"] = "Stars on reviews raising %s have SD %.2f." % (p["name"], p["stars"]["sd"])
        ge["cv"] = "Across countries, %s has CV %.0f%%." % (p["name"], p["cv"])
        ge["rating_gap"] = "%s: %+.2f stars; reviews mentioning it average %.2f, the rest %.2f." % (p["name"], p["gap"], p["stars"]["mean"], d["mean_without"])
        ge["cohens_d"] = "%s: d = %.2f." % (p["name"], p["cohen_d"])
        ge["chi_square"] = "%s: Cramér's V = %.2f, adjusted p %s." % (p["name"], p["cramer"], "< 0.001" if p["p"] < 0.001 else "= %.3f" % p["p"])
        ge["kappa"] = "Overall κ = %.2f. %s has κ = %.2f." % (rep["meta"]["kappa"], p["name"], p["kappa"])
    if st:
        lo = min(st, key=lambda x: x["net"])
        ge["net_sentiment"] = "%s: net sentiment %+.0f across %d statements." % (lo["name"], lo["net"], lo["total"])
        b = max(st, key=lambda x: x["blocker"])
        ge["blocker_share"] = "At %s, %d%% of problem statements describe a blocker, the highest of any stage." % (b["name"], b["blocker"])
    if "time" in rep and rep["time"]["series"]:
        s = rep["time"]["series"][0]
        ge["cmh"] = "%s: %s%% of reviews in earlier weeks and %s%% in the last four, adjusted p %s." % (
            byid[s["id"]]["name"], f1(s["earlier"]), f1(s["recent"]), "< 0.001" if s["p_adj"] < 0.001 else "= %.2f" % s["p_adj"])
    ge["holm"] = "Applied within each family of tests (over time and between countries). Below 0.05 after adjustment counts as a significant difference."
    need = measures_used(rep)
    ge = {k: ge.get(k, "Not available for this report.") for k in need}
    return {"summary": sm, "patterns": dict(pt, caption=cap), "glossary_examples": ge}


def merge_slots(got, fb, need):
    """Keep every writer slot that passes its own check; replace the others with the code-written slot."""
    if not isinstance(got, dict):
        return fb, ["all"]
    out, replaced = {"summary": [], "patterns": {}, "glossary_examples": {}}, []
    sm = got.get("summary") if isinstance(got.get("summary"), list) else []
    for k, t in enumerate(sm[:6]):
        ok = isinstance(t, str) and words(t) <= 45 and len(t) <= 330 and not BANNED.search(t)
        out["summary"].append(t if ok else fb["summary"][min(k, len(fb["summary"]) - 1)])
        replaced += [] if ok else ["summary[%d]" % k]
    if len(out["summary"]) < 4:
        out["summary"] = fb["summary"]
        replaced.append("summary")
    pt = got.get("patterns") if isinstance(got.get("patterns"), dict) else {}
    for k in ("problems_title", "strengths_title"):
        t = pt.get(k)
        ok = isinstance(t, str) and t and words(t) <= 14 and len(t) <= 90 and not BANNED.search(t)
        out["patterns"][k] = t if ok else fb["patterns"][k]
        replaced += [] if ok else ["patterns." + k]
    cap = pt.get("caption")
    ok = isinstance(cap, str) and cap.startswith(CAPTION_OPEN) and words(cap) <= 70 and len(cap) <= 480 and not BANNED.search(cap)
    out["patterns"]["caption"] = cap if ok else fb["patterns"]["caption"]
    replaced += [] if ok else ["patterns.caption"]
    ge = got.get("glossary_examples") if isinstance(got.get("glossary_examples"), dict) else {}
    for k in need:
        t = ge.get(k)
        ok = isinstance(t, str) and t and words(t) <= 25 and len(t) <= 180 and not BANNED.search(t)
        out["glossary_examples"][k] = t if ok else fb["glossary_examples"][k]
        replaced += [] if ok else ["glossary_examples." + k]
    return out, replaced


def assemble(stats, slots, notice=None):
    d = copy.deepcopy(stats["report"])
    d["summary"] = slots["summary"]
    d["patterns"] = slots["patterns"]
    d["glossary_examples"] = slots["glossary_examples"]
    d["meta"]["notice"] = notice
    return d


def main(run):
    s = run_settings(run)
    stats = read_json(run.p("stats", "stats.json"))
    need = measures_used(stats["report"])
    payload = {"facts": facts(stats), "required_glossary_keys": need}
    agent = llm.Agent("report-writer", s)
    run.log("Writing text slots (%s)." % agent.model)
    fb = fallback_slots(stats)
    try:
        got = llm.call(agent, payload, run, None, lambda o: check_slots(o, need), tag="report text", return_last=True)
    except RuntimeError as e:
        run.log("report-writer failed twice (%s); using code-written fallback text." % str(e)[:200])
        got = None
    slots, replaced = merge_slots(got, fb, need)
    source = "fallback" if got is None else "report-writer" + (" (%d slots from code)" % len(replaced) if replaced else "")
    if replaced and got is not None:
        run.log("Kept the writer's text; %d slots over their limits replaced by code text: %s" % (len(replaced), ", ".join(replaced)))
    write_json(run.p("report", "slots.draft.json"), {"source": source, "slots": slots, "facts": payload["facts"]})
    run.update_record(prompts={agent.name: agent.version}, counts={"write": {"source": source}})
    return slots


if __name__ == "__main__":
    main(Run(sys.argv[1]))
