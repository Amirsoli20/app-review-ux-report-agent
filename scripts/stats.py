"""Step 12. Compute every statistic in the report (section 11) -> stats/stats.json.

stats.json has two parts:
- "report": the numeric keys of report_data.json, already rounded for display (meta, about, countries,
  country_selection, mix, sentiment, issues, board, teams, journey, time, quotes). The report builder
  copies them unchanged; only text slots are added later.
- "detail": full-precision values, per-issue statement and review IDs, lift pairs and everything the
  number audit and the run record need (NFR-4 traceability).
"""
import collections
import datetime as dt
import re
import sys

import numpy as np

import statlib as sl
from common import Run, language_name, read_json, read_jsonl, read_yaml, run_settings, words, write_json

TYPE_MAP = {"Bug report": "Bug", "Complaint": "Complaint", "Feature request": "Request", "Praise": "Praise"}
SEV = ["Blocker", "Major", "Minor", "Cosmetic"]
PII = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d ()-]{7,}\d|#\s?\d{4,}|\b\d{6,}\b|@\w{3,}|https?://", re.I)


def is_problem(st):
    return st["statement_type"] in ("Bug report", "Complaint") or (st["statement_type"] == "Comparison" and st["sentiment"] == "Negative")


def is_praise(st):
    return st["statement_type"] == "Praise" or (st["statement_type"] == "Comparison" and st["sentiment"] == "Positive")


def r1(x):
    return round(float(x), 1)


def r2(x):
    return round(float(x), 2)


def r3(x):
    return round(float(x), 3)


def issue_type(sts):
    t = collections.Counter(st["statement_type"] for st in sts)
    top = t.most_common(1)[0][0] if t else "Complaint"
    if top in TYPE_MAP:
        return TYPE_MAP[top]
    pos = sum(st["sentiment"] == "Positive" for st in sts)
    return "Praise" if pos > len(sts) / 2 else "Complaint"


def first_paragraph(text, limit=700):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    p = paras[0] if paras else ""
    if len(p) < 140 and len(paras) > 1:
        p = p + " " + paras[1]
    p = " ".join(p.split())
    if len(p) > limit:
        cut = p[:limit]
        p = cut[:cut.rfind(". ") + 1] if ". " in cut else cut.rsplit(" ", 1)[0] + "…"
    return p


def short_notes(t, limit=220):
    t = " ".join((t or "").split())
    if len(t) <= limit:
        return t or "No release notes."
    cut = t[:limit]
    i = max(cut.rfind(". "), cut.rfind("! "))
    return cut[:i + 1] if i > 60 else cut.rsplit(" ", 1)[0] + "…"


def monday(d):
    d = dt.date.fromisoformat(d)
    return d - dt.timedelta(days=d.weekday())


def main(run):
    s = run_settings(run)
    seed = s["random_seed"]
    app = read_json(run.p("app.json"))
    csel = read_json(run.p("countries.json"))
    windows = read_json(run.p("clean", "windows.json"))
    reviews = read_jsonl(run.p("clean", "reviews.jsonl"))
    sts = read_jsonl(run.p("labels", "final.jsonl"))
    issues_def = read_yaml(run.p("issues", "issues.yaml"))["issues"]
    structure = read_yaml(run.p("issues", "structure.yaml"))
    val = read_json(run.p("validation", "validation.json"))
    gate = read_json(run.p("validation", "gate.json"))
    rec = run.record()
    counts = rec.get("counts", {})

    N = len(reviews)
    rv_by_id = {r["review_id"]: r for r in reviews}
    sel = csel["countries"]
    W = {c["code"]: c["weight"] for c in sel}
    n_c = collections.Counter(r["country"] for r in reviews)
    for c in sel:
        n_c.setdefault(c["code"], 0)
    disp = [c for c in sel if n_c[c["code"]] >= s["min_reviews_country"]] or [c for c in sel if n_c[c["code"]] > 0]
    disp_codes = [c["code"] for c in disp]
    multi = len(disp) > 1
    stars_all = np.array([r["rating"] for r in reviews])
    thr = gate["repetition_threshold"]
    k_overall = val["kappa"]["issue_id"] if val["kappa"]["issue_id"] is not None else 0.0

    # ---- per-issue sets ----
    idef = {i["issue_id"]: i for i in issues_def}
    st_by_issue = collections.defaultdict(list)
    for st in sts:
        st_by_issue[st["issue_id"]].append(st)
    rev_by_issue = {i: {st["review_id"] for st in ss} for i, ss in st_by_issue.items()}
    stage_name = {st["id"]: st["name"] for st in structure["stages"]}
    cat_name = {c["id"]: c["name"] for c in structure["categories"]}
    cat_of_issue = {i: c["id"] for c in structure["categories"] for i in c["issue_ids"]}

    def share(revset, codes=None):
        codes = codes or [c["code"] for c in sel]
        k = collections.Counter(rv_by_id[r]["country"] for r in revset)
        if len(codes) == 1:
            n = n_c[codes[0]]
            lo, hi = sl.wilson(k[codes[0]], n)
            return (k[codes[0]] / n if n else 0.0), lo, hi
        p, _, lo, hi = sl.stratified({c: k[c] for c in codes}, {c: n_c[c] for c in codes}, {c: W[c] for c in codes})
        return p, lo, hi

    named = [i for i in idef if i in rev_by_issue]
    recurring = sorted([i for i in named if len(rev_by_issue[i]) >= thr], key=lambda i: -len(rev_by_issue[i]))
    long_tail = [i for i in idef if 0 < len(rev_by_issue.get(i, ())) < thr]

    issues_out, detail_issues = [], {}
    for iid in recurring:
        d = idef[iid]
        ss, rs = st_by_issue[iid], rev_by_issue[iid]
        typ = issue_type(ss)
        kc = collections.Counter(rv_by_id[r]["country"] for r in rs)
        cnts = [kc[c] for c in disp_codes]
        per = [100 * kc[c] / n_c[c] if n_c[c] else 0.0 for c in disp_codes]
        p, lo, hi = share(rs)
        with_s = [rv_by_id[r]["rating"] for r in rs]
        without = [r["rating"] for r in reviews if r["review_id"] not in rs]
        desc = sl.describe_stars(with_s)
        gap, glo, ghi, _ = sl.welch(with_s, without)
        chi = sl.chi2_2xk(cnts, [n_c[c] for c in disp_codes], seed=seed) if multi else {"chi2": 0.0, "p": 1.0, "cramer": 0.0, "method": "one country"}
        sev = None
        if typ in ("Bug", "Complaint"):
            sc = collections.Counter(st["severity"] for st in ss if st["severity"])
            sev = [sc[x] for x in SEV] if sum(sc.values()) else None
        pk = val["per_issue"].get(iid, {})
        kap = pk.get("kappa")
        stc = collections.Counter(st["stage_id"] for st in ss if st["stage_id"] and st["stage_id"] != "none")
        stage_id = stc.most_common(1)[0][0] if stc else d.get("stage_id")
        stars_of = [rv_by_id[r]["rating"] for r in rs]
        item = {"id": iid, "name": d["name"], "category": cat_name.get(cat_of_issue.get(iid, d["category_id"]), d["category_id"]),
                "type": typ, "definition": d["definition"], "counts": cnts, "n": len(rs), "wshare": r2(100 * p),
                "wci": [r2(100 * lo), r2(100 * hi)], "per_country": [r2(x) for x in per], "cv": r1(sl.cv(per)) if multi else 0.0,
                "chi2": r1(chi["chi2"]), "p": chi["p"], "cramer": r3(chi["cramer"]),
                "stars": {"mean": r2(desc["mean"]), "sd": r2(desc["sd"]), "median": desc["median"], "mode": desc["mode"], "cv": r1(desc["cv"])},
                "gap": r2(gap), "gap_ci": [r2(glo), r2(ghi)], "cohen_d": r2(sl.cohen_d(with_s, without)), "severity": sev,
                "kappa": r2(kap if kap is not None else k_overall), "short_name": d["short_name"],
                "stage": stage_name.get(stage_id) if stage_id else None,
                "team": {"primary": d["team_primary"], "secondary": list(d["team_secondary"])}}
        if typ == "Praise":
            item["n_high"] = sum(x >= 4 for x in stars_of)
        else:
            item["n_low"] = sum(x <= 2 for x in stars_of)
        issues_out.append(item)
        detail_issues[iid] = {"statement_ids": [st["statement_id"] for st in ss], "review_ids": sorted(rs),
                              "n_statements": len(ss), "pooled_share": 100 * len(rs) / N, "wshare": 100 * p,
                              "wci": [100 * lo, 100 * hi], "chi_method": chi["method"], "p_raw": chi["p"],
                              "kappa_sampled": kap is not None, "kappa_detail": pk, "stars": desc,
                              "mean_without": float(np.mean(without)) if without else 0.0, "gap_full": [gap, glo, ghi],
                              "small_group": len(rs) < s["min_group_for_tests"], "stage_id": stage_id,
                              "sev_statements": sum(sev) if sev else 0}
    # Holm across problems, and across strengths, for the country tests
    for group in (lambda i: i["type"] != "Praise", lambda i: i["type"] == "Praise"):
        g = [i for i in issues_out if group(i)]
        for i, padj in zip(g, sl.holm([i["p"] for i in g])):
            i["p"] = float("%.3g" % padj)
            detail_issues[i["id"]]["p_holm"] = padj
    problems = [i for i in issues_out if i["type"] != "Praise"]
    strengths = [i for i in issues_out if i["type"] == "Praise"]
    rec_ids = {i["id"] for i in issues_out}
    itype = {i["id"]: i["type"] for i in issues_out}

    # ---- review mix ----
    rp, rpr = collections.defaultdict(bool), collections.defaultdict(bool)
    for st in sts:
        if is_problem(st):
            rp[st["review_id"]] = True
        if is_praise(st):
            rpr[st["review_id"]] = True
    mix = {str(k): [0, 0, 0, 0] for k in range(1, 6)}
    for r in reviews:
        a, b = rp[r["review_id"]], rpr[r["review_id"]]
        mix[str(r["rating"])][0 if a and not b else 1 if a and b else 2 if b else 3] += 1

    # ---- sentiment ----
    sc = collections.Counter(st["sentiment"] for st in sts)
    ns = len(sts)
    overall = {}
    for key, lab in (("negative", "Negative"), ("mixed", "Mixed"), ("neutral", "Neutral"), ("positive", "Positive")):
        lo, hi = sl.wilson(sc[lab], ns)
        overall[key] = {"n": sc[lab], "p": r1(100 * sc[lab] / ns if ns else 0), "lo": r1(100 * lo), "hi": r1(100 * hi)}
    cats = []
    for c in structure["categories"]:
        ss = [st for i in c["issue_ids"] for st in st_by_issue.get(i, [])]
        cc = collections.Counter(st["sentiment"] for st in ss)
        cats.append({"name": c["name"], "neg": cc["Negative"], "mixed": cc["Mixed"], "neutral": cc["Neutral"], "pos": cc["Positive"],
                     "total": len(ss), "net": r1(sl.net_sentiment(cc["Positive"], cc["Negative"], len(ss))), "id": c["id"],
                     "n_issues": sum(1 for i in c["issue_ids"] if i in rev_by_issue),
                     "n_reviews": len({st["review_id"] for st in ss})})
    nonempty = [c for c in cats if c["total"] > 0]
    cats_report = nonempty if len(nonempty) >= s["categories_min"] else cats
    cat_flags = [c["name"] for c in cats if c["n_issues"] < s["category_min_issues"] and c["n_reviews"] < s["category_min_review_share"] * N]

    # ---- journey ----
    stages = []
    for stg in structure["stages"]:
        ss = [st for st in sts if st["stage_id"] == stg["id"]]
        cc = collections.Counter(st["sentiment"] for st in ss)
        prob = [st for st in ss if st["statement_type"] in ("Bug report", "Complaint")]
        blk = sum(st["severity"] == "Blocker" for st in prob)

        def top(kind):
            rset = collections.defaultdict(set)
            for st in ss:
                i = st["issue_id"]
                if i in rec_ids and (itype[i] == "Praise") == (kind == "praise"):
                    rset[i].add(st["review_id"])
            return max(sorted(rset), key=lambda i: len(rset[i])) if rset else None
        lw = stg.get("listing_words") or []
        src = ("Listing (%s) and reviews" % ", ".join('"%s"' % w for w in lw[:3])) if stg["source"] == "listing_and_reviews" and lw else \
              ("Listing and reviews" if stg["source"] == "listing_and_reviews" else "Reviews only")
        stages.append({"name": stg["name"], "desc": stg["desc"], "neg": cc["Negative"], "pos": cc["Positive"],
                       "other": cc["Neutral"] + cc["Mixed"], "total": len(ss),
                       "net": r1(sl.net_sentiment(cc["Positive"], cc["Negative"], len(ss))),
                       "top_problem": top("problem"), "top_strength": top("praise"),
                       "blocker": int(round(100 * blk / len(prob))) if prob else 0, "source": src,
                       "_id": stg["id"], "_problem_statements": len(prob)})
    if sum(x["total"] > 0 for x in stages) >= s["stages_min"]:
        stages = [x for x in stages if x["total"] > 0]
    low_blocker = [x["name"] for x in stages if 0 < x["_problem_statements"] < s["min_problem_statements_blocker"]]
    unassigned = sum(st["stage_id"] in (None, "none") for st in sts)

    # ---- teams (problems only) ----
    teams = collections.OrderedDict()
    for i in problems:
        teams.setdefault(i["team"]["primary"], {"primary": [], "secondary": []})["primary"].append(i["id"])
        for t in i["team"]["secondary"]:
            teams.setdefault(t, {"primary": [], "secondary": []})["secondary"].append(i["id"])
    teams_out = []
    for name, v in teams.items():
        rs = set().union(*[rev_by_issue[i] for i in v["primary"]]) if v["primary"] else set()
        p, lo, hi = share(rs) if rs else (0.0, 0.0, 0.0)
        teams_out.append({"name": name, "n": len(rs), "w": r1(100 * p), "lo": r1(100 * lo), "hi": r1(100 * hi),
                          "primary": v["primary"], "secondary": v["secondary"]})
    teams_out.sort(key=lambda t: (-t["w"], -len(t["secondary"])))

    # ---- time ----
    time_out, time_detail = None, {}
    if reviews:
        last = max(monday(r["date"]) for r in reviews)
        first = max(min(monday(r["date"]) for r in reviews), last - dt.timedelta(weeks=25))
        nW = (last - first).days // 7 + 1
        wk = lambda r: (monday(r["date"]) - first).days // 7  # noqa: E731
        in_win = [r for r in reviews if monday(r["date"]) >= first]
        n_week = [0] * nW
        nwc = collections.defaultdict(lambda: collections.Counter())
        for r in in_win:
            n_week[wk(r)] += 1
            nwc[wk(r)][r["country"]] += 1
        solid = sum(n >= s["min_reviews_week_solid"] for n in n_week)
        recent_from = max(1, nW - int(s["recent_weeks"]))
        if solid >= s["min_solid_weeks_for_time"] and nW > s["recent_weeks"]:
            codes = [c["code"] for c in sel]
            rec_n = {c: sum(nwc[t][c] for t in range(recent_from, nW)) for c in codes}
            ear_n = {c: sum(nwc[t][c] for t in range(0, recent_from)) for c in codes}
            both = [c for c in codes if rec_n[c] > 0 and ear_n[c] > 0]
            excluded = [c for c in codes if c not in both and (rec_n[c] or ear_n[c])]
            series, raw_p = [], []
            for i in problems[:int(s["time_top_problems"])]:
                rs = rev_by_issue[i["id"]]
                kwc = collections.defaultdict(lambda: collections.Counter())
                for rid in rs:
                    r = rv_by_id[rid]
                    if monday(r["date"]) >= first:
                        kwc[wk(r)][r["country"]] += 1
                pts = []
                for t in range(nW):
                    present = [c for c in codes if nwc[t][c] > 0]
                    p, _, lo, hi = sl.stratified({c: kwc[t][c] for c in present}, {c: nwc[t][c] for c in present}, {c: W[c] for c in present})
                    pts.append({"t": t, "n": n_week[t], "k": sum(kwc[t].values()), "p": r2(100 * p), "lo": r2(100 * lo),
                                "hi": r2(100 * hi), "countries": len(present)})
                if both:
                    kr = {c: sum(kwc[t][c] for t in range(recent_from, nW)) for c in both}
                    ke = {c: sum(kwc[t][c] for t in range(0, recent_from)) for c in both}
                    pr = sl.stratified(kr, {c: rec_n[c] for c in both}, {c: W[c] for c in both})[0]
                    pe = sl.stratified(ke, {c: ear_n[c] for c in both}, {c: W[c] for c in both})[0]
                    pv = sl.cmh([[[kr[c], rec_n[c] - kr[c]], [ke[c], ear_n[c] - ke[c]]] for c in both])
                else:
                    pr = pe = 0.0
                    pv = None
                raw_p.append(1.0 if pv is None else pv)
                series.append({"id": i["id"], "pts": pts, "earlier": r1(100 * pe), "recent": r1(100 * pr), "diff": r1(100 * (pr - pe))})
            for sr, padj in zip(series, sl.holm(raw_p)):
                sr["p_adj"] = float("%.3g" % padj)
            rel = []
            vs = sorted([v for v in app["versions"] if v.get("date")], key=lambda v: v["date"], reverse=True)
            last_end = last + dt.timedelta(days=6)
            for v in vs:
                d = dt.date.fromisoformat(v["date"])
                if not first <= d <= last_end:
                    continue
                pos = ((d - first).days - 3) / 7
                if rel and rel[-1]["pos"] - pos < 2:
                    continue
                rel.append({"pos": round(max(0.0, min(nW - 1, pos)), 2), "label": "v%s · %s %d" % (v["version"], d.strftime("%b"), d.day)})
                if len(rel) >= 6:
                    break
            time_out = {"weeks": ["%s %d" % ((first + dt.timedelta(weeks=t)).strftime("%b"), (first + dt.timedelta(weeks=t)).day) for t in range(nW)],
                        "n_week": n_week, "recent_from": recent_from, "excluded_countries": excluded,
                        "releases": sorted(rel, key=lambda x: x["pos"]), "series": series}
            time_detail = {"first_week": first.isoformat(), "raw_p": raw_p, "countries_in_test": both, "solid_weeks": solid}
        else:
            time_detail = {"hidden": True, "solid_weeks": solid, "weeks": nW}

    # ---- quotes (rule 12.5) ----
    from group_phrases import load_vectors, phrase_key
    vec = load_vectors(run)
    quotes, quote_detail = [], {}
    for i in problems[:6] + strengths[:4]:
        ss = st_by_issue[i["id"]]
        mat = np.stack([vec[phrase_key(st["issue_phrase"])] for st in ss])
        cen = mat.mean(0)
        cen = cen / (np.linalg.norm(cen) or 1)
        cands = []
        for st, v in zip(ss, mat):
            if words(st["text_span"]) >= 40 or PII.search(st["text_span"]):
                continue
            lang = rv_by_id[st["review_id"]]["language"]
            if lang not in ("en", "und") and not st.get("translation"):
                continue
            cands.append((float(v @ cen), st["confidence"], st))
        cands.sort(key=lambda x: (-x[0], -x[1], x[2]["statement_id"]))
        if not cands:
            continue
        st = cands[0][2]
        r = rv_by_id[st["review_id"]]
        tr = st.get("translation") if r["language"] not in ("en",) and st.get("translation") and st["translation"].strip() != st["text_span"].strip() else None
        quotes.append({"issue_id": i["id"], "text": st["text_span"], "translation": tr, "review_id": r["review_id"],
                       "stars": r["rating"], "version": r["app_version"], "country": r["country"]})
        quote_detail[i["id"]] = [{"statement_id": c[2]["statement_id"], "similarity": round(c[0], 4)} for c in cands[:int(s["quotes_per_issue_card"])]]

    # ---- lift (run record only) ----
    lift = []
    top6 = problems[:6]
    for a in range(len(top6)):
        for b in range(a + 1, len(top6)):
            A, B = rev_by_issue[top6[a]["id"]], rev_by_issue[top6[b]["id"]]
            kab = len(A & B)
            lf, cond = sl.lift(kab, len(A), len(B), N)
            if lf >= 2 and kab >= 3:
                lift.append({"a": top6[a]["id"], "b": top6[b]["id"], "k_ab": kab, "lift": round(lf, 2), "p_b_given_a": round(cond, 3)})

    # ---- countries, meta, about ----
    countries_out = []
    for c in disp:
        w = windows.get(c["code"], {})
        langs = [language_name(l) for l, n in (w.get("languages") or {}).items() if n >= 0.1 * max(1, w.get("n", 1))][:2]
        countries_out.append({"code": c["code"], "name": c["name"], "ratings": c["ratings"], "weight": r1(100 * c["weight"]),
                              "n": n_c[c["code"]], "window": w.get("label", ""), "days": w.get("days", 0), "lang": ", ".join(langs) or "Unknown"})
    lc = collections.Counter(r["language"] for r in reviews if r["language"] != "und")
    languages = [language_name(l) for l, n in lc.most_common() if n >= 0.01 * N][:8] or ["Unknown"]
    dates = sorted(r["date"] for r in reviews)
    top_c = max(sel, key=lambda c: c["ratings"])
    vsort = sorted([v for v in app["versions"] if v.get("date")], key=lambda v: v["date"], reverse=True)
    langs_l = app.get("languages") or []
    meta = {"app_name": app["name"], "app_short": app["app_short"], "app_id": app["app_id"], "run_date": dt.date.today().isoformat(),
            "period_start": dates[0] if dates else "", "period_end": dates[-1] if dates else "", "countries": [c["code"] for c in sel],
            "n_reviews": N, "n_statements": counts.get("extract", {}).get("statements", len(sts)), "n_statements_kept": len(sts),
            "mean_stars": r2(stars_all.mean() if N else 0), "kappa": r2(k_overall), "repetition_threshold": thr,
            "languages": languages, "second_pass_n": val["n"], "notice": None}
    about = {"description": first_paragraph(app["description"]),
             "description_source": "App Store description, first paragraph (%s store)" % app.get("listing_country", "US"),
             "developer": app["developer"], "category": app["category"], "price": app["price_label"],
             "current_version": vsort[0]["version"] if vsort else "unknown", "current_version_date": vsort[0]["date"] if vsort else meta["period_end"],
             "store_rating": r1(top_c.get("store_rating") or app["store_rating"].get(top_c["code"]) or 0),
             "store_rating_country": top_c["code"], "store_rating_count": int(top_c["ratings"]),
             "languages_label": (", ".join(langs_l[:3]) + (" and %d more" % (len(langs_l) - 3) if len(langs_l) > 3 else "")) if langs_l else "Not listed",
             "features": structure.get("listed_features") or app.get("listed_features") or [],
             "versions": [{"version": v["version"], "date": v["date"], "notes": short_notes(v["notes"])} for v in vsort[:6]]}
    lt_reviews = set().union(*[rev_by_issue[i] for i in long_tail]) if long_tail else set()
    board = {"long_tail_issues": len(long_tail), "long_tail_reviews": len(lt_reviews),
             "other_statements": sum(st["issue_id"] == "other" for st in sts)}
    for x in stages:
        x.pop("_id")
        x.pop("_problem_statements")
    report = {"schema_version": "1.0", "meta": meta, "about": about, "countries": countries_out,
              "country_selection": {"candidates": csel["candidates"], "coverage": r1(100 * csel["coverage"]), "target": int(round(100 * csel["target"]))},
              "mix": mix, "sentiment": {"overall": overall, "categories": [{k: c[k] for k in ("name", "neg", "mixed", "neutral", "pos", "total", "net")} for c in cats_report]},
              "issues": issues_out, "board": board, "teams": teams_out, "journey": {"stages": stages, "unassigned": unassigned},
              "quotes": quotes}
    if time_out:
        report["time"] = time_out
    detail = {"issues": detail_issues, "long_tail": {i: len(rev_by_issue[i]) for i in long_tail},
              "named_issues": len(named), "issues_defined": len(idef), "categories": cats, "category_size_flags": cat_flags,
              "low_blocker_stages": low_blocker, "time": time_detail, "quotes": quote_detail, "lift": lift,
              "display_countries": disp_codes, "hidden_countries": [c["code"] for c in sel if c["code"] not in disp_codes],
              "kappa": val["kappa"], "mix_rule": "problem = bug report, complaint, or negative comparison; praise = praise or positive comparison",
              "high_star_with_problem": _mix_share(mix, ("4", "5"), (0, 1)), "low_star_with_praise": _mix_share(mix, ("1", "2"), (1, 2)),
              "reviews_with_problem": sum(rp.values()) / max(1, N), "reviews_with_praise": sum(rpr.values()) / max(1, N),
              "versions": dict(collections.Counter(r["app_version"] for r in reviews).most_common())}
    write_json(run.p("stats", "stats.json"), {"report": report, "detail": detail})
    run.log("Computed stratified shares, intervals and tests for %d recurring issues (threshold %d reviews), %d categories, %d stages%s and %d countries." % (
        len(issues_out), thr, len(cats_report), len(stages), (", %d weeks" % len(time_out["weeks"])) if time_out else "", len(disp)))
    run.update_record(counts={"stats": {"recurring": len(issues_out), "long_tail": len(long_tail), "named": len(named),
                                        "categories": len(cats_report), "stages": len(stages), "weeks": len(time_out["weeks"]) if time_out else 0,
                                        "countries_displayed": len(disp), "lift_pairs": lift}})
    return report


def _mix_share(mix, stars, cols):
    k = sum(mix[s][c] for s in stars for c in cols)
    n = sum(sum(mix[s]) for s in stars)
    lo, hi = sl.wilson(k, n)
    return {"k": k, "n": n, "p": 100 * k / n if n else 0.0, "lo": 100 * lo, "hi": 100 * hi}


if __name__ == "__main__":
    main(Run(sys.argv[1]))
