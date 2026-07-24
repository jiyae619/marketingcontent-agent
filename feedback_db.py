"""SQLite-backed feedback log for marketing content generation.

Tracks every generation and which versions the user copied (= approved).
Copied content is the high-signal training data for the learning loop —
it's the user's voice, validated by their own action.

The DB file lives at testing/results/feedback.db and is gitignored.
"""

import hashlib
import json
import os
import sqlite3
import sys
import time
from contextlib import contextmanager
from typing import Dict, List, Optional

DB_PATH = os.environ.get("FEEDBACK_DB_PATH", "testing/results/feedback.db")


def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


SCHEMA = """
CREATE TABLE IF NOT EXISTS generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    original_input TEXT NOT NULL,
    generated_content TEXT NOT NULL,
    link_url TEXT,
    has_image INTEGER DEFAULT 0,
    eval_score REAL,
    eval_detail TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS copies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generation_id INTEGER REFERENCES generations(id) ON DELETE SET NULL,
    platform TEXT NOT NULL,
    final_content TEXT NOT NULL,
    copied_at REAL NOT NULL
);

-- generation_cache: avoids re-hitting Gemini for identical inputs.
-- cache_key = sha256(platform + input + link_url + has_image + voice_version).
-- Invalidated automatically when voice_version bumps (new copy logged).
CREATE TABLE IF NOT EXISTS generation_cache (
    cache_key  TEXT PRIMARY KEY,
    platform   TEXT NOT NULL,
    content    TEXT NOT NULL,
    eval_score REAL,
    created_at REAL NOT NULL
);

-- voice_versions: tracks how many copies exist per platform.
-- Used as part of the cache key so cache auto-invalidates when voice changes.
CREATE TABLE IF NOT EXISTS voice_versions (
    platform TEXT PRIMARY KEY,
    version  INTEGER NOT NULL DEFAULT 0
);

-- voice_profiles: synthesized style description (Phase D).
CREATE TABLE IF NOT EXISTS voice_profiles (
    platform      TEXT PRIMARY KEY,
    style_text    TEXT NOT NULL,
    based_on      INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL
);

-- schema_meta: key/value markers for one-time migrations and backfills.
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gen_platform_created
    ON generations(platform, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_copy_platform_copied
    ON copies(platform, copied_at DESC);
"""


@contextmanager
def _connect():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist, then run additive migrations.
    Safe to call repeatedly."""
    with _connect() as conn:
        conn.executescript(SCHEMA)
    _migrate()


# Columns added to the existing `generations` table after its original shape
# shipped. CREATE TABLE IF NOT EXISTS cannot add these to a table that already
# exists, so they are applied idempotently here.
_GENERATION_COLUMNS = (
    ("model", "TEXT"),            # which provider/model produced this row
    ("prompt_version", "TEXT"),  # hash of the channel template (pre voice injection)
    ("voice_version", "INTEGER"),# voice counter at generation time
    ("cache_key", "TEXT"),       # dedup key; the row IS the cache entry (see server.py)
)


def _migrate() -> None:
    """Idempotent additive schema migrations. Safe on every startup.

    Adds new columns to `generations` (ALTER TABLE ADD COLUMN can't live in the
    CREATE TABLE IF NOT EXISTS schema for an already-created table) and the unique
    index that makes `cache_key` a lookup key. A busy_timeout serializes concurrent
    startups, and a duplicate-column error is tolerated in case two processes race.
    """
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        existing = {row[1] for row in conn.execute("PRAGMA table_info(generations)")}
        for col, decl in _GENERATION_COLUMNS:
            if col not in existing:
                try:
                    conn.execute(f"ALTER TABLE generations ADD COLUMN {col} {decl}")
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        raise
        # NULLs are distinct in a SQLite unique index, so un-cached rows
        # (every /api/compare row, legacy rows) coexist with NULL cache_key.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_gen_cache_key ON generations(cache_key)"
        )
        conn.commit()
    finally:
        conn.close()


def log_generation(*, platform: str, original_input: str, generated_content: str,
                   link_url: str = "", has_image: bool = False,
                   eval_score: Optional[float] = None,
                   eval_detail: str = "",
                   model: Optional[str] = None,
                   prompt_version: Optional[str] = None,
                   voice_version: Optional[int] = None,
                   cache_key: Optional[str] = None) -> int:
    """Record a generation. Returns the row id (use as generation_id for copies).

    Provenance (model, prompt_version, voice_version) attributes the row; cache_key
    makes the row double as its own cache entry (see generation_by_cache_key).
    """
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO generations
                (platform, original_input, generated_content,
                 link_url, has_image, eval_score, eval_detail, created_at,
                 model, prompt_version, voice_version, cache_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (platform, original_input, generated_content,
             link_url, 1 if has_image else 0,
             eval_score, eval_detail, time.time(),
             model, prompt_version, voice_version, cache_key),
        )
        return cur.lastrowid


def log_copy(*, platform: str, final_content: str,
             generation_id: Optional[int] = None) -> int:
    """Record that the user copied this content (approval signal).
    Bumps voice_version for the platform, which invalidates the cache.
    """
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO copies (generation_id, platform, final_content, copied_at)
            VALUES (?, ?, ?, ?)
            """,
            (generation_id, platform, final_content, time.time()),
        )
        copy_id = cur.lastrowid
        # Bump voice version → all cached generations for this platform are now stale
        conn.execute(
            """
            INSERT INTO voice_versions (platform, version) VALUES (?, 1)
            ON CONFLICT(platform) DO UPDATE SET version = version + 1
            """,
            (platform,),
        )
        return copy_id


def voice_version(platform: str) -> int:
    """Current voice version for a platform (0 = no copies yet)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT version FROM voice_versions WHERE platform = ?", (platform,)
        ).fetchone()
        return row["version"] if row else 0


def make_cache_key(platform: str, user_input: str, link_url: str,
                   has_image: bool, voice_ver: int) -> str:
    """Deterministic hash used as the cache lookup key."""
    raw = json.dumps([platform, user_input, link_url, int(has_image), voice_ver],
                     ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_get(key: str) -> Optional[Dict]:
    """Return cached generation or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT content, eval_score FROM generation_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
        return dict(row) if row else None


def cache_set(key: str, platform: str, content: str,
              eval_score: Optional[float] = None) -> None:
    """Store a generation in cache."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO generation_cache (cache_key, platform, content, eval_score, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                content = excluded.content,
                eval_score = excluded.eval_score,
                created_at = excluded.created_at
            """,
            (key, platform, content, eval_score, time.time()),
        )


def copy_count(platform: str) -> int:
    """Total copies ever logged for a platform."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM copies WHERE platform = ?", (platform,)
        ).fetchone()
        return row[0] if row else 0


def get_voice_profile(platform: str) -> Optional[str]:
    """Return synthesized style description if it exists and is fresh enough."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT style_text, based_on FROM voice_profiles WHERE platform = ?",
            (platform,),
        ).fetchone()
        if not row:
            return None
        # Re-synthesize when 3+ new copies arrived since last synthesis
        current = copy_count(platform)
        if current - row["based_on"] >= 3:
            return None
        return row["style_text"]


def save_voice_profile(platform: str, style_text: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO voice_profiles (platform, style_text, based_on, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(platform) DO UPDATE SET
                style_text = excluded.style_text,
                based_on   = excluded.based_on,
                created_at = excluded.created_at
            """,
            (platform, style_text, copy_count(platform), time.time()),
        )


def recent_copies(platform: str, limit: int = 3) -> List[Dict]:
    """Most recent copies for a platform — drives the learning loop."""
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT id, generation_id, platform, final_content, copied_at
            FROM copies
            WHERE platform = ?
            ORDER BY copied_at DESC
            LIMIT ?
            """,
            (platform, limit),
        )
        return [dict(r) for r in cur.fetchall()]


def stats_by_platform() -> List[Dict]:
    """Light dashboard query: gen count, copy count, avg eval per platform."""
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT
                g.platform AS platform,
                COUNT(g.id) AS generations,
                COALESCE(AVG(g.eval_score), 0) AS avg_eval,
                (SELECT COUNT(*) FROM copies c WHERE c.platform = g.platform) AS copies
            FROM generations g
            GROUP BY g.platform
            ORDER BY g.platform
            """
        )
        return [dict(r) for r in cur.fetchall()]


if __name__ == "__main__":
    init_db()
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        for row in stats_by_platform():
            print(
                f"{row['platform']:10} gens={row['generations']:4} "
                f"copies={row['copies']:4} avg_eval={row['avg_eval']:.1f}"
            )
    else:
        print(f"feedback DB initialized at {DB_PATH}")
