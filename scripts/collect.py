"""Step 3. Collect the most recent written reviews per selected country -> raw/<CC>.json.

Reviewer names are hashed here, before anything is written, so no output holds a name (NFR-5).
A country that fails is retried once, then logged; the run continues (NFR-9).
"""
import math
import sys
from concurrent.futures import ThreadPoolExecutor

import appstore
from common import Run, read_json, run_settings, sha, write_json


def collect_country(app_id, cc, limit, page_size, salt, state):
    """Fetch pages into `state` (reviews, next page), so a retry continues where the last attempt stopped."""
    pages = math.ceil(limit / page_size)
    while state["page"] <= pages and len(state["reviews"]) < limit and not state["done"]:
        res = appstore.get_reviews(app_id, cc.lower(), state["page"], page_size)
        state["fetched"] += 1
        for r in res["reviews"]:
            r["author_hash"] = sha(salt + r.pop("user_name"), 16)
            state["reviews"].append(r)
        state["page"] += 1
        state["done"] = not res["next"]
    return {"country": cc, "pages": state["fetched"], "reviews": state["reviews"][:limit], "errors": []}


def main(run):
    s = run_settings(run)
    appstore.configure(s)
    app = read_json(run.p("app.json"))
    countries = read_json(run.p("countries.json"))["countries"]
    salt = "app-review-ux:" + app["app_id"]

    def job(c):
        cc = c["code"]
        out = run.p("raw", cc + ".json")
        last = None
        state = {"page": 1, "reviews": [], "fetched": 0, "done": False}
        for attempt in (1, 2):
            try:
                data = collect_country(app["app_id"], cc, s["reviews_per_country"], s["review_page_size"], salt, state)
                data["attempts"] = attempt
                write_json(out, data)
                return cc, len(data["reviews"]), data["pages"], None
            except Exception as e:  # noqa: BLE001 - one country must not stop the run
                last = repr(e)
                run.log("Collecting %s failed (attempt %d): %s" % (cc, attempt, last))
        # keep the pages that did arrive; the country is used with fewer reviews and the failure is logged
        write_json(out, {"country": cc, "pages": state["fetched"], "reviews": state["reviews"][:s["reviews_per_country"]],
                         "errors": [last], "attempts": 2, "partial": True})
        return cc, len(state["reviews"]), state["fetched"], last

    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(job, countries))
    pages = sum(r[2] for r in res)
    total = sum(r[1] for r in res)
    failed = [r[0] for r in res if r[3]]
    run.log("Collected %d reviews from %d feed pages in %d countries%s." % (
        total, pages, len(res), (" (failed: %s)" % ", ".join(failed)) if failed else ""))
    run.update_record(counts={"collect": {"pages": pages, "reviews": total, "failed_countries": failed,
                                          "per_country": {r[0]: r[1] for r in res}}})
    return total


if __name__ == "__main__":
    main(Run(sys.argv[1]))
