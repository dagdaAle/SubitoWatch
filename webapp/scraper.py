"""
Scraper for Subito.it listings, focused on the province of Verona.

Subito.it is a Next.js site: the search results are embedded as JSON in a
``<script id="__NEXT_DATA__">`` blob. Parsing that JSON is far more stable than
scraping the rendered HTML, so that's what we do here.

Public entry point: :func:`search`. It builds a Subito search URL for the
Verona province (optionally narrowed to a comune), fetches the page(s), and
returns a normalized list of listing dicts.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

# curl_cffi impersonates a real browser's TLS/JA3 fingerprint. Subito.it's WAF
# blocks plain ``requests`` (HTTP 403) based on that fingerprint, regardless of
# headers or IP, so we must use a client that looks like Chrome at the TLS level.
from curl_cffi import requests

# Verona lives in the Veneto region on Subito's URL scheme:
#   https://www.subito.it/annunci-{region}/vendita/{condition}/{provincia}/?q={query}
_BASE_URL = "https://www.subito.it/annunci-veneto/vendita/usato/verona/"

# Subito serves images from a CDN that returns 400/404 unless a "rule" query
# param (image size preset) is appended. This is the preset the site itself uses.
_IMG_RULE = "gallery-desktop-2x-auto"

# Subito blocks obvious bots; present a normal desktop browser UA.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.S,
)


def _extract_ads(html: str) -> list[dict[str, Any]]:
    """Pull the ad list out of a Subito search page's __NEXT_DATA__ blob."""
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except (ValueError, TypeError):
        return []
    try:
        items = data["props"]["pageProps"]["initialState"]["items"]
    except (KeyError, TypeError):
        return []
    # originalList is the full result list (30/page); it already includes the
    # gallery items, so we don't merge galleryList/boostedItems to avoid dupes.
    ads = items.get("originalList")
    return ads if isinstance(ads, list) else []


def _price_of(ad: dict[str, Any]) -> tuple[int | None, str]:
    """Return (numeric_price, display_price) from an ad's features dict."""
    feats = ad.get("features") or {}
    price_feat = feats.get("/price") or {}
    values = price_feat.get("values") or []
    if not values:
        return None, ""
    first = values[0] or {}
    display = str(first.get("value", "")).strip()  # e.g. "8890 €"
    key = first.get("key")  # e.g. "8890" (raw number as string)
    numeric: int | None = None
    if key is not None:
        try:
            numeric = int(float(key))
        except (ValueError, TypeError):
            numeric = None
    if numeric is None and display:
        # Fallback: strip non-digits from the display string.
        digits = re.sub(r"[^\d]", "", display)
        numeric = int(digits) if digits else None
    return numeric, display


def _thumb_of(ad: dict[str, Any]) -> str | None:
    images = ad.get("images") or []
    if not images:
        return None
    base = (images[0] or {}).get("cdnBaseUrl")
    if not base:
        return None
    # The CDN requires a size "rule" param, otherwise it returns 400/404.
    return f"{base}?rule={_IMG_RULE}"


def _shop_of(ad: dict[str, Any]) -> tuple[bool, str]:
    """
    Return (is_shop, shop_name) for an ad's advertiser.

    Subito's ``advertiser`` block flags professional sellers with
    ``company: true`` (and usually a ``shopId``/``shopName``); private
    sellers have ``company: false`` and no shop info. We treat an ad as a
    shop when it's a company or exposes a shopId.
    """
    adv = ad.get("advertiser") or {}
    is_shop = bool(adv.get("company")) or bool(adv.get("shopId"))
    shop_name = str(adv.get("shopName") or adv.get("name") or "").strip()
    return is_shop, shop_name


def _normalize(ad: dict[str, Any]) -> dict[str, Any] | None:
    """Turn a raw Subito ad into our normalized listing dict (or None if unusable)."""
    if ad.get("kind") != "AdItem":
        return None
    url = (ad.get("urls") or {}).get("default")
    if not url:
        return None
    numeric_price, display_price = _price_of(ad)
    geo = ad.get("geo") or {}
    is_shop, shop_name = _shop_of(ad)
    return {
        "listing_url": url,
        "title": ad.get("subject") or "",
        "price": numeric_price,
        "price_display": display_price,
        "town": (geo.get("town") or {}).get("value") or "",
        "city": (geo.get("city") or {}).get("value") or "",
        "date": ad.get("date") or "",
        "thumbnail": _thumb_of(ad),
        "description": ad.get("body") or "",
        "is_shop": is_shop,
        "shop_name": shop_name,
    }


def search(
    query: str,
    *,
    comune: str = "",
    min_price: int | None = None,
    max_price: int | None = None,
    pages: int = 1,
) -> list[dict[str, Any]]:
    """
    Search Subito.it (Verona province) for ``query``.

    ``comune`` optionally narrows the results to a single town (client-side
    filter on the ``town`` field, case-insensitive substring match).
    ``min_price``/``max_price`` filter on the numeric price (listings with no
    price pass the filter only when no bound is set on that side).
    ``pages`` fetches multiple result pages (Subito paginates via ``?o=N``).
    """
    query = (query or "").strip()
    if not query:
        return []

    collected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for page in range(1, max(1, pages) + 1):
        params: dict[str, Any] = {"q": query}
        if page > 1:
            params["o"] = page
        try:
            resp = requests.get(
                _BASE_URL,
                params=params,
                headers=_HEADERS,
                timeout=20,
                impersonate="chrome",
            )
            resp.raise_for_status()
        except Exception as exc:  # curl_cffi raises RequestsError / HTTPError
            raise RuntimeError(f"Errore nel contattare Subito.it: {exc}") from exc

        ads = _extract_ads(resp.text)
        if not ads:
            break  # no more results / structure changed

        for raw in ads:
            listing = _normalize(raw)
            if listing is None:
                continue
            if listing["listing_url"] in seen_urls:
                continue
            seen_urls.add(listing["listing_url"])
            collected.append(listing)

        # Be polite between page fetches.
        if page < pages:
            time.sleep(1.0)

    # Client-side filters.
    # The search URL already restricts to the province of Verona, so ``city`` is
    # always "Verona". Leaving ``comune`` empty therefore returns the whole
    # province. When set, we narrow to a single comune by matching either the
    # ``town`` (the actual comune, e.g. "Legnago") or the ``city`` field.
    comune_needle = comune.strip().lower()
    results: list[dict[str, Any]] = []
    for item in collected:
        if comune_needle and (
            comune_needle not in item["town"].lower()
            and comune_needle not in item["city"].lower()
        ):
            continue
        price = item["price"]
        if min_price is not None and (price is None or price < min_price):
            continue
        if max_price is not None and (price is None or price > max_price):
            continue
        results.append(item)

    return results


def search_keywords(
    keywords: list[str],
    *,
    comune: str = "",
    min_price: int | None = None,
    max_price: int | None = None,
    pages: int = 1,
) -> list[dict[str, Any]]:
    """
    Run :func:`search` for each keyword and merge the results, deduped by URL.

    This backs a "channel" that follows several search terms at once (e.g. a
    "Tecnologia" channel tracking iphone + macbook + cuffie). A failure on one
    keyword doesn't sink the others.
    """
    merged: dict[str, dict[str, Any]] = {}
    for kw in keywords:
        kw = (kw or "").strip()
        if not kw:
            continue
        try:
            for item in search(
                kw,
                comune=comune,
                min_price=min_price,
                max_price=max_price,
                pages=pages,
            ):
                merged.setdefault(item["listing_url"], item)
        except RuntimeError:
            # Skip a keyword that failed; keep results from the others.
            continue
    return list(merged.values())
