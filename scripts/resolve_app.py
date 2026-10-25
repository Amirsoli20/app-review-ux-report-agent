"""Step 1. Resolve the app from a link, id or name, and read its App Store listing -> app.json."""
import re
import sys

import appstore
from common import Run, write_json


def _norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).split()


def choose(term, results):
    """The match with the most ratings, among results whose name contains every word of the term.
    Falls back to all results when no name contains the term."""
    want = set(_norm(term))
    named = [r for r in results if want and want <= set(_norm(r["name"]))]
    pool = named or results
    if not pool:
        return None, []
    best = max(pool, key=lambda r: r["rating_count"])
    alts = sorted([r for r in results if r["app_id"] != best["app_id"]], key=lambda r: -r["rating_count"])[:5]
    return best, alts


def short_name(name):
    return re.split(r"\s*[:\-–—|]\s+|\s+[-–—|]\s*", name, maxsplit=1)[0].strip() or name


def main(run, app_input, country=None):
    app_id, term = appstore.parse_app_input(app_input)
    store = (country or "us").lower()
    resolution = {"input": app_input, "method": "id" if app_id else "search"}
    if not app_id:
        results = appstore.search_apps(term, store)
        best, alts = choose(term, results)
        if not best:
            raise SystemExit("No App Store app matches %r in the %s store" % (term, store.upper()))
        app_id = best["app_id"]
        resolution.update(term=term, store=store, n_matches=len(results), chosen=best, alternatives=alts)
        run.log("Searched %r: %d matches. Picked id%s %s (%s ratings)." % (term, len(results), app_id, best["name"], f"{best['rating_count']:,}"))

    listing = None
    for cc in [store, "us", "gb"]:
        listing = appstore.get_listing(app_id, cc)
        if listing:
            break
    lookup = appstore.lookup_app(app_id, store) or appstore.lookup_app(app_id, "us")
    if not listing and not lookup:
        raise SystemExit("App id%s not found in the App Store" % app_id)

    if listing:
        versions = [v for v in listing["versions"] if v.get("version") and v.get("date")]
        app = {"app_id": app_id, "name": listing["name"], "developer": listing["developer"] or (lookup or {}).get("developer", ""),
               "category": listing["category"] or (lookup or {}).get("category", ""), "price": listing["price"],
               "price_label": listing["price_label"], "in_app_purchases": listing["in_app_purchases"],
               "description": listing["description"] or (lookup or {}).get("description", ""), "subtitle": listing["subtitle"],
               "languages": listing["languages"], "listing_country": listing["country"].upper(), "versions": versions,
               "rating_histogram": listing["rating_histogram"]}
    else:  # lookup fallback: current version only
        app = {"app_id": app_id, "name": lookup["name"], "developer": lookup["developer"], "category": lookup["category"],
               "price": float(lookup["price"] or 0), "price_label": "Free" if not lookup["price"] else lookup["formatted_price"],
               "in_app_purchases": [], "description": lookup["description"] or "", "subtitle": None,
               "languages": lookup["languages"], "listing_country": store.upper(),
               "versions": [{"version": lookup["version"], "date": lookup["current_version_date"], "notes": lookup["release_notes"] or ""}]}
        resolution["listing_fallback"] = "lookup service (no version history)"
    app["app_short"] = short_name(app["name"])
    app["listed_features"] = []  # filled from the description in step 8
    app["store_rating"] = {store.upper(): (lookup or {}).get("rating")}
    app["store_rating_count"] = {store.upper(): (lookup or {}).get("rating_count", 0)}
    app["resolution"] = resolution
    write_json(run.p("app.json"), app, "app")
    run.log("Read the listing: %s, %s, %d versions with release notes, %d in-app purchases." % (
        app["category"], app["price_label"], len(app["versions"]), len(app["in_app_purchases"])))
    run.update_record(app={"app_id": app_id, "name": app["name"], "resolution": resolution})
    return app


if __name__ == "__main__":
    main(Run(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
