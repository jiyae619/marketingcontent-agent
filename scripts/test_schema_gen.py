#!/usr/bin/env python3
"""Tests for scripts/schema_gen.py — the enum, and the character caps.

Each test names the defect it guards. No live model call: assemble() and
classify_event_type() are pure functions of (facts, prose) / (raw string).
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

    # --- the 836-char whatsapp/kakaotalk regression -------------------------
    # A live generation shipped 836 chars: "sentences: N" in the prompt bounds
    # a COUNT, and a run-on single sentence sails past it. Simulated here
    # without a model call by handing assemble() an oversized body directly.
    runaway = ("This is a very long run-on sentence that just keeps going " * 12).strip()
    prose = {"hook": "Join us", "body": [runaway], "cta": "Sign up", "hashtags": []}

    for platform in ("whatsapp", "kakaotalk"):
        text = assemble(platform, BASE_FACTS, prose)
        check(f"{platform}: an 800+ char body is capped",
              len(text) <= 340, f"{len(text)} chars")
        check(f"{platform}: the facts line survives the cap intact",
              "Location: PKNIC HQ" in text and "Speaker: 박운영" in text, text)
        check(f"{platform}: the cta survives the cap intact",
              "Sign up" in text, text)

    # Grounded facts are never sacrificed to fit the cap, even when they alone
    # exceed it — correctness over cosmetic compliance, matching the guard's
    # existing rule for weekdays/placeholders elsewhere in this codebase.
    huge_facts = {**BASE_FACTS,
                 "location": "A Really Long Venue Name That Goes On For A While, Building 4",
                 "link": "https://example.com/very/long/path/to/the/event/page/here"}
    text = assemble("kakaotalk", huge_facts, {"hook": "hi", "body": ["short"],
                                              "cta": "go", "hashtags": []})
    check("facts are never truncated even when they alone exceed total_max",
          "Building 4" in text and "example.com" in text
          and text.rstrip().endswith("go"), text)

    # The exact live failure: empty body, everything front-loaded into hook+cta.
    # A body-only shrink left this UNCHANGED at 440 chars the first time this
    # backstop was written — cta has to be elastic too, or a long hook+cta pair
    # with nothing in body sails straight through.
    prose_empty_body = {
        "hook": "Join us for an inspiring seminar with LinkedIn pro, 박운영, on "
               "LinkedIn networking and personal branding.",
        "body": [],
        "cta": "Register now and be the first to learn how to master LinkedIn "
              "networking and personal branding from an expert in the field. "
              "Register here.",
        "hashtags": [],
    }
    text = assemble("whatsapp", {**BASE_FACTS,
                                 "map_url": "https://maps.example/pknic"},
                    prose_empty_body)
    check("empty-body overflow is still capped (cta absorbs the cut)",
          len(text) <= 340, f"{len(text)} chars")
    check("hook survives that cut intact",
          "Join us for an inspiring seminar" in text, text)
    check("facts survive that cut intact",
          "Speaker: 박운영" in text and "Topics: Networking" in text, text)

    # --- normal-length content is untouched ---------------------------------
    normal = {"hook": "Join us for a great session.",
              "body": ["Learn practical networking tips."],
              "cta": "Sign up today.", "hashtags": []}
    text = assemble("whatsapp", BASE_FACTS, normal)
    check("normal-length whatsapp content is not mangled",
          "Join us for a great session." in text
          and "Learn practical networking tips." in text, text)

    print(f"\n{'FAILED: ' + '; '.join(FAILED) if FAILED else 'all passed'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
