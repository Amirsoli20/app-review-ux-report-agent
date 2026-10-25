"""Step 2. Select countries by rating count (section 8) -> countries.json."""
import sys
from concurrent.futures import ThreadPoolExecutor

import appstore
from common import Run, country_name, read_json, run_settings, write_json


def pick(counts, target, cmin, cmax):
    """Rank by rating count; add countries until they cover `target` of all ratings found, within [cmin, cmax]."""
    ranked = sorted([(c, n) for c, n in counts.items() if n > 0], key=lambda x: -x[1])
    total = sum(n for _, n in ranked)
    chosen, cum = [], 0
    for c, n in ranked:
        if len(chosen) >= cmax:
            break
        if len(chosen) >= cmin and total and cum / total >= target:
            break
        chosen.append((c, n))
        cum += n
    return chosen, (cum / total if total else 0.0), total


def main(run, country=None):
    s = run_settings(run)
    appstore.configure(s)
    app = read_json(run.p("app.json"))
    app_id = app["app_id"]
    if country:
        cc = country.lower()
        info = appstore.lookup_app(app_id, cc)
        n = (info or {}).get("rating_count", 0)
        chosen, coverage, candidates, lookups = [(cc, n)], 1.0, 1, {cc: info}
        run.log("Country set by input: %s (%s ratings)." % (cc.upper(), f"{n:,}"))
    else:
        cands = s["candidate_countries"]
        with ThreadPoolExecutor(4) as ex:  # the shared limiter keeps this at the per-minute budget
            res = list(ex.map(lambda c: (c, _safe_lookup(app_id, c)), cands))
        lookups = dict(res)
        counts = {c: (v or {}).get("rating_count", 0) for c, v in lookups.items()}
        chosen, coverage, _ = pick(counts, s["rating_coverage_target"], s["countries_min"], s["countries_max"])
        candidates = len(cands)
        run.log("Looked up rating counts in %d countries. Kept %s: %.1f%% of all ratings." % (
            candidates, ", ".join(c.upper() for c, _ in chosen), 100 * coverage))
    tot = sum(n for _, n in chosen) or 1
    countries = [{"code": c.upper(), "name": country_name(c), "ratings": n, "weight": n / tot,
                  "store_rating": (lookups.get(c) or {}).get("rating")} for c, n in chosen]
    if not countries:
        raise SystemExit("The app has no ratings in any candidate country")
    out = {"countries": countries, "candidates": candidates, "coverage": coverage,
           "target": s["rating_coverage_target"], "all_counts": {c: (v or {}).get("rating_count", 0) for c, v in lookups.items()}}
    write_json(run.p("countries.json"), out)
    app["store_rating"] = {c["code"]: c["store_rating"] for c in countries}
    app["store_rating_count"] = {c["code"]: c["ratings"] for c in countries}
    write_json(run.p("app.json"), app, "app")
    run.update_record(countries=[{k: c[k] for k in ("code", "ratings", "weight")} for c in countries])
    return out


def _safe_lookup(app_id, c):
    try:
        return appstore.lookup_app(app_id, c)
    except RuntimeError:
        return None


if __name__ == "__main__":
    main(Run(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else None)
