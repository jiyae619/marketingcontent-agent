#!/usr/bin/env python3
"""Tests for scripts/schema_gen.py — the enum, and the character caps.

Each test names the defect it guards. No live model call: assemble() and
classify_event_type() are pure functions of (facts, prose) / (raw string).
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "testing/core"))
from schema_gen import assemble, classify_event_type, EVENT_TYPES  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    FAILED.append(f"{name}: {detail}") if not cond else None
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if not cond else ""))


BASE_FACTS = {"event_type": "seminar", "person": "박운영", "date": "Oct 2, 2026",
              "time": "6 PM PST", "location": "PKNIC HQ", "price": None,
              "link": None, "topics": ["Networking"], "map_url": None}


def main():
    # --- event type enum, trimmed to 3 -------------------------------------
    check("exactly 3 event types remain",
          set(EVENT_TYPES) == {"seminar", "webinar", "conference"}, set(EVENT_TYPES))
    # Old categories fold onto the closest of the three rather than going null —
    # a demo brief written before the trim should not silently lose its label.
    for old_term, want in [("coaching session", "seminar"), ("workshop", "seminar"),
                           ("info session", "seminar"), ("webinar", "webinar"),
                           ("meetup", "conference"), ("networking", "conference")]:
        got = classify_event_type(old_term)
        check(f"'{old_term}' folds onto '{want}'", got == want, got)
    check("an unmatched term is None, not guessed",
          classify_event_type("underwater basket weaving") is None)

    # --- reader-facing layout ---------------------------------------------
    # Each check is something a person scrolling that channel would notice.
    FULL = {**BASE_FACTS, "price": "Free", "link": "https://pknic.org/e/1",
            "map_url": "https://maps.example/pknic",
            "topics": ["Resume review", "Interview strategy", "Networking"]}
    PROSE = {"hook": "Join us for a practical career seminar.",
             "body": ["Bring your resume and leave with a sharper one.",
                      "Real interview questions, answered live."],
             "cta": "Save your seat today.", "hashtags": ["career", "seminar", "jobs"]}

    for platform in ("linkedin", "circle", "kakaotalk", "whatsapp", "instagram"):
        t = assemble(platform, FULL, PROSE)
        # Topics were "Topics: a / Topics: b / Topics: c" — one heading now.
        check(f"{platform}: topics grouped under one heading",
              t.count("Networking") == 1 and "Topics:" not in t
              and ("What we'll cover:" in t), t)
        # A reader asks "when is it" — date and time belong on one line.
        when_lines = [l for l in t.split("\n") if "Oct 2, 2026" in l]
        check(f"{platform}: date and time share one line",
              len(when_lines) == 1 and "6 PM PST" in when_lines[0], when_lines)
        # Blank lines between blocks are what makes a phone post scannable.
        check(f"{platform}: blocks separated by blank lines", "\n\n" in t, t)

    for platform in ("kakaotalk", "whatsapp"):
        t = assemble(platform, FULL, PROSE)
        # The old chat layout was ONE "Event: … · Date: … · Location: …" line.
        check(f"{platform}: each fact on its own line, not one '·' run-on",
              not any(l.count(":") > 2 for l in t.split("\n") if "http" not in l), t)

    t = assemble("kakaotalk", FULL, PROSE)
    check("kakaotalk uses ▶ markers (Korean notice convention)",
          "▶ When: Oct 2, 2026" in t, t)

    t = assemble("instagram", FULL, PROSE)
    # Caption URLs are dead text on Instagram.
    check("instagram: no raw URLs, 'link in bio' instead",
          "http" not in t and "Link in bio" in t, t)
    check("instagram: logistics lead with emoji, price folded onto the date line",
          "🗓 Oct 2, 2026 · 6 PM PST · Free" in t and "📍 PKNIC HQ" in t, t)

    t = assemble("linkedin", FULL, PROSE)
    check("linkedin: register and map links sit under the cta",
          "Save your seat today.\nRegister: https://pknic.org/e/1\nMap: https://maps.example/pknic" in t, t)

    # --- x: built by priority under 280, never sliced mid-word --------------
    t = assemble("x", FULL, PROSE)
    check("x: fits 280", len(t) <= 280, len(t))
    check("x: shows when and where", "🗓 Oct 2, 2026" in t and "📍 PKNIC HQ" in t, t)
    check("x: carries the link with the ask", "Save your seat today. https://pknic.org/e/1" in t, t)
    long_hook = {**PROSE, "hook": ("An unusually long opening line that keeps going " * 8).strip()}
    t = assemble("x", FULL, long_hook)
    check("x: an over-long draft is trimmed at a word boundary, not 'this val'",
          len(t) <= 280 and "…" in t and "🗓" in t, t)

    # --- prose hygiene ------------------------------------------------------
    dup = {**PROSE, "body": ["Bring your resume.", "Save your seat today and learn more."]}
    t = assemble("linkedin", FULL, dup)
    check("a body paragraph repeating the cta is dropped",
          t.count("Save your seat today") == 1, t)
    debris = {**PROSE, "body": ["clickHere", "A real paragraph here."]}
    check("a single-token body paragraph is dropped",
          "clickHere" not in assemble("linkedin", FULL, debris))

    # --- the 836-char whatsapp regression ------------------------------------
    # "sentences: 4" bounds a COUNT; a run-on sentence sails past it. Simulated
    # without a model call by handing assemble() an oversized body directly.
    runaway = ("This is a very long run-on sentence that just keeps going " * 12).strip()
    for platform in ("whatsapp", "kakaotalk"):
        t = assemble(platform, FULL, {**PROSE, "body": [runaway]})
        check(f"{platform}: a runaway body is cut back (was 836 chars live)",
              runaway not in t and len(t) < 560, f"{len(t)} chars")
        check(f"{platform}: logistics and the ask survive the cut",
              "Where: PKNIC HQ" in t and "Save your seat today." in t, t)

    # Grounded facts are never sacrificed to fit, even when they alone exceed
    # the budget — correctness over cosmetic compliance.
    huge = {**FULL, "location": "A Really Long Venue Name That Goes On For A While, Building 4"}
    t = assemble("kakaotalk", huge, PROSE)
    check("facts are never truncated to fit a length budget", "Building 4" in t, t)

    # --- restyle guard vs the enum ------------------------------------------
    # After the 9->3 trim the displayed label wasn't in the grounded string, so
    # every channel flagged the event's OWN name as a restyle.
    from schema_gen import facts_from_fields
    _, grounded, _ = facts_from_fields(
        {"ko": True, "event_type": "세미나", "date": "2026-10-15",
         "location": "Seattle University"}, True)
    from evaluators import strip_ungrounded
    check("the event's own label is not flagged as a restyle",
          strip_ungrounded("이번 세미나에 참여하세요", grounded)[1] == [])

    print(f"\n{'FAILED: ' + '; '.join(FAILED) if FAILED else 'all passed'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
