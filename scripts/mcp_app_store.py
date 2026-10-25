"""`app-store` MCP server: Apple's public App Store search, lookup, reviews and listing, with the rate limit
shared with the pipeline scripts (see appstore.py).

Tools: search_apps(term, country), lookup_app(id, country), get_reviews(id, country, page), get_listing(id, country)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as Server

import appstore  # noqa: E402
from common import load_settings  # noqa: E402

appstore.configure(load_settings())
mcp = Server("app-store")


@mcp.tool()
def search_apps(term: str, country: str = "us") -> list:
    """Search the App Store for iOS apps by name. Returns id, name, developer, rating count and average per match."""
    return appstore.search_apps(term, country.lower())


@mcp.tool()
def lookup_app(id: str, country: str = "us") -> dict:
    """Rating count and average rating of one app in one country store (null when the app is not sold there)."""
    return appstore.lookup_app(id, country.lower()) or {"app_id": id, "country": country, "found": False}


@mcp.tool()
def get_reviews(id: str, country: str = "us", page: int = 1) -> dict:
    """One page (20) of the most recent written reviews of an app in one country store, newest first.
    Reviewer names are replaced by a hash."""
    from common import sha
    res = appstore.get_reviews(id, country.lower(), page)
    for r in res["reviews"]:
        r["author_hash"] = sha("app-review-ux:" + id + r.pop("user_name"), 16)
    return res


@mcp.tool()
def get_listing(id: str, country: str = "us") -> dict:
    """The app's App Store page: description, price, in-app purchases, rating, languages and version history
    with release notes."""
    return appstore.get_listing(id, country.lower()) or {"app_id": id, "country": country, "found": False}


if __name__ == "__main__":
    mcp.run()
