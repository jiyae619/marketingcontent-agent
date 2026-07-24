#!/usr/bin/env python3
"""Write-path validation fixture for the feedback data layer (U1-U5).

Dependency-free (stdlib assert). Exercises every verdict type, the flag taxonomy,
the cache-as-generation lookup, the copies->feedback_events backfill, the voice
loop counter repoint + versioning, and per-session hands-on time — the acceptance
gate before any real use, since no UI writes to this model in this phase.

SAFETY: feedback_db.DB_PATH binds FEEDBACK_DB_PATH at import time, so this script
binds a throwaway temp path BEFORE importing feedback_db and refuses to run
against the real testing/results/feedback.db.

    Run:  python3 scripts/test_feedback_db.py
       or FEEDBACK_DB_PATH=/tmp/x.db python3 scripts/test_feedback_db.py
"""
import os
import sqlite3
import sys
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

DEFAULT_DB = os.path.join(_REPO_ROOT, "testing/results/feedback.db")

# Bind a temp DB before importing feedback_db (which reads the env var at import).
_env = os.environ.get("FEEDBACK_DB_PATH")
if not _env or os.path.abspath(_env) == os.path.abspath(DEFAULT_DB):
    os.environ["FEEDBACK_DB_PATH"] = os.path.join(
        tempfile.mkdtemp(prefix="fbtest_"), "test.db"
    )

import feedback_db as db  # noqa: E402

assert os.path.abspath(db.DB_PATH) != os.path.abspath(DEFAULT_DB), \
    "refusing to run against the real feedback.db"


def fresh_db():
    """Point feedback_db at a brand-new temp DB and initialize it."""
    db.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="fbtest_"), "test.db")
    db.init_db()


def _raw():
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


CHECKS = 0


def check(label, cond):
    global CHECKS
    CHECKS += 1
    assert cond, f"FAILED: {label}"
    print(f"  ok  {label}")


# ---------------------------------------------------------------------------
def test_u1_provenance_and_migration():
    print("U1 provenance + migration")
    fresh_db()
    db.init_db()  # idempotent second run must not error
    gid = db.log_generation(
        platform="linkedin", original_input="brief", generated_content="hi",
        model="gemini-2.5-flash", prompt_version="abc123", voice_version=0, cache_key="k1",
    )
    row = db.get_generation(gid)
    check("provenance persists", row["model"] == "gemini-2.5-flash"
          and row["prompt_version"] == "abc123" and row["voice_version"] == 0)
    # AE4: rows attributable to distinct models
    g2 = db.log_generation(platform="linkedin", original_input="b",
                           generated_content="x", model="gpt-4o-mini")
    check("AE4 model attribution", db.get_generation(g2)["model"] == "gpt-4o-mini")
    with _raw() as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(generations)")}
    check("migration added all provenance columns",
          {"model", "prompt_version", "voice_version", "cache_key"} <= cols)


def test_u2_cache_as_generation():
    print("U2 cache merged into generations")
    fresh_db()
    key = db.make_cache_key("linkedin", "brief text", "", False, 0)
    gid = db.log_generation(platform="linkedin", original_input="brief text",
                            generated_content="HELLO POST", cache_key=key)
    hit = db.generation_by_cache_key(key)
    check("AE1 cache hit returns the same generation",
          hit is not None and hit["id"] == gid and hit["generated_content"] == "HELLO POST")
    # NULL cache_key rows (compare-style) coexist under the unique index
    for m in ("gpt-4o-mini", "claude-haiku"):
        db.log_generation(platform="linkedin", original_input="b",
                          generated_content="x", model=m, cache_key=None)
    with _raw() as c:
        nulls = c.execute("SELECT COUNT(*) FROM generations WHERE cache_key IS NULL").fetchone()[0]
    check("NULL cache_key rows coexist", nulls == 2)
    # voice-bump invalidation: a new voice_version → new key → miss
    key2 = db.make_cache_key("linkedin", "brief text", "", False, 1)
    check("voice bump invalidates cache", db.generation_by_cache_key(key2) is None)
    # unique key enforced
    try:
        db.log_generation(platform="linkedin", original_input="dup",
                          generated_content="dup", cache_key=key)
        raise AssertionError("duplicate cache_key was allowed")
    except sqlite3.IntegrityError:
        check("unique cache_key enforced", True)


def test_u3_feedback_events():
    print("U3 feedback-event stream + taxonomy + validation")
    fresh_db()
    gid = db.log_generation(platform="linkedin", original_input="i",
                            generated_content="ORIGINAL TEXT")
    # AE3: edit + ai_slop flag stores both texts, derives voice family, linked
    eid = db.log_feedback(generation_id=gid, platform="linkedin", verdict="edit",
                          original_content="ORIGINAL TEXT", final_content="EDITED TEXT",
                          flag_category="ai_slop")
    with _raw() as c:
        ev = dict(c.execute("SELECT * FROM feedback_events WHERE id=?", (eid,)).fetchone())
    check("AE3 edit+flag: verdict/family/both texts/linked",
          ev["verdict"] == "edit" and ev["flag_family"] == "voice"
          and ev["original_content"] and ev["final_content"] and ev["generation_id"] == gid)
    # AE2: error string rejected
    try:
        db.log_feedback(generation_id=None, platform="linkedin", verdict="approve",
                        final_content="Error: quota exceeded")
        raise AssertionError("error string was accepted")
    except ValueError:
        check("AE2 error string rejected", True)
    # empty / placeholder rejected
    for bad in ("", "   ", "Generating..."):
        try:
            db.log_feedback(generation_id=None, platform="x", verdict="approve", final_content=bad)
            raise AssertionError(f"accepted bad content {bad!r}")
        except ValueError:
            pass
    check("empty/placeholder rejected", True)
    # unknown flag / unknown verdict raise
    for kwargs in ({"verdict": "reject", "flag_category": "foo"},
                   {"verdict": "sideways"}):
        try:
            db.log_feedback(generation_id=None, platform="x", **kwargs)
            raise AssertionError(f"accepted invalid {kwargs}")
        except ValueError:
            pass
    check("unknown flag/verdict rejected", True)
    # classification: normalized newline → approve; real change → edit; no original → approve
    check("classify newline-only → approve", db.classify_verdict("hello world", "hello world\n") == "approve")
    check("classify changed → edit", db.classify_verdict("hello world", "hello there") == "edit")
    check("classify no original → approve", db.classify_verdict(None, "anything") == "approve")
    # reject does NOT bump voice_version; approve does
    before = db.voice_version("circle")
    db.log_feedback(generation_id=None, platform="circle", verdict="reject",
                    flag_category="hallucination", final_content=None)
    mid = db.voice_version("circle")
    db.log_feedback(generation_id=None, platform="circle", verdict="approve", final_content="good")
    after = db.voice_version("circle")
    check("reject no bump, approve bumps", before == mid and after == mid + 1)


def test_u3_backfill_orphans():
    print("U3 backfill (real-shape orphans)")
    # seed a legacy DB whose copies' generation_ids DON'T resolve
    db.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="fbtest_"), "test.db")
    with _raw() as c:
        c.executescript(
            "CREATE TABLE generations (id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL,"
            " original_input TEXT NOT NULL, generated_content TEXT NOT NULL, link_url TEXT,"
            " has_image INTEGER DEFAULT 0, eval_score REAL, eval_detail TEXT, created_at REAL NOT NULL);"
            "CREATE TABLE copies (id INTEGER PRIMARY KEY AUTOINCREMENT, generation_id INTEGER,"
            " platform TEXT NOT NULL, final_content TEXT NOT NULL, copied_at REAL NOT NULL);"
        )
        c.execute("INSERT INTO copies (generation_id, platform, final_content, copied_at) VALUES (NULL,'linkedin','A',1.0)")
        c.execute("INSERT INTO copies (generation_id, platform, final_content, copied_at) VALUES (999,'x','B',2.0)")
        c.commit()
    db.init_db()  # migrate + backfill
    with _raw() as c:
        rows = [dict(r) for r in c.execute("SELECT verdict, generation_id, original_content FROM feedback_events ORDER BY id")]
    check("backfill: 2 approve events, orphan gen/original NULL",
          len(rows) == 2 and all(r["verdict"] == "approve" and r["generation_id"] is None
                                 and r["original_content"] is None for r in rows))
    db.init_db()  # idempotent
    with _raw() as c:
        n = c.execute("SELECT COUNT(*) FROM feedback_events").fetchone()[0]
    check("backfill marker: second run is a no-op", n == 2)


def test_u4_reader_repoint_and_versioning():
    print("U4 reader repoint + voice versioning")
    fresh_db()
    # regression guard: NO copies-table writes; copy_count must read feedback_events
    for i in range(2):
        db.log_feedback(generation_id=None, platform="linkedin", verdict="approve",
                        final_content=f"post {i}")
    check("copy_count reads feedback_events", db.copy_count("linkedin") == 2)
    db.save_voice_profile("linkedin", "Voice v1")
    check("get_voice_profile fresh returns active", db.get_voice_profile("linkedin") == "Voice v1")
    for i in range(3):
        db.log_feedback(generation_id=None, platform="linkedin", verdict="approve",
                        final_content=f"more {i}")
    check("staleness re-triggers synthesis (counter didn't freeze)",
          db.get_voice_profile("linkedin") is None)
    db.save_voice_profile("linkedin", "Voice v2")
    with _raw() as c:
        vs = [dict(r) for r in c.execute(
            "SELECT version, style_text FROM voice_profile_versions WHERE platform='linkedin' ORDER BY version")]
    check("append-only versioning (no destructive overwrite)",
          len(vs) == 2 and vs[0]["style_text"] == "Voice v1" and vs[1]["style_text"] == "Voice v2")
    db.log_feedback(generation_id=None, platform="linkedin", verdict="edit",
                    original_content="x", final_content="EDITED")
    rc = db.recent_copies("linkedin", limit=20)
    check("recent_copies includes edits", any(r["final_content"] == "EDITED" for r in rc))


def test_u5_hands_on_time():
    print("U5 per-session hands-on time")
    fresh_db()
    with _raw() as c:
        def gen(p, t):
            c.execute("INSERT INTO generations (platform, original_input, generated_content, created_at) VALUES (?,?,?,?)", (p, "i", "o", t))
        def approve(p, t):
            c.execute("INSERT INTO feedback_events (generation_id, platform, verdict, created_at) VALUES (NULL,?, 'approve', ?)", (p, t))
        B = 1_000_000.0
        for i, p in enumerate(["linkedin", "instagram", "x"]):
            gen(p, B + i * 0.3)
        for i, p in enumerate(["linkedin", "instagram", "x"]):
            approve(p, B + 300 + i * 0.4)       # session 1: ~300s
        gen("kakaotalk", B + 40 * 60)
        approve("kakaotalk", B + 40 * 60 + 120)  # session 2 (after gap): 120s
        gen("whatsapp", B + 3 * 3600)            # incomplete: no close
        # session 3 closed by an EDIT (not approve) — must still count
        def edit_close(p, t):
            c.execute("INSERT INTO feedback_events (generation_id, platform, verdict, created_at) VALUES (NULL,?, 'edit', ?)", (p, t))
        gen("linkedin", B + 6 * 3600)
        edit_close("linkedin", B + 6 * 3600 + 90)  # 90s, closed by edit
        c.commit()
    r = db.hands_on_time_stats()
    check("4 sessions, 3 completed (edit closes a session)",
          r["sessions"] == 4 and r["completed_sessions"] == 3)
    check("AE5 burst=one session ~300s, gap-split ~120s",
          abs(r["durations_seconds"][0] - 300) < 2 and abs(r["durations_seconds"][1] - 120) < 2)
    check("edit-closed session counted ~90s", abs(r["durations_seconds"][2] - 90) < 2)


def main():
    print(f"feedback_db write-path fixture — temp DB at {db.DB_PATH}\n")
    test_u1_provenance_and_migration()
    test_u2_cache_as_generation()
    test_u3_feedback_events()
    test_u3_backfill_orphans()
    test_u4_reader_repoint_and_versioning()
    test_u5_hands_on_time()
    print(f"\nALL {CHECKS} CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\n{e}")
        sys.exit(1)
