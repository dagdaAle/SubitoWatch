"""
Persistent storage for SubitoWatch (channel-based model).

Tables:
* ``channels``          -> user-defined feeds (name + keywords + price filter +
                           optional comune). Each channel is one themed search.
* ``channel_listings``  -> the listings currently belonging to each channel,
                           with a per-channel ``first_seen`` timestamp. This is
                           what powers the "new since last refresh" highlight.
* ``feedback``          -> global favorites (like/dislike) keyed by listing_url,
                           independent of any channel so it survives everything.

The DB is a single SQLite file whose path comes from ``SUBITO_DB`` (defaults to
``subito.db``); in Docker it lives on a mounted volume.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Any, Literal

Verdict = Literal["like", "dislike"]

_DB_PATH = os.environ.get("SUBITO_DB", "subito.db")
_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create all tables if they don't exist yet."""
    with _lock, _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS channels (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                keywords    TEXT NOT NULL,   -- JSON array of search terms
                comune      TEXT DEFAULT '',
                min_price   INTEGER,
                max_price   INTEGER,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                refreshed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_listings (
                channel_id    INTEGER NOT NULL,
                listing_url   TEXT NOT NULL,
                title         TEXT,
                price         INTEGER,
                price_display TEXT,
                town          TEXT,
                city          TEXT,
                date          TEXT,
                thumbnail     TEXT,
                is_shop       INTEGER NOT NULL DEFAULT 0,
                shop_name     TEXT,
                first_seen    TEXT NOT NULL DEFAULT (datetime('now')),
                last_seen     TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (channel_id, listing_url),
                FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                listing_url   TEXT PRIMARY KEY,
                verdict       TEXT NOT NULL CHECK (verdict IN ('like', 'dislike')),
                title         TEXT,
                price         INTEGER,
                price_display TEXT,
                town          TEXT,
                thumbnail     TEXT,
                is_shop       INTEGER NOT NULL DEFAULT 0,
                shop_name     TEXT,
                updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        _migrate(conn)


# Columns each table is expected to have, with the SQL to add them if missing.
# CREATE TABLE IF NOT EXISTS never alters an existing table, so a DB created by
# an older schema (e.g. a feedback table without price_display/town/thumbnail)
# would keep the old columns and break inserts. This lightweight migration adds
# any missing column via ALTER TABLE so persisted data survives schema changes.
_EXPECTED_COLUMNS: dict[str, dict[str, str]] = {
    "channels": {
        "comune": "ALTER TABLE channels ADD COLUMN comune TEXT DEFAULT ''",
        "min_price": "ALTER TABLE channels ADD COLUMN min_price INTEGER",
        "max_price": "ALTER TABLE channels ADD COLUMN max_price INTEGER",
        "refreshed_at": "ALTER TABLE channels ADD COLUMN refreshed_at TEXT",
    },
    "channel_listings": {
        "price_display": "ALTER TABLE channel_listings ADD COLUMN price_display TEXT",
        "town": "ALTER TABLE channel_listings ADD COLUMN town TEXT",
        "city": "ALTER TABLE channel_listings ADD COLUMN city TEXT",
        "date": "ALTER TABLE channel_listings ADD COLUMN date TEXT",
        "thumbnail": "ALTER TABLE channel_listings ADD COLUMN thumbnail TEXT",
        "is_shop": "ALTER TABLE channel_listings ADD COLUMN is_shop INTEGER NOT NULL DEFAULT 0",
        "shop_name": "ALTER TABLE channel_listings ADD COLUMN shop_name TEXT",
    },
    "feedback": {
        "price_display": "ALTER TABLE feedback ADD COLUMN price_display TEXT",
        "town": "ALTER TABLE feedback ADD COLUMN town TEXT",
        "thumbnail": "ALTER TABLE feedback ADD COLUMN thumbnail TEXT",
        "is_shop": "ALTER TABLE feedback ADD COLUMN is_shop INTEGER NOT NULL DEFAULT 0",
        "shop_name": "ALTER TABLE feedback ADD COLUMN shop_name TEXT",
    },
}


def _migrate(conn: sqlite3.Connection) -> None:
    """Add any columns missing from pre-existing tables (idempotent)."""
    for table, columns in _EXPECTED_COLUMNS.items():
        existing = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for column, alter_sql in columns.items():
            if column not in existing:
                conn.execute(alter_sql)


# --------------------------------------------------------------------------- #
# Channels                                                                     #
# --------------------------------------------------------------------------- #


def _row_to_channel(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "keywords": _loads_list(row["keywords"]),
        "comune": row["comune"] or "",
        "min_price": row["min_price"],
        "max_price": row["max_price"],
        "created_at": row["created_at"],
        "refreshed_at": row["refreshed_at"],
    }


def create_channel(
    name: str,
    keywords: list[str],
    *,
    comune: str = "",
    min_price: int | None = None,
    max_price: int | None = None,
) -> dict[str, Any]:
    """Create a channel and return it."""
    name = (name or "").strip()
    kws = [k.strip() for k in keywords if k and k.strip()]
    if not name:
        raise ValueError("channel name is required")
    if not kws:
        raise ValueError("at least one keyword is required")
    with _lock, _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO channels (name, keywords, comune, min_price, max_price)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, json.dumps(kws, ensure_ascii=False), comune, min_price, max_price),
        )
        channel_id = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM channels WHERE id = ?", (channel_id,)
        ).fetchone()
    return _row_to_channel(row)


def list_channels() -> list[dict[str, Any]]:
    """Return all channels, each annotated with counts of listings/new."""
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM channels ORDER BY created_at"
        ).fetchall()
        channels = [_row_to_channel(r) for r in rows]
        for ch in channels:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM channel_listings WHERE channel_id = ?",
                (ch["id"],),
            ).fetchone()["c"]
            new = conn.execute(
                """
                SELECT COUNT(*) AS c FROM channel_listings
                WHERE channel_id = ? AND first_seen = last_seen
                """,
                (ch["id"],),
            ).fetchone()["c"]
            ch["total_count"] = total
            ch["new_count"] = new
    return channels


def get_channel(channel_id: int) -> dict[str, Any] | None:
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT * FROM channels WHERE id = ?", (channel_id,)
        ).fetchone()
    return _row_to_channel(row) if row else None


def delete_channel(channel_id: int) -> None:
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))


def _mark_refreshed(conn: sqlite3.Connection, channel_id: int) -> None:
    conn.execute(
        "UPDATE channels SET refreshed_at = datetime('now') WHERE id = ?",
        (channel_id,),
    )


def upsert_channel_listings(
    channel_id: int, listings: list[dict[str, Any]]
) -> int:
    """
    Store the current listings for a channel. Returns how many were NEW.

    "New" = first time this URL appears in this channel. We keep first_seen
    stable and bump last_seen on every refresh; a listing is considered new when
    first_seen == last_seen (i.e. it was just inserted this refresh).
    """
    new_count = 0
    with _lock, _connect() as conn:
        for item in listings:
            url = item.get("listing_url")
            if not url:
                continue
            existing = conn.execute(
                """
                SELECT 1 FROM channel_listings
                WHERE channel_id = ? AND listing_url = ?
                """,
                (channel_id, url),
            ).fetchone()
            if existing is None:
                new_count += 1
                conn.execute(
                    """
                    INSERT INTO channel_listings
                        (channel_id, listing_url, title, price, price_display,
                         town, city, date, thumbnail, is_shop, shop_name,
                         first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            datetime('now'), datetime('now'))
                    """,
                    (
                        channel_id, url, item.get("title"), item.get("price"),
                        item.get("price_display"), item.get("town"),
                        item.get("city"), item.get("date"), item.get("thumbnail"),
                        int(bool(item.get("is_shop"))), item.get("shop_name"),
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE channel_listings SET
                        title = ?, price = ?, price_display = ?, town = ?,
                        city = ?, date = ?, thumbnail = ?,
                        is_shop = ?, shop_name = ?,
                        last_seen = datetime('now')
                    WHERE channel_id = ? AND listing_url = ?
                    """,
                    (
                        item.get("title"), item.get("price"),
                        item.get("price_display"), item.get("town"),
                        item.get("city"), item.get("date"), item.get("thumbnail"),
                        int(bool(item.get("is_shop"))), item.get("shop_name"),
                        channel_id, url,
                    ),
                )
        _mark_refreshed(conn, channel_id)
    return new_count


def get_channel_listings(channel_id: int) -> list[dict[str, Any]]:
    """
    Return the channel's listings, newest-added first, each with ``is_new``.

    ``is_new`` is true when first_seen == last_seen (added in the last refresh).
    """
    with _lock, _connect() as conn:
        rows = conn.execute(
            """
            SELECT listing_url, title, price, price_display, town, city, date,
                   thumbnail, is_shop, shop_name, first_seen, last_seen,
                   (first_seen = last_seen) AS is_new
            FROM channel_listings
            WHERE channel_id = ?
            ORDER BY is_new DESC, date DESC
            """,
            (channel_id,),
        ).fetchall()
    return [
        {
            "listing_url": r["listing_url"],
            "title": r["title"] or "",
            "price": r["price"],
            "price_display": r["price_display"] or "",
            "town": r["town"] or "",
            "city": r["city"] or "",
            "date": r["date"] or "",
            "thumbnail": r["thumbnail"],
            "is_shop": bool(r["is_shop"]),
            "shop_name": r["shop_name"] or "",
            "is_new": bool(r["is_new"]),
        }
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# Favorites (feedback)                                                         #
# --------------------------------------------------------------------------- #


def set_feedback(
    listing_url: str,
    verdict: Verdict | None,
    *,
    title: str = "",
    price: int | None = None,
    price_display: str = "",
    town: str = "",
    thumbnail: str | None = None,
    is_shop: bool = False,
    shop_name: str = "",
) -> None:
    """Store/update/clear the verdict for a listing (verdict=None clears it)."""
    if not listing_url:
        raise ValueError("listing_url is required")
    with _lock, _connect() as conn:
        if verdict is None:
            conn.execute(
                "DELETE FROM feedback WHERE listing_url = ?", (listing_url,)
            )
            return
        if verdict not in ("like", "dislike"):
            raise ValueError(f"invalid verdict: {verdict!r}")
        conn.execute(
            """
            INSERT INTO feedback
                (listing_url, verdict, title, price, price_display, town,
                 thumbnail, is_shop, shop_name, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(listing_url) DO UPDATE SET
                verdict       = excluded.verdict,
                title         = excluded.title,
                price         = excluded.price,
                price_display = excluded.price_display,
                town          = excluded.town,
                thumbnail     = excluded.thumbnail,
                is_shop       = excluded.is_shop,
                shop_name     = excluded.shop_name,
                updated_at    = datetime('now')
            """,
            (
                listing_url, verdict, title, price, price_display, town,
                thumbnail, int(bool(is_shop)), shop_name,
            ),
        )


def get_all_feedback() -> dict[str, str]:
    """Return ``{listing_url: verdict}`` for every listing with feedback."""
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT listing_url, verdict FROM feedback"
        ).fetchall()
    return {row["listing_url"]: row["verdict"] for row in rows}


def get_favorites() -> list[dict[str, Any]]:
    """Return full details of all liked listings (for the Favorites view)."""
    with _lock, _connect() as conn:
        rows = conn.execute(
            """
            SELECT listing_url, title, price, price_display, town, thumbnail,
                   is_shop, shop_name, updated_at
            FROM feedback
            WHERE verdict = 'like'
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return [
        {
            "listing_url": r["listing_url"],
            "title": r["title"] or "",
            "price": r["price"],
            "price_display": r["price_display"] or "",
            "town": r["town"] or "",
            "thumbnail": r["thumbnail"],
            "is_shop": bool(r["is_shop"]),
            "shop_name": r["shop_name"] or "",
        }
        for r in rows
    ]


def _loads_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []
