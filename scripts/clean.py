"""Step 4. Clean: remove duplicates, detect language, infer app version, record country date windows.

-> clean/reviews.jsonl, clean/windows.json

Apple's review data carries no app version, so each review gets the version that was current in the
store on its date, from the listing's version history (`version_inferred: true`).
"""
import bisect
import collections
import datetime as dt
import sys
import unicodedata

from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException

from common import Run, read_json, write_json, write_jsonl

DetectorFactory.seed = 0


def norm_text(t):
    return " ".join(unicodedata.normalize("NFC", t or "").split()).lower()


def detect_language(text):
    t = (text or "").strip()
    if len(t) < 12:
        return "und"
    try:
        best = detect_langs(t)[0]
        return best.lang if best.prob >= 0.6 else "und"
    except LangDetectException:
        return "und"


def version_finder(versions):
    vs = sorted([(v["date"], v["version"]) for v in versions if v.get("date")])
    dates = [d for d, _ in vs]

    def at(date):
        if not vs:
            return "unknown"
        i = bisect.bisect_right(dates, date) - 1
        return vs[i][1] if i >= 0 else "≤" + vs[0][1]
    return at


def window_label(d0, d1):
    a, b = dt.date.fromisoformat(d0), dt.date.fromisoformat(d1)
    return "%s %d to %s %d" % (a.strftime("%b"), a.day, b.strftime("%b"), b.day)


def main(run):
    app = read_json(run.p("app.json"))
    countries = read_json(run.p("countries.json"))["countries"]
    version_at = version_finder(app["versions"])
    seen_ids, seen_text = set(), set()
    out, dup_id, dup_text = [], 0, 0
    for c in countries:
        raw = read_json(run.p("raw", c["code"] + ".json"))
        for r in raw["reviews"]:
            rid = "%s-%s" % (c["code"], r["apple_id"])
            key = (r["author_hash"], norm_text(r["title"] + " " + r["body"]))
            if rid in seen_ids:
                dup_id += 1
                continue
            if key in seen_text:
                dup_text += 1
                continue
            seen_ids.add(rid)
            seen_text.add(key)
            date = (r["date"] or "")[:10]
            out.append({"review_id": rid, "country": c["code"], "rating": int(r["rating"]),
                        "title": r["title"].strip(), "body": r["body"].strip(),
                        "language": detect_language(r["title"] + ". " + r["body"]),
                        "app_version": version_at(date), "version_inferred": True,
                        "date": date, "author_hash": r["author_hash"]})
    write_jsonl(run.p("clean", "reviews.jsonl"), out, "review")

    windows = {}
    for c in countries:
        ds = sorted(r["date"] for r in out if r["country"] == c["code"])
        langs = collections.Counter(r["language"] for r in out if r["country"] == c["code"] and r["language"] != "und")
        if ds:
            days = (dt.date.fromisoformat(ds[-1]) - dt.date.fromisoformat(ds[0])).days + 1
            windows[c["code"]] = {"start": ds[0], "end": ds[-1], "days": days, "label": window_label(ds[0], ds[-1]),
                                  "n": len(ds), "languages": dict(langs.most_common())}
        else:
            windows[c["code"]] = {"start": None, "end": None, "days": 0, "label": "no reviews", "n": 0, "languages": {}}
    write_json(run.p("clean", "windows.json"), windows)
    run.log("Cleaned: %d duplicates by review ID and %d by identical author and text removed, %d kept." % (dup_id, dup_text, len(out)))
    run.update_record(counts={"clean": {"in": len(out) + dup_id + dup_text, "dup_id": dup_id, "dup_text": dup_text, "kept": len(out)}})
    return out


if __name__ == "__main__":
    main(Run(sys.argv[1]))
