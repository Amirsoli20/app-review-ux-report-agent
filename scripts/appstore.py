"""Client for Apple's public App Store services, with a rate limit shared by every process.

Services used
- iTunes Search API  (search):  https://itunes.apple.com/search
- iTunes Lookup API  (lookup):  https://itunes.apple.com/lookup            ~20 calls per minute (NFR-2)
- App Store web catalog (reviews, listing): https://apps.apple.com/api/apps/v1/catalog/...
  This is the same-origin API the public apps.apple.com pages read. It serves reviews newest first,
  20 per page, and the full listing (description, version history, in-app purchases, rating count).
  Apple's older customer-review RSS feed returns no entries any more, so it is not used.
"""
import fcntl
import json
import os
import re
import time
from pathlib import Path

import httpx

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"
CATALOG = "https://apps.apple.com/api/apps/v1/catalog"
CACHE = Path(os.environ.get("APP_REVIEW_CACHE", Path.home() / ".cache" / "app-review-ux"))

RATES = {"lookup": 20, "web": 120}  # calls per minute; overridden by settings via configure()


def configure(settings):
    RATES["lookup"] = int(settings.get("lookup_calls_per_minute", RATES["lookup"]))
    RATES["web"] = int(settings.get("review_calls_per_minute", RATES["web"]))


class RateLimiter:
    """Sliding-window limiter stored in a lock file, so parallel processes share one budget."""

    def __init__(self, bucket):
        self.bucket = bucket
        CACHE.mkdir(parents=True, exist_ok=True)
        self.path = CACHE / ("rate-%s.json" % bucket)

    def wait(self):
        per_min = RATES[self.bucket]
        while True:
            with open(self.path, "a+") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.seek(0)
                try:
                    stamps = json.loads(f.read() or "[]")
                except ValueError:
                    stamps = []
                now = time.time()
                stamps = [t for t in stamps if now - t < 60]
                if len(stamps) < per_min:
                    stamps.append(now)
                    f.seek(0)
                    f.truncate()
                    f.write(json.dumps(stamps))
                    return
                delay = 60 - (now - stamps[0]) + 0.05
            time.sleep(max(0.05, delay))


_limiters = {}
_client = None


def _http():
    global _client
    if _client is None:
        _client = httpx.Client(headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30,
                               follow_redirects=True)
    return _client


def get_json(url, params=None, bucket="web", attempts=6):
    """GET with rate limit, and backoff on 403/429/5xx and network errors."""
    lim = _limiters.setdefault(bucket, RateLimiter(bucket))
    last = None
    for a in range(attempts):
        lim.wait()
        try:
            r = _http().get(url, params=params)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
            last = "HTTP %d: %s" % (r.status_code, r.text[:200])
            if r.status_code == 429:  # Apple's capacity limit: wait longer, honouring Retry-After when sent
                ra = r.headers.get("Retry-After")
                time.sleep(float(ra) if ra and ra.isdigit() else [20, 45, 90, 120, 180, 240][a])
                continue
        except (httpx.HTTPError, ValueError) as e:
            last = repr(e)
        time.sleep([3, 10, 30, 60, 90, 120][a])
    raise RuntimeError("request failed after %d attempts: %s %s (%s)" % (attempts, url, params, last))


# ---------- search and lookup ----------

def search_apps(term, country="us", limit=15):
    d = get_json("https://itunes.apple.com/search",
                 {"term": term, "country": country, "entity": "software", "limit": limit}, bucket="lookup")
    out = []
    for x in (d or {}).get("results", []):
        out.append({"app_id": str(x["trackId"]), "name": x.get("trackName", ""), "developer": x.get("sellerName") or x.get("artistName", ""),
                    "rating_count": int(x.get("userRatingCount") or 0), "rating": x.get("averageUserRating"),
                    "category": x.get("primaryGenreName"), "url": x.get("trackViewUrl")})
    return out


def lookup_app(app_id, country="us"):
    """Rating count and average for one country store. None when the app is not in that store."""
    d = get_json("https://itunes.apple.com/lookup", {"id": app_id, "country": country}, bucket="lookup")
    res = (d or {}).get("results") or []
    if not res:
        return None
    x = res[0]
    return {"app_id": str(x["trackId"]), "country": country, "name": x.get("trackName"),
            "rating_count": int(x.get("userRatingCount") or 0), "rating": x.get("averageUserRating"),
            "version": x.get("version"), "description": x.get("description"), "release_notes": x.get("releaseNotes"),
            "current_version_date": (x.get("currentVersionReleaseDate") or "")[:10], "price": x.get("price"),
            "formatted_price": x.get("formattedPrice"), "currency": x.get("currency"),
            "category": x.get("primaryGenreName"), "developer": x.get("sellerName") or x.get("artistName"),
            "languages": x.get("languageCodesISO2A") or []}


# ---------- reviews ----------

def get_reviews(app_id, country, page=1, page_size=20):
    """One page of written reviews, newest first. page is 1-based."""
    offset = (page - 1) * page_size
    d = get_json("%s/%s/apps/%s/reviews" % (CATALOG, country, app_id),
                 {"offset": offset, "limit": page_size, "platform": "web", "sort": "recent",
                  "additionalPlatforms": "appletv,ipad,iphone,mac"})
    if d is None:
        return {"reviews": [], "next": False}
    out = []
    for x in d.get("data", []):
        a = x.get("attributes", {})
        out.append({"apple_id": str(x.get("id")), "date": a.get("date"), "rating": a.get("rating"),
                    "title": a.get("title") or "", "body": a.get("review") or "", "user_name": a.get("userName") or "",
                    "is_edited": bool(a.get("isEdited"))})
    return {"reviews": out, "next": bool(d.get("next"))}


# ---------- listing ----------

def _price_label(offers, iaps):
    get = next((o for o in offers or [] if o.get("type") in ("get", "buy")), None)
    price = (get or {}).get("price") or 0
    base = "Free" if not price else (get.get("priceFormatted") or str(price))
    if not iaps:
        return base + ", no in-app purchases" if base == "Free" else base
    return base + ", with in-app purchases"


def get_listing(app_id, country="us"):
    """Description, price, in-app purchases, rating, languages and version history with release notes."""
    params = {"platform": "iphone", "additionalPlatforms": "ipad", "extend": "versionHistory,description",
              "include": "top-in-apps,genres,developer"}
    if country == "us":
        params["l"] = "en-US"
    d = get_json("%s/%s/apps/%s" % (CATALOG, country, app_id), params)
    if not d or not d.get("data"):
        return None
    a = d["data"][0]
    at = a.get("attributes", {})
    ios = (at.get("platformAttributes") or {}).get("ios") or {}
    iaps, seen = [], set()
    for x in (a.get("relationships", {}).get("top-in-apps", {}) or {}).get("data", []):
        xa = x.get("attributes", {})
        offer = (xa.get("offers") or [{}])[0]
        key = (xa.get("name"), offer.get("priceFormatted"))
        if key in seen:
            continue
        seen.add(key)
        iaps.append({"name": xa.get("name"), "price": offer.get("priceFormatted")})
    versions = [{"version": v.get("versionDisplay"), "date": v.get("releaseDate"), "notes": (v.get("releaseNotes") or "").strip()}
                for v in ios.get("versionHistory") or []]
    desc = (ios.get("description") or {}).get("standard") or ""
    rating = at.get("userRating") or {}
    return {"app_id": str(a.get("id")), "country": country, "name": at.get("name"), "subtitle": ios.get("subtitle"),
            "developer": at.get("artistName") or (ios.get("seller") or ""), "category": at.get("genreDisplayName"),
            "description": desc, "price_label": _price_label(ios.get("offers"), iaps), "in_app_purchases": iaps,
            "price": float(((ios.get("offers") or [{}])[0]).get("price") or 0),
            "store_rating": rating.get("value"), "store_rating_count": int(rating.get("ratingCount") or 0),
            "rating_histogram": rating.get("ratingCountList"), "languages": ios.get("languageList") or [],
            "versions": versions, "url": at.get("url")}


def parse_app_input(text):
    """Return (app_id or None, term). Accepts an App Store link, an id ('id123', '123') or a name."""
    t = text.strip()
    m = re.search(r"/id(\d{5,})", t) or re.fullmatch(r"(?:id)?(\d{5,})", t)
    if m:
        return m.group(1), None
    return None, t
