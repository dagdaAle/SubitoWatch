"""Baseline: the BuyWatcher tables as created before Alembic (IF NOT EXISTS, safe on the live DB).

Revision ID: 0001
Revises:
"""
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
    CREATE TABLE IF NOT EXISTS bw_topics (
            id INTEGER PRIMARY KEY, body TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, legacy_channel_id INTEGER UNIQUE
        )
    ''')
    op.execute('''
    CREATE TABLE IF NOT EXISTS bw_listings (
            id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, source TEXT NOT NULL,
            body TEXT NOT NULL, content_hash TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
        )
    ''')
    op.execute('''
    CREATE TABLE IF NOT EXISTS bw_snapshots (
            id INTEGER PRIMARY KEY, listing_id INTEGER NOT NULL REFERENCES bw_listings(id),
            body TEXT NOT NULL, content_hash TEXT NOT NULL, captured_at TEXT NOT NULL,
            UNIQUE(listing_id, content_hash)
        )
    ''')
    op.execute('''
    CREATE TABLE IF NOT EXISTS bw_matches (
            topic_id INTEGER NOT NULL REFERENCES bw_topics(id) ON DELETE CASCADE,
            listing_id INTEGER NOT NULL REFERENCES bw_listings(id),
            state TEXT NOT NULL DEFAULT 'pending', analysis TEXT, evaluation_key TEXT,
            error TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, evaluated_at TEXT,
            PRIMARY KEY(topic_id, listing_id)
        )
    ''')
    op.execute('''
    CREATE TABLE IF NOT EXISTS bw_runs (
            id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL REFERENCES bw_topics(id) ON DELETE CASCADE,
            state TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, report TEXT NOT NULL DEFAULT '{}'
        )
    ''')
    op.execute('''
    CREATE UNIQUE INDEX IF NOT EXISTS bw_one_run ON bw_runs(topic_id) WHERE state='running'
    ''')
    op.execute('''
    CREATE TABLE IF NOT EXISTS bw_feedback (
            topic_id INTEGER NOT NULL REFERENCES bw_topics(id) ON DELETE CASCADE,
            listing_id INTEGER NOT NULL REFERENCES bw_listings(id), verdict TEXT NOT NULL,
            PRIMARY KEY(topic_id, listing_id)
        )
    ''')
    op.execute('''
    CREATE TABLE IF NOT EXISTS bw_profile (
            id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
        )
    ''')


def downgrade():
    raise NotImplementedError('Baseline: restore a backup instead.')
