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
import statistics
import sys
import time
from contextlib import contextmanager
from typing import Dict, List, Optional

# Provisional inactivity gap that bounds a "session". Deliberately NOT tuned from
# current timestamps (they are dev/test noise, not real work sessions) — revisit
# once real usage accrues.
SESSION_GAP_SECONDS = 30 * 60

DB_PATH = os.environ.get("FEEDBACK_DB_PATH", "testing/results/feedback.db")

# Shared flag taxonomy — ONE source of truth for human flags now and the LLM
# judge's scoring criteria later. Two families: grounding (fix = better facts /
# retrieval) and voice (fix = the learning loop). Extend by adding entries; new
# categories need no migration since they are validated in code, not schema.
FLAG_TAXONOMY = {
    "hallucination":  "grounding",   # fabricated facts about the speaker/event
    "irrelevant":     "grounding",   # generic / off-brief; misses what matters
    "ai_slop":        "voice",       # robotic, generic AI tone; needs humanizing
    "kr_en_register": "voice",       # right facts, wrong Korean/English register
}

VALID_VERDICTS = ("approve", "edit", "reject")


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

-- voice_profiles: legacy single-row-per-platform table (superseded by
-- voice_profile_versions; retained, no longer read or written).
CREATE TABLE IF NOT EXISTS voice_profiles (
    platform      TEXT PRIMARY KEY,
    style_text    TEXT NOT NULL,
    based_on      INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL
);

-- voice_profile_versions: append-only synthesized style history. The latest
-- version per platform is the active one; prior versions stay inspectable.
CREATE TABLE IF NOT EXISTS voice_profile_versions (
    platform    TEXT NOT NULL,
    version     INTEGER NOT NULL,
    style_text  TEXT NOT NULL,
    based_on    INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL,
    PRIMARY KEY (platform, version)
);

-- schema_meta: key/value markers for one-time migrations and backfills.
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- feedback_events: the unified verdict stream (approve/edit/reject), canonical
-- source superseding `copies`. Each event links to its generation and may carry
-- one flag (category + family). Edits keep both original and final text.
CREATE TABLE IF NOT EXISTS feedback_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    generation_id    INTEGER REFERENCES generations(id) ON DELETE SET NULL,
    platform         TEXT NOT NULL,
    verdict          TEXT NOT NULL,   -- approve | edit | reject
    flag_category    TEXT,            -- nullable; must be in FLAG_TAXONOMY
    flag_family      TEXT,            -- nullable; derived from the category
    original_content TEXT,            -- generation text at verdict time (nullable)
    final_content    TEXT,            -- human-final text (nullable for reject)
    created_at       REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fb_platform_created
    ON feedback_events(platform, created_at DESC);

-- judge_results: machine grades from the LLM-as-judge pipeline, linked to the
-- generation. Distinct from feedback_events (those are HUMAN verdicts); these are
-- MODEL verdicts. Per-category scores stored as JSON.
CREATE TABLE IF NOT EXISTS judge_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    generation_id INTEGER REFERENCES generations(id) ON DELETE SET NULL,
    platform      TEXT NOT NULL,
    judge_model   TEXT NOT NULL,
    overall       INTEGER,
    safety_pass   INTEGER,        -- 0 / 1 / NULL
    scores        TEXT,           -- JSON: {category: {score, reason}}
    created_at    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_judge_gen ON judge_results(generation_id);

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
        _backfill_copies_to_feedback(conn)
        conn.commit()
    finally:
        conn.close()


def _backfill_copies_to_feedback(conn) -> None:
    """One-time migration of legacy `copies` (approvals) into feedback_events.

    Marker-guarded via schema_meta so it runs once; the marker is written only on
    completion, so an interrupted backfill re-runs. When a copy's generation_id
    doesn't resolve to a live generation (true of existing rows), both
    generation_id and original_content are stored NULL — the FK stays honest.
    """
    done = conn.execute(
        "SELECT value FROM schema_meta WHERE key = 'copies_backfilled'"
    ).fetchone()
    if done:
        return
    # Mirror is_genuine_content in SQL so legacy error/placeholder strings (the
    # old copy path had no validation) don't enter voice training via history.
    conn.execute(
        """
        INSERT INTO feedback_events
            (generation_id, platform, verdict, flag_category, flag_family,
             original_content, final_content, created_at)
        SELECT
            g.id, c.platform, 'approve', NULL, NULL,
            g.generated_content, c.final_content, c.copied_at
        FROM copies c
        LEFT JOIN generations g ON g.id = c.generation_id
        WHERE TRIM(c.final_content) != ''
          AND c.final_content NOT LIKE 'Error:%'
          AND LOWER(TRIM(c.final_content)) != 'generating...'
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('copies_backfilled', ?)",
        (str(time.time()),),
    )


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


def get_generation(generation_id: int) -> Optional[Dict]:
    """Fetch a generation row by id, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM generations WHERE id = ?", (generation_id,)
        ).fetchone()
        return dict(row) if row else None


def log_judge_result(*, generation_id: Optional[int], platform: str, judge_model: str,
                     overall: Optional[int] = None, safety_pass: Optional[bool] = None,
                     scores: Optional[Dict] = None) -> int:
    """Persist one machine judge verdict, linked to its generation. Returns row id.

    Distinct from log_feedback (human verdicts) — this records what the LLM judge
    graded. `scores` is the per-category dict; stored as JSON.
    """
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO judge_results
                (generation_id, platform, judge_model, overall, safety_pass, scores, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (generation_id, platform, judge_model, overall,
             None if safety_pass is None else (1 if safety_pass else 0),
             json.dumps(scores) if scores is not None else None,
             time.time()),
        )
        return cur.lastrowid


def is_genuine_content(text: Optional[str]) -> bool:
    """False for content that must never enter voice training: empty/whitespace,
    error strings, or the 'Generating...' placeholder.

    Sentinel-level only — this does NOT catch model refusals or truncated stubs
    (a broader minimum-substance heuristic is a later hardening step).
    """
    if not text or not text.strip():
        return False
    t = text.strip()
    if t.startswith("Error:"):
        return False
    if t.lower() == "generating...":
        return False
    return True


def _normalize_content(text: Optional[str]) -> str:
    """Normalize trailing whitespace / line-endings so a newline-only artifact
    isn't misread as a human edit."""
    if text is None:
        return ""
    lines = text.replace("\r\n", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def classify_verdict(original: Optional[str], final: str) -> str:
    """approve when `final` matches the generation (normalized), else edit.
    approve when there is no original to compare against."""
    if original is None:
        return "approve"
    return "approve" if _normalize_content(original) == _normalize_content(final) else "edit"


def log_feedback(*, generation_id: Optional[int], platform: str, verdict: str,
                 original_content: Optional[str] = None,
                 final_content: Optional[str] = None,
                 flag_category: Optional[str] = None) -> int:
    """Record one human verdict on a generation. Returns the event id.

    approve/edit bump voice_version (they yield content the voice loop learns
    from); reject does not. A flag_category must be in FLAG_TAXONOMY and its
    family is derived. Raises ValueError on an unknown verdict/flag, or on
    non-genuine final_content.
    """
    if verdict not in VALID_VERDICTS:
        raise ValueError(f"unknown verdict: {verdict!r}")
    flag_family = None
    if flag_category is not None:
        if flag_category not in FLAG_TAXONOMY:
            raise ValueError(f"unknown flag category: {flag_category!r}")
        flag_family = FLAG_TAXONOMY[flag_category]
    if final_content is not None and not is_genuine_content(final_content):
        raise ValueError("final_content is not genuine content")
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO feedback_events
                (generation_id, platform, verdict, flag_category, flag_family,
                 original_content, final_content, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (generation_id, platform, verdict, flag_category, flag_family,
             original_content, final_content, time.time()),
        )
        event_id = cur.lastrowid
        if verdict in ("approve", "edit"):
            # Bump the voice counter → cached generations for this platform
            # become stale (their cache_key includes voice_version).
            conn.execute(
                """
                INSERT INTO voice_versions (platform, version) VALUES (?, 1)
                ON CONFLICT(platform) DO UPDATE SET version = version + 1
                """,
                (platform,),
            )
        return event_id


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


def generation_by_cache_key(cache_key: str) -> Optional[Dict]:
    """Return the generation row that IS this cache entry, or None.

    The cache is not a separate content copy: a generation is logged with its
    cache_key (see log_generation), so a hit returns a real generation — content,
    id, and provenance — and an approval linked to cached content can never be
    orphaned. Supersedes the old cache_get/cache_set + generation_cache table.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM generations WHERE cache_key = ?", (cache_key,)
        ).fetchone()
        return dict(row) if row else None


def copy_count(platform: str) -> int:
    """Count of approvals+edits for a platform.

    Named `copy_count` for continuity; drives the voice-synthesis staleness rule
    and trigger. Reads feedback_events (the canonical stream) — NOT the retired
    `copies` table — so it keeps growing after writes to `copies` stopped. This
    repoint is load-bearing: leaving it on `copies` would freeze the counter and
    silently stall voice synthesis.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM feedback_events "
            "WHERE platform = ? AND verdict IN ('approve','edit')",
            (platform,),
        ).fetchone()
        return row[0] if row else 0


def get_voice_profile(platform: str) -> Optional[str]:
    """Return the active (latest) synthesized style if it exists and is fresh.

    Re-synthesize (return None) once 3+ new approvals/edits arrived since the
    active version was built — same staleness rule as before, now sourced from
    feedback_events via copy_count.
    """
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT style_text, based_on FROM voice_profile_versions
            WHERE platform = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (platform,),
        ).fetchone()
        if not row:
            return None
        current = copy_count(platform)
        if current - row["based_on"] >= 3:
            return None
        return row["style_text"]


def save_voice_profile(platform: str, style_text: str) -> None:
    """Append a new voice-profile version (never overwrites — prior versions stay
    inspectable). The latest version becomes the active one."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM voice_profile_versions "
            "WHERE platform = ?",
            (platform,),
        ).fetchone()
        next_version = row["v"] + 1
        conn.execute(
            """
            INSERT INTO voice_profile_versions
                (platform, version, style_text, based_on, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (platform, next_version, style_text, copy_count(platform), time.time()),
        )


def recent_copies(platform: str, limit: int = 3) -> List[Dict]:
    """Most recent approved/edited content for a platform — drives the learning loop.

    Reads approve+edit feedback_events (edits included: an edited-then-approved
    post is the strongest voice signal). `copied_at` aliases the event time so
    existing callers keep working.
    """
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT id, generation_id, platform, final_content, created_at AS copied_at
            FROM feedback_events
            WHERE platform = ? AND verdict IN ('approve','edit')
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (platform, limit),
        )
        return [dict(r) for r in cur.fetchall()]


def stats_by_platform() -> List[Dict]:
    """Light dashboard query: gen count, approval count, avg eval per platform."""
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT
                g.platform AS platform,
                COUNT(g.id) AS generations,
                COALESCE(AVG(g.eval_score), 0) AS avg_eval,
                (SELECT COUNT(*) FROM feedback_events f
                 WHERE f.platform = g.platform
                   AND f.verdict IN ('approve','edit')) AS copies
            FROM generations g
            GROUP BY g.platform
            ORDER BY g.platform
            """
        )
        return [dict(r) for r in cur.fetchall()]


def hands_on_time_stats() -> Dict:
    """Per-session hands-on time: first generation → session close.

    Buckets generation timestamps and closing-verdict timestamps (cross-platform,
    since one brief fans out to several channels) into sessions by an inactivity
    gap. A session closes on the last approve OR edit verdict — both mean the user
    accepted content and finished (edit = accepted-after-editing); reject does not
    close a session. A session with no close is incomplete and excluded from the
    median; a session whose close precedes its first generation is dropped.

    Returns {sessions, completed_sessions, median_seconds, durations_seconds}.
    """
    with _connect() as conn:
        events = [(r[0], "gen") for r in conn.execute(
            "SELECT created_at FROM generations WHERE created_at IS NOT NULL"
        )]
        events += [(r[0], "close") for r in conn.execute(
            "SELECT created_at FROM feedback_events WHERE verdict IN ('approve','edit')"
        )]

    events.sort(key=lambda e: e[0])
    if not events:
        return {"sessions": 0, "completed_sessions": 0,
                "median_seconds": None, "durations_seconds": []}

    sessions: List[List] = []
    current = [events[0]]
    for ev in events[1:]:
        if ev[0] - current[-1][0] > SESSION_GAP_SECONDS:
            sessions.append(current)
            current = [ev]
        else:
            current.append(ev)
    sessions.append(current)

    durations: List[float] = []
    for s in sessions:
        gen_times = [t for t, kind in s if kind == "gen"]
        close_times = [t for t, kind in s if kind == "close"]
        if not gen_times or not close_times:
            continue  # incomplete: no generation, or no approve/edit to close it
        dur = max(close_times) - min(gen_times)
        if dur < 0:
            continue  # close precedes first generation — drop
        durations.append(dur)

    return {
        "sessions": len(sessions),
        "completed_sessions": len(durations),
        "median_seconds": statistics.median(durations) if durations else None,
        "durations_seconds": durations,
    }


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
