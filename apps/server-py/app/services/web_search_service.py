"""Web search service (free, no API key).

Originally targeted DuckDuckGo, but DuckDuckGo is unreachable from the
container's network (blocked in CN). Falls back to Bing HTML search which
is reachable and returns rich result snippets. No API key required.

Returns a list of {title, url, snippet} dicts.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BING_URL = "https://www.bing.com/search"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


async def search_web(query: str, *, max_results: int = 8) -> list[dict[str, Any]]:
    """Search Bing and return result dicts with title/url/snippet."""

    query = (query or "").strip()
    if not query:
        return []
    limit = max(1, min(int(max_results or 8), 20))
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(_BING_URL, params={"q": query, "count": str(limit * 2)}, headers=_HEADERS)
            html = resp.text
    except Exception as exc:
        logger.warning("Web search failed: %s", exc)
        return [{"error": f"Search request failed: {exc}"}]

    results: list[dict[str, Any]] = []
    # Bing organic results: <li class="b_algo"> with <h2><a href="URL">TITLE</a></h2> and <p>snippet</p>
    blocks = re.findall(r'<li[^>]+class="b_algo"[^>]*>(.*?)</li>', html, re.DOTALL)
    for block in blocks:
        link_m = re.search(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not link_m:
            continue
        url = link_m.group(1)
        title = re.sub(r"<[^>]+>", "", link_m.group(2)).strip()
        snippet_m = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
        snippet = re.sub(r"<[^>]+>", "", snippet_m.group(1)).strip() if snippet_m else ""
        if not title:
            title = url
        results.append({"title": title, "url": url, "snippet": snippet[:500]})
        if len(results) >= limit:
            break
    if not results:
        return [{"error": "No results found. Bing may have changed its HTML structure."}]
    return results
