#!/usr/bin/env python3
"""Tests for the typed brief form.

Each test names the defect it prevents. The form exists because parse_brief()
got three of six fields wrong on the standing sample brief, so a test that only
checked "validate returns a dict" would not be able to fail when that regressed.
"""
import datetime as dt, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import brief_fields as bf  # noqa: E402

OK = {"event_type": "coaching session", "person": "박운영", "date": "2026-09-14",
      "time": "15:00", "timezone": "PST", "location": "Seattle University",
      "topics": ["커리어 레쥬메"]}
FAILED = []


def check(name, cond, detail=""):
    FAILED.append(f"{name}: {detail}") if not cond else None
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if not cond else ""))


def main():
    f, e = bf.validate(OK)
    # parse_brief() left date null and put "sep 14th, 2026, 3PM PST" — a date AND
    # a time — into `time`. A post with no date is not shippable.
    check("date and time are separate fields",
          f["date"] == "Sep 14, 2026" and f["time"] == "3 PM PST", f)
    check("valid payload has no errors", e == {}, e)

    ko, _ = bf.validate(OK, ko=True)
    # The model re-typed "sep 14th, 2026, 3PM PST" as "2026-09-14"/"15:00 PST",
    # neither a substring of the brief, so both were discarded as ungrounded.
    # Locale rendering belongs to code, which knows the locale.
    check("korean renders in korean",
          ko["date"] == "9월 14일, 2026" and ko["time"] == "오후 3시 PST", ko)

    # A weekday was the single most-invented value across the seven-model sweep.
    # No field produces one, so none can reach the output.
    check("no weekday is ever rendered",
          not any(d in f["date"] for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")),
          f["date"])
    # NOT a bare "일" — that is the day-of-month suffix in "14일". A Korean
    # weekday is "일요일" or a parenthesised "(일)".
    import re as _re
    check("no weekday in korean either",
          not _re.search(r"[월화수목금토일]요일|[（(][월화수목금토일][)）]", ko["date"]),
          ko["date"])

    # Errors are returned together, not raised on the first one, so a form can
    # show every problem at once instead of one per submit.
    _, errs = bf.validate({"event_type": "seminar", "date": "sep 14th 2026",
                           "time": "3PM", "location": "", "link": "pknic.org"})
    check("all field errors reported at once",
          set(errs) == {"date", "time", "location", "link"}, errs)

    # Every field validates individually here, yet the hour is ambiguous —
    # which is a grounding defect the per-field checks cannot see.
    _, errs = bf.validate({"event_type": "x", "date": "2026-09-14",
                           "time": "15:00", "location": "y"})
    check("time without a zone is rejected", errs.get("timezone"), errs)

    # A missing optional field must emit nothing. This is what "if a detail is
    # missing, OMIT it" looks like in code, and it is why "[Insert Price]" is
    # unrepresentable: no branch writes a placeholder.
    f2, e2 = bf.validate({"event_type": "x", "date": "2026-09-14", "location": "y"})
    check("absent optional fields are None, not placeholders",
          f2["price"] is None and f2["link"] is None and f2["person"] is None and e2 == {}, f2)

    # A required field missing must block generation rather than produce a post
    # with a hole in it.
    _, e3 = bf.validate({"event_type": "x"})
    check("required fields block", set(e3) == {"date", "location"}, e3)

    # Midnight is hour 0: a naive `hour - 12` / truthiness bug renders "오전 0시".
    mid, _ = bf.validate({**OK, "time": "00:30"}, ko=True)
    check("midnight renders as 12-hour, not 0", "0시" not in mid["time"], mid["time"])
    noon, _ = bf.validate({**OK, "time": "12:00"}, ko=True)
    check("noon is 오후 12시", noon["time"] == "오후 12시 PST", noon["time"])

    print(f"\n{'FAILED: ' + '; '.join(FAILED) if FAILED else 'all passed'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
