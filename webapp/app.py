"""
SubitoWatch: a small local web app to monitor Subito.it listings in the
province of Verona, organized into user-defined "channels".

A channel is a themed feed (e.g. "Moto", "Tecnologia") made of one or more
search keywords plus optional comune/price filters. Refreshing a channel runs
all its keywords on Subito, dedupes, and stores the results, flagging which
listings are new since the last refresh.

Endpoints:
* ``GET  /``                        -> serves the single-page UI.
* ``GET  /channels``                -> list channels (with total/new counts).
* ``POST /channels``                -> create a channel.
* ``DELETE /channels/{id}``         -> delete a channel (and its listings).
* ``POST /channels/{id}/refresh``   -> re-run the channel's searches on Subito.
* ``GET  /channels/{id}/listings``  -> listings for a channel (+ feedback map).
* ``POST /feedback``                -> store/clear a like/dislike for a listing.
* ``GET  /favorites``               -> all liked listings (global).

A background thread refreshes every channel once a day so the feeds stay fresh
even without manual interaction. Meant for local, personal use (run via Docker);
it does no auth. Persistence is a single SQLite file (see ``storage.py``).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import scraper
import storage

app = FastAPI(title="SubitoWatch", version="2.0.0")

# How often the background scheduler refreshes all channels (seconds).
_REFRESH_INTERVAL_SECONDS = 24 * 60 * 60  # once a day


class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=1)
    keywords: list[str] = Field(..., min_length=1)
    comune: str = ""
    min_price: int | None = Field(None, ge=0)
    max_price: int | None = Field(None, ge=0)


class ChannelUpdate(BaseModel):
    """Partial update: only the fields sent are changed."""
    name: str | None = Field(None, min_length=1)
    keywords: list[str] | None = Field(None, min_length=1)
    comune: str | None = None
    min_price: int | None = Field(None, ge=0)
    max_price: int | None = Field(None, ge=0)


class FeedbackRequest(BaseModel):
    listing_url: str = Field(..., min_length=1)
    verdict: Literal["like", "dislike"] | None = None
    title: str = ""
    price: int | None = None
    price_display: str = ""
    town: str = ""
    thumbnail: str | None = None
    is_shop: bool = False
    shop_name: str = ""


def _refresh_channel(channel: dict[str, Any]) -> int:
    """Run a channel's searches on Subito and store results. Returns new count."""
    listings = scraper.search_keywords(
        channel["keywords"],
        comune=channel["comune"],
        min_price=channel["min_price"],
        max_price=channel["max_price"],
    )
    return storage.upsert_channel_listings(channel["id"], listings)


def _scheduler_loop() -> None:
    """Background thread: refresh every channel once per interval."""
    # Small initial delay so startup isn't blocked by network I/O.
    time.sleep(30)
    while True:
        try:
            for channel in storage.list_channels():
                try:
                    _refresh_channel(channel)
                except Exception:
                    # One channel failing shouldn't stop the others.
                    continue
        except Exception:
            pass
        time.sleep(_REFRESH_INTERVAL_SECONDS)


@app.on_event("startup")
def _startup() -> None:
    storage.init_db()
    thread = threading.Thread(target=_scheduler_loop, daemon=True)
    thread.start()


# --------------------------------------------------------------------------- #
# Channels                                                                     #
# --------------------------------------------------------------------------- #


@app.get("/channels")
def get_channels() -> dict[str, Any]:
    return {"channels": storage.list_channels()}


@app.post("/channels")
def add_channel(req: ChannelCreate) -> dict[str, Any]:
    try:
        channel = storage.create_channel(
            req.name,
            req.keywords,
            comune=req.comune,
            min_price=req.min_price,
            max_price=req.max_price,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Populate it immediately so the user sees results right away.
    try:
        new_count = _refresh_channel(channel)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    channel["new_count"] = new_count
    channel["total_count"] = new_count
    return {"channel": channel}


@app.put("/channels/{channel_id}")
def update_channel(channel_id: int, req: ChannelUpdate) -> dict[str, Any]:
    """Change a channel's name/filters. The new filters apply from the next refresh."""
    try:
        channel = storage.update_channel(channel_id, req.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if channel is None:
        raise HTTPException(status_code=404, detail="Canale non trovato.")
    return {"channel": channel}


@app.delete("/channels/{channel_id}")
def remove_channel(channel_id: int) -> dict[str, Any]:
    storage.delete_channel(channel_id)
    return {"ok": True, "id": channel_id}


@app.post("/channels/{channel_id}/refresh")
def refresh_channel(channel_id: int) -> dict[str, Any]:
    channel = storage.get_channel(channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="channel not found")
    try:
        new_count = _refresh_channel(channel)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ok": True,
        "id": channel_id,
        "new_count": new_count,
        "listings": storage.get_channel_listings(channel_id),
        "feedback": storage.get_all_feedback(),
    }


@app.get("/channels/{channel_id}/listings")
def channel_listings(channel_id: int) -> dict[str, Any]:
    channel = storage.get_channel(channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="channel not found")
    return {
        "channel": channel,
        "listings": storage.get_channel_listings(channel_id),
        "feedback": storage.get_all_feedback(),
    }


# --------------------------------------------------------------------------- #
# Favorites (feedback)                                                         #
# --------------------------------------------------------------------------- #


@app.post("/feedback")
def set_feedback(req: FeedbackRequest) -> dict[str, Any]:
    storage.set_feedback(
        req.listing_url,
        req.verdict,
        title=req.title,
        price=req.price,
        price_display=req.price_display,
        town=req.town,
        thumbnail=req.thumbnail,
        is_shop=req.is_shop,
        shop_name=req.shop_name,
    )
    return {"ok": True, "listing_url": req.listing_url, "verdict": req.verdict}


@app.get("/favorites")
def favorites() -> dict[str, Any]:
    return {"favorites": storage.get_favorites()}


# Serve the SPA. Mounted last so API routes take precedence.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
