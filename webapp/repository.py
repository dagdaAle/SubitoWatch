"""BuyWatcher data layer. Legacy tables remain untouched; all migrations additive."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from typing import Any

import storage

_LOCK = threading.RLock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@contextmanager
def connect():
    path = os.getenv('BUYWATCHER_DB') or storage._DB_PATH
    with _LOCK, closing(sqlite3.connect(path, timeout=20)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        yield conn


def init_db():
    if os.getenv('BUYWATCHER_DB'):
        storage._DB_PATH = os.environ['BUYWATCHER_DB']
    storage.init_db()
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS bw_topics (
            id INTEGER PRIMARY KEY, body TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, legacy_channel_id INTEGER UNIQUE
        );
        CREATE TABLE IF NOT EXISTS bw_listings (
            id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, source TEXT NOT NULL,
            body TEXT NOT NULL, content_hash TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bw_snapshots (
            id INTEGER PRIMARY KEY, listing_id INTEGER NOT NULL REFERENCES bw_listings(id),
            body TEXT NOT NULL, content_hash TEXT NOT NULL, captured_at TEXT NOT NULL,
            UNIQUE(listing_id, content_hash)
        );
        CREATE TABLE IF NOT EXISTS bw_matches (
            topic_id INTEGER NOT NULL REFERENCES bw_topics(id) ON DELETE CASCADE,
            listing_id INTEGER NOT NULL REFERENCES bw_listings(id),
            state TEXT NOT NULL DEFAULT 'pending', analysis TEXT, evaluation_key TEXT,
            error TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, evaluated_at TEXT,
            PRIMARY KEY(topic_id, listing_id)
        );
        CREATE TABLE IF NOT EXISTS bw_runs (
            id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL REFERENCES bw_topics(id) ON DELETE CASCADE,
            state TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, report TEXT NOT NULL DEFAULT '{}'
        );
        CREATE UNIQUE INDEX IF NOT EXISTS bw_one_run ON bw_runs(topic_id) WHERE state='running';
        CREATE TABLE IF NOT EXISTS bw_feedback (
            topic_id INTEGER NOT NULL REFERENCES bw_topics(id) ON DELETE CASCADE,
            listing_id INTEGER NOT NULL REFERENCES bw_listings(id), verdict TEXT NOT NULL,
            PRIMARY KEY(topic_id, listing_id)
        );
        ''')
        # Restart recovery; network work is never continued with an abandoned lock.
        db.execute("UPDATE bw_runs SET state='interrupted', finished_at=? WHERE state='running'", (now(),))
        db.execute("UPDATE bw_matches SET state='pending' WHERE state='evaluating'")
    migrate_legacy()


def migrate_legacy():
    for channel in storage.list_channels():
        with connect() as db:
            existing = db.execute('SELECT id FROM bw_topics WHERE legacy_channel_id=?', (channel['id'],)).fetchone()
            if existing:
                continue
            body = dict(name=channel['name'], need='Ricerca importata: '+', '.join(channel['keywords']),
                        keywords=channel['keywords'], requirements=[], preferences=[], exclusions=[],
                        accepted_defects='', budget=channel['max_price'], location=channel['comune'],
                        shipping_allowed=True, sources=['subito'], relevance_threshold=70,
                        interval_hours=24, active=False)
            stamp = now()
            cur = db.execute('INSERT INTO bw_topics(body,created_at,updated_at,legacy_channel_id) VALUES(?,?,?,?)',
                             (json.dumps(body), stamp, stamp, channel['id']))
            topic_id = cur.lastrowid
        with storage._lock, storage._connect() as db:
            ads = db.execute('SELECT * FROM channel_listings WHERE channel_id=?', (channel['id'],)).fetchall()
        for row in ads:
            ad = dict(row)
            record = dict(listing_url=ad['listing_url'], title=ad['title'] or '', description='',
                          price=ad['price'], shipping_cost=None, fees=None, currency='EUR', town=ad['town'] or '',
                          images=[ad['thumbnail']] if ad['thumbnail'] else [], condition='', seller=ad['shop_name'] or '',
                          is_shop=bool(ad['is_shop']), buying_format='unknown', source='subito', external_id='',
                          published_at=ad['date'] or '', availability='unknown')
            listing_id = save_listing(topic_id, record)
            verdict = storage.get_all_feedback().get(ad['listing_url'])
            if verdict:
                set_feedback(topic_id, listing_id, verdict)


def topic_row(row):
    return {**json.loads(row['body']), 'id': row['id'], 'revision': row['revision'],
            'created_at': row['created_at'], 'updated_at': row['updated_at']}


def list_topics():
    with connect() as db:
        rows = db.execute('SELECT * FROM bw_topics ORDER BY created_at').fetchall()
        topics = [topic_row(r) for r in rows]
        for t in topics:
            t['counts'] = dict(db.execute('SELECT state,COUNT(*) FROM bw_matches WHERE topic_id=? GROUP BY state', (t['id'],)).fetchall())
            run = db.execute('SELECT * FROM bw_runs WHERE topic_id=? ORDER BY id DESC LIMIT 1', (t['id'],)).fetchone()
            t['last_run'] = run_row(run) if run else None
    return topics


def get_topic(topic_id):
    with connect() as db:
        row = db.execute('SELECT * FROM bw_topics WHERE id=?', (topic_id,)).fetchone()
    return topic_row(row) if row else None


def save_topic(body, topic_id=None):
    stamp = now()
    with connect() as db:
        if topic_id is None:
            cur = db.execute('INSERT INTO bw_topics(body,created_at,updated_at) VALUES(?,?,?)', (json.dumps(body), stamp, stamp))
            topic_id = cur.lastrowid
        else:
            db.execute('UPDATE bw_topics SET body=?, revision=revision+1, updated_at=? WHERE id=?', (json.dumps(body), stamp, topic_id))
            db.execute("UPDATE bw_matches SET state='pending', analysis=NULL, evaluation_key=NULL, error=NULL WHERE topic_id=?", (topic_id,))
    return get_topic(topic_id)


def delete_topic(topic_id):
    with connect() as db:
        db.execute('DELETE FROM bw_topics WHERE id=?', (topic_id,))


def save_listing(topic_id, body):
    content_hash, stamp = digest(body), now()
    with connect() as db:
        existing = db.execute('SELECT source FROM bw_listings WHERE url=?', (body['listing_url'],)).fetchone()
        if existing and existing['source'] != body['source']:
            raise ValueError('URL già registrato da una fonte diversa; conserva la provenienza originale.')
        db.execute('''INSERT INTO bw_listings(url,source,body,content_hash,first_seen,last_seen)
            VALUES(?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET source=excluded.source,body=excluded.body,
            content_hash=excluded.content_hash,last_seen=excluded.last_seen''',
            (body['listing_url'], body['source'], json.dumps(body), content_hash, stamp, stamp))
        listing_id = db.execute('SELECT id FROM bw_listings WHERE url=?', (body['listing_url'],)).fetchone()[0]
        db.execute('INSERT OR IGNORE INTO bw_snapshots(listing_id,body,content_hash,captured_at) VALUES(?,?,?,?)',
                   (listing_id, json.dumps(body), content_hash, stamp))
        db.execute('''INSERT INTO bw_matches(topic_id,listing_id,first_seen,last_seen) VALUES(?,?,?,?)
            ON CONFLICT(topic_id,listing_id) DO UPDATE SET last_seen=excluded.last_seen''', (topic_id, listing_id, stamp, stamp))
        # Any topic referencing changed source data must be evaluated again.
        for match in db.execute('SELECT topic_id,evaluation_key FROM bw_matches WHERE listing_id=?', (listing_id,)).fetchall():
            if match['evaluation_key'] and not match['evaluation_key'].startswith(content_hash+':'):
                db.execute("UPDATE bw_matches SET state='pending', analysis=NULL, evaluation_key=NULL WHERE topic_id=? AND listing_id=?", (match['topic_id'], listing_id))
    return listing_id


def matches(topic_id):
    with connect() as db:
        rows = db.execute('''SELECT l.*,m.state,m.analysis,m.error,m.first_seen AS topic_first_seen,
            m.last_seen AS topic_last_seen,m.evaluated_at,m.evaluation_key,f.verdict
            FROM bw_matches m JOIN bw_listings l ON l.id=m.listing_id
            LEFT JOIN bw_feedback f ON f.topic_id=m.topic_id AND f.listing_id=m.listing_id
            WHERE m.topic_id=? ORDER BY m.first_seen DESC''', (topic_id,)).fetchall()
    return [{**json.loads(r['body']), 'id':r['id'], 'content_hash':r['content_hash'], 'state':r['state'],
             'analysis':json.loads(r['analysis']) if r['analysis'] else None, 'error':r['error'],
             'first_seen':r['topic_first_seen'], 'last_seen':r['topic_last_seen'],
             'evaluated_at':r['evaluated_at'], 'evaluation_key':r['evaluation_key'], 'verdict':r['verdict']} for r in rows]


def save_evaluation(topic_id, listing_id, state, analysis=None, key=None, error=None):
    with connect() as db:
        if key:
            current = db.execute('SELECT content_hash FROM bw_listings WHERE id=?', (listing_id,)).fetchone()
            if not current or not key.startswith(current['content_hash']+':'):
                # Another topic may have refreshed the same listing during inference.
                db.execute("UPDATE bw_matches SET state='pending',analysis=NULL,evaluation_key=NULL,error=NULL WHERE topic_id=? AND listing_id=?", (topic_id,listing_id))
                return False
        db.execute('''UPDATE bw_matches SET state=?,analysis=?,evaluation_key=?,error=?,evaluated_at=?
            WHERE topic_id=? AND listing_id=?''', (state, json.dumps(analysis) if analysis else None, key, error, now(), topic_id, listing_id))
    return True


def start_run(topic_id):
    with connect() as db:
        try:
            cur = db.execute("INSERT INTO bw_runs(topic_id,state,started_at) VALUES(?,'running',?)", (topic_id, now()))
        except sqlite3.IntegrityError:
            return None
    return cur.lastrowid


def finish_run(run_id, state, report):
    with connect() as db:
        db.execute('UPDATE bw_runs SET state=?,finished_at=?,report=? WHERE id=?', (state, now(), json.dumps(report), run_id))


def run_row(row):
    return {**dict(row), 'report':json.loads(row['report'])}


def get_run(run_id):
    with connect() as db:
        row = db.execute('SELECT * FROM bw_runs WHERE id=?', (run_id,)).fetchone()
    return run_row(row) if row else None


def runs(topic_id):
    with connect() as db:
        return [run_row(r) for r in db.execute('SELECT * FROM bw_runs WHERE topic_id=? ORDER BY id DESC LIMIT 20', (topic_id,))]


def set_feedback(topic_id, listing_id, verdict):
    with connect() as db:
        if not db.execute('SELECT 1 FROM bw_matches WHERE topic_id=? AND listing_id=?', (topic_id,listing_id)).fetchone():
            raise ValueError('Annuncio non appartenente al topic')
        if verdict is None:
            db.execute('DELETE FROM bw_feedback WHERE topic_id=? AND listing_id=?', (topic_id,listing_id))
        else:
            db.execute('INSERT INTO bw_feedback VALUES(?,?,?) ON CONFLICT(topic_id,listing_id) DO UPDATE SET verdict=excluded.verdict', (topic_id,listing_id,verdict))


def history(listing_id):
    with connect() as db:
        return [{'captured_at':r['captured_at'], 'listing':json.loads(r['body'])} for r in db.execute('SELECT * FROM bw_snapshots WHERE listing_id=? ORDER BY captured_at', (listing_id,))]
