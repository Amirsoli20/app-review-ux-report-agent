"""Step 8. Name issues and build the app's structure with the issue-namer sub-agent (section 7 pass 3, 9.5, 9.6).

-> issues/issues.yaml, issues/structure.yaml (frozen after this step), proposed_issue on each statement,
   listed_features in app.json.
"""
import collections
import re
import math
import sys

import llm
from common import Run, TEAMS, read_json, read_jsonl, run_settings, words, write_json, write_jsonl, write_yaml


def threshold(n_reviews, s):
    return max(int(s["repetition_min_reviews"]), math.ceil(float(s["repetition_min_share"]) * n_reviews))


def build_payload(app, groups, sts, n_reviews, s, existing=None):
    clustered = [g for g in groups if g["clustered"]]
    # unclustered phrases, most frequent first, up to a cap: big runs have thousands of one-off phrases whose
    # statements the assigner still places; small runs keep them all
    single = sorted([g for g in groups if not g["clustered"]], key=lambda g: -g["n_statements"])
    single = single[:int(s.get("namer_max_single_phrases", 400))]
    loc = collections.Counter(" ".join(st["location_phrase"].lower().split()) for st in sts)
    gp = []
    for i, g in enumerate(clustered):
        gp.append({"group_id": g["group_id"], "n_statements": g["n_statements"], "n_reviews": g["n_reviews"],
                   "central_phrases": ["%s (%d)" % (c["phrase"], c["n"]) for c in g["central_phrases"]],
                   "quotes": g["quotes"][:5 if i < 150 else 2], "types": g["types"], "sentiments": g["sentiments"],
                   "ux_dimensions": g["ux_dimensions"]})
    p = {"app": {"name": app["name"], "category": app["category"], "subtitle": app.get("subtitle"),
                 "description": app["description"][:5000], "in_app_purchases": [i["name"] for i in app["in_app_purchases"][:12]],
                 "versions": [{"version": v["version"], "date": v["date"], "notes": v["notes"][:300]} for v in app["versions"][:8]]},
         "n_reviews": n_reviews, "repetition_threshold": threshold(n_reviews, s),
         "limits": {"categories": [s["categories_min"], s["categories_max"]], "stages": [s["stages_min"], s["stages_max"]],
                    "secondary_teams_max": s["secondary_teams_max"]},
         "groups": gp,
         "single_phrases": [{"group_id": g["group_id"], "phrase": g["central_phrases"][0]["phrase"], "n": g["n_statements"]} for g in single],
         "location_phrases": [{"phrase": k, "n": n} for k, n in loc.most_common(200)]}
    if existing:
        p["task"] = "extend"
        p["existing"] = existing
    return p


def repair(obj, payload, s, extend=False):
    """Fix small defects in the namer's answer in place, so one bad field does not discard the whole answer.
    Returns notes on what was changed (kept in structure.yaml)."""
    notes = []
    gids = {g["group_id"] for g in payload["groups"]} | {g["group_id"] for g in payload["single_phrases"]}
    stages = {st["id"] for st in (payload["existing"]["stages"] if extend else obj.get("stages", []))}
    seen = collections.Counter()
    for i in obj["issues"]:
        seen[i["issue_id"]] += 1
        if seen[i["issue_id"]] > 1:
            i["issue_id"] = "%s-%d" % (i["issue_id"], seen[i["issue_id"]])
            notes.append("duplicate id renamed to %s" % i["issue_id"])
        n = words(i["short_name"])
        if not 2 <= n <= 4 or len(i["short_name"]) > 26:
            base = i["short_name"] if n > 4 or len(i["short_name"]) > 26 else i["name"]
            sn = " ".join(base.split()[:4 if n > 4 else 3])
            while len(sn) > 26 and len(sn.split()) > 2:
                sn = " ".join(sn.split()[:-1])
            notes.append("issue %s: short_name %r -> %r" % (i["issue_id"], i["short_name"], sn[:26]))
            i["short_name"] = sn[:26]
        bad = [g for g in i["source_groups"] if g not in gids]
        if bad:
            i["source_groups"] = [g for g in i["source_groups"] if g in gids]
            notes.append("issue %s: dropped unknown groups %s" % (i["issue_id"], ", ".join(bad[:5])))
        if i["team_primary"] in i["team_secondary"]:
            i["team_secondary"] = [t for t in i["team_secondary"] if t != i["team_primary"]]
        if i["stage_id"] is not None and i["stage_id"] not in stages:
            notes.append("issue %s: unknown stage %s set to none" % (i["issue_id"], i["stage_id"]))
            i["stage_id"] = None
    if not extend:
        for k, st in enumerate(sorted(obj["stages"], key=lambda x: x.get("order") if isinstance(x.get("order"), int) else 999)):
            st["order"] = k + 1
            st["desc"] = st.get("desc", "")[:40]
            if st.get("source") not in ("listing_and_reviews", "reviews_only"):
                st["source"] = "listing_and_reviews" if st.get("listing_words") else "reviews_only"
        lts = obj.get("location_to_stage") or {}
        obj["location_to_stage"] = {k: v for k, v in lts.items() if v in stages or v == "none"}
        covered = {g for i in obj["issues"] for g in i["source_groups"]}
        big = [g["group_id"] for g in payload["groups"] if g["n_reviews"] >= payload["repetition_threshold"] and g["group_id"] not in covered]
        if big:
            notes.append("groups at or above the threshold left to the assigner: %s" % ", ".join(big[:20]))
    return notes


def check_output(obj, payload, s, extend=False):
    """Structural problems only (after repair): these send the answer back to the namer once."""
    import jsonschema
    from common import schema
    if not isinstance(obj, dict) or not isinstance(obj.get("issues"), list):
        raise ValueError("the answer must be an object with an 'issues' list")
    need = schema("issue")["required"]
    gaps = ["%s: missing %s" % (i.get("issue_id", "?") if isinstance(i, dict) else "?",
                                ", ".join(k for k in need if not isinstance(i, dict) or k not in i))
            for i in obj["issues"] if not isinstance(i, dict) or any(k not in i for k in need)]
    if gaps:
        raise ValueError("issues with missing fields: " + "; ".join(gaps[:10]))
    obj["_repairs"] = repair(obj, payload, s, extend)
    rep = obj.pop("_repairs")
    jsonschema.validate(obj, schema("namer_output") if not extend else {"type": "object", "properties": {"issues": {"type": "array", "items": schema("issue")}}})
    obj["_repairs"] = rep
    probs = []
    if extend:
        old = {i["issue_id"] for i in payload["existing"]["issues"]}
        clash = sorted({i["issue_id"] for i in obj["issues"]} & old)
        if clash:
            probs.append("new issues reuse existing ids: %s" % ", ".join(clash))
        cats = {c["id"] for c in payload["existing"]["categories"]}
    else:
        cats = {c["id"] for c in obj["categories"]}
        lo, hi = s["categories_min"], s["categories_max"]
        if not lo <= len(obj["categories"]) <= hi:
            probs.append("%d categories; between %d and %d are required" % (len(obj["categories"]), lo, hi))
        lo, hi = s["stages_min"], s["stages_max"]
        if not lo <= len(obj["stages"]) <= hi:
            probs.append("%d stages; between %d and %d are required" % (len(obj["stages"]), lo, hi))
        bad_names = [c["name"] for c in obj["categories"] if c["name"].strip().lower() in ("complaints", "bugs", "praise", "requests", "other", "general")]
        if bad_names:
            probs.append("category names must name a product area, not a type or feeling: %s" % ", ".join(bad_names))
    for i in obj["issues"]:
        if i["category_id"] not in cats:
            probs.append("issue %s: unknown category_id %s" % (i["issue_id"], i["category_id"]))
        for k in ("name", "short_name", "definition"):
            m = PEOPLE.search(i[k])
            if m:
                probs.append("issue %s: %s uses %r; describe the experience without users or customers" % (i["issue_id"], k, m.group(0)))
    return probs


PEOPLE = re.compile(r"\b(users?|customers?)\b", re.I)


def scrub_people(issues):
    """Last resort after the namer's retry: banned words for people in issue text become "people"."""
    for i in issues:
        for k in ("name", "short_name", "definition"):
            i[k] = PEOPLE.sub(lambda m: "people" if m.group(0).lower().endswith("s") else "person", i[k])


def fallback(payload, s):
    """Degraded structure when the issue-namer fails twice: one issue per cluster, named by its central phrase."""
    issues, cats = [], collections.OrderedDict()
    for g in payload["groups"]:
        dim = max(g["ux_dimensions"], key=g["ux_dimensions"].get)
        cid = dim.lower().replace(" ", "-")
        cats.setdefault(cid, {"id": cid, "name": dim, "issue_ids": []})
        name = g["central_phrases"][0].rsplit(" (", 1)[0]
        typ = max(g["types"], key=g["types"].get)
        iid = "c-" + g["group_id"]
        issues.append({"issue_id": iid, "name": name[:1].upper() + name[1:], "short_name": " ".join(name.split()[:3])[:26],
                       "definition": "Statements whose issue phrase is close to \"%s\"." % name, "category_id": cid,
                       "dominant_type": typ, "stage_id": None, "ux_dimension": dim, "team_primary": "UX design",
                       "team_secondary": [], "source_groups": [g["group_id"]]})
        cats[cid]["issue_ids"].append(iid)
    loc = [l for l in payload["location_phrases"] if l["phrase"] != "general"][:s["stages_max"]]
    stages = [{"id": "st%d" % k, "order": k + 1, "name": l["phrase"][:1].upper() + l["phrase"][1:], "desc": l["phrase"][:40],
               "source": "reviews_only", "listing_words": []} for k, l in enumerate(loc)]
    return {"listed_features": [], "issues": issues, "categories": list(cats.values()), "stages": stages,
            "location_to_stage": {l["phrase"]: "st%d" % k for k, l in enumerate(loc)}, "fallback": True}


def apply_routing_rules(issue, statements):
    """Rule 9.5.2: a bug report whose statements mention an update or a version adds QA and release."""
    import re
    upd = re.compile(r"\b(update[ds]?|updating|version|upgrade[ds]?|aktualisierung|update|mise à jour|actualizaci[oó]n|"
                     r"atualiza[cç][aã]o|aggiornamento|versione|versión|versão|バージョン|アップデート|업데이트)\b", re.I)
    if issue["dominant_type"] != "Bug report" or "QA and release" in [issue["team_primary"]] + issue["team_secondary"]:
        return issue
    texts = [(st["text_span"] + " " + (st.get("translation") or "")) for st in statements]
    if texts and sum(bool(upd.search(t)) for t in texts) / len(texts) >= 0.2:
        sec = [t for t in issue["team_secondary"] if t != "QA and release"]
        issue["team_secondary"] = (sec[:1] if len(sec) >= 2 else sec) + ["QA and release"]
        issue["routing_note"] = "QA and release added: statements mention an update or version"
    return issue


def main(run):
    s = run_settings(run)
    app = read_json(run.p("app.json"))
    groups = read_json(run.p("issues", "groups.json"))["groups"]
    sts = read_jsonl(run.p("labels", "statements.jsonl"))
    n_reviews = len(read_jsonl(run.p("clean", "reviews.jsonl")))
    payload = build_payload(app, groups, sts, n_reviews, s)
    agent = llm.Agent("issue-namer", s)
    run.log("Naming issues from %d clusters and %d single phrases (%s)." % (len(payload["groups"]), len(payload["single_phrases"]), agent.model))
    try:
        out = llm.call(agent, payload, run, None, lambda o: check_output(o, payload, s), tag="name issues", return_last=True)
        try:
            hard = [p for p in check_output(out, payload, s) if "describe the experience" not in p]
        except Exception as e:  # noqa: BLE001 - malformed answer: treat like a failed call
            raise RuntimeError("issue-namer answer invalid: %s" % str(e)[:300])
        if hard:
            raise RuntimeError("issue-namer answer still invalid: " + "; ".join(hard[:5]))
        scrub_people(out["issues"])
        used_fallback = False
    except RuntimeError as e:
        run.log("issue-namer failed twice (%s); using the degraded fallback structure." % str(e)[:300])
        out, used_fallback = fallback(payload, s), True
    freeze(run, app, out, sts, groups, used_fallback, agent.version)
    return out


def freeze(run, app, out, sts, groups, used_fallback, version):
    by_group = {}
    for i in out["issues"]:
        for g in i["source_groups"]:
            by_group.setdefault(g, i["issue_id"])
    sts_by_issue = collections.defaultdict(list)
    for st in sts:
        st["proposed_issue"] = by_group.get(st["group_id"], "other")
        sts_by_issue[st["proposed_issue"]].append(st)
    for i in out["issues"]:
        apply_routing_rules(i, sts_by_issue.get(i["issue_id"], []))
    cats = {c["id"]: dict(c, issue_ids=[]) for c in out["categories"]}
    for i in out["issues"]:
        cats[i["category_id"]]["issue_ids"].append(i["issue_id"])
    stages = sorted(out["stages"], key=lambda x: x["order"])
    for k, st in enumerate(stages):
        st["order"] = k + 1
    structure = {"repairs": out.pop("_repairs", []), "listed_features": out.get("listed_features", []), "categories": list(cats.values()), "stages": stages,
                 "location_to_stage": out.get("location_to_stage") or {}, "fallback": used_fallback}
    write_yaml(run.p("issues", "issues.yaml"), {"issues": out["issues"]})
    write_yaml(run.p("issues", "structure.yaml"), structure)
    write_jsonl(run.p("labels", "statements.jsonl"), sts, "statement")
    app["listed_features"] = structure["listed_features"]
    write_json(run.p("app.json"), app, "app")
    n_listing = sum(st["source"] == "listing_and_reviews" for st in stages)
    run.log("%d groups became %d issues in %d categories; a %d-stage journey (%d stages match the listing)." % (
        len(groups), len(out["issues"]), len(cats), len(stages), n_listing))
    run.update_record(counts={"name": {"groups": len(groups), "issues": len(out["issues"]), "categories": len(cats),
                                       "stages": len(stages), "stages_from_listing": n_listing, "fallback": used_fallback,
                                       "teams_used": sorted({i["team_primary"] for i in out["issues"]} & set(TEAMS))}},
                      prompts={"issue-namer": version})


if __name__ == "__main__":
    main(Run(sys.argv[1]))
