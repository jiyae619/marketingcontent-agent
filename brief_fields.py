"""Typed brief fields: the form that replaces parse_brief().

parse_brief() is a regex over free text, and on the standing sample brief it got
three of six fields wrong — person null with the name buried inside event_type,
date null, and "sep 14th, 2026, 3PM PST" (a date AND a time) sitting in `time`.
That is the deterministic layer of the fact/prose split, so a heuristic there
undermines everything built on top of it.

A form removes the guessing. Each field below has a type, so `date` is a date
rather than whatever a regex matched, and the locale rendering decision
("9월 14일" vs "Sep 14") moves into code that already knows the locale instead of
being a string the model may re-type. The lesson of the whole prototype applies
to the input side too: if code can answer, code answers.

Free text stays supported — parse_brief() is the fallback for a pasted brief —
but a parsed brief is a guess and a submitted form is not, and validate() says
which one produced each value.
"""
from __future__ import annotations

import datetime as _dt
import re

# Time zones we render; abbreviation is published verbatim, never converted.
TIMEZONES = ("PST", "PDT", "EST", "EDT", "KST", "UTC", "GMT", "CET", "JST")

# (name, type, required, EN label, KO label)
FIELDS = (
    ("event_type", "enum",  True,  "Event type", "행사 유형"),
    ("person",     "text",  False, "Speaker",    "연사"),
    ("date",       "date",  True,  "Date",       "날짜"),
    ("time",       "time",  False, "Time",       "시간"),
    ("timezone",   "tz",    False, "Time zone",  "시간대"),
    ("location",   "text",  True,  "Location",   "장소"),
    ("price",      "money", False, "Price",      "참가비"),
    ("link",       "url",   False, "Link",       "링크"),
    ("topics",     "list",  False, "Agenda",     "주제"),
)
REQUIRED = tuple(n for n, _, req, _, _ in FIELDS if req)

_URL_RE = re.compile(r"^https?://\S+$", re.I)
_TIME_RE = re.compile(r"^(?P<h>\d{1,2}):(?P<m>\d{2})$")

_MONTHS_KO = "1월 2월 3월 4월 5월 6월 7월 8월 9월 10월 11월 12월".split()


class FieldError(ValueError):
    pass


def _coerce_date(v):
    """ISO in, date out. The form supplies ISO; anything else is a caller bug,
    and guessing a format is what this module exists to stop."""
    if isinstance(v, _dt.date):
        return v
    try:
        return _dt.date.fromisoformat(str(v).strip())
    except ValueError:
        raise FieldError(f"date must be ISO (YYYY-MM-DD), got {v!r}")


def _coerce_time(v):
    m = _TIME_RE.match(str(v).strip())
    if not m or not (0 <= int(m["h"]) <= 23 and 0 <= int(m["m"]) <= 59):
        raise FieldError(f"time must be HH:MM (24h), got {v!r}")
    return _dt.time(int(m["h"]), int(m["m"]))


def render_date(d, ko):
    """The one place a date becomes text. Weekday is deliberately NOT rendered:
    it was the single most-invented value across the seven-model sweep, and a
    reader does not need it when the date is exact."""
    return f"{_MONTHS_KO[d.month - 1]} {d.day}일, {d.year}" if ko \
        else f"{d.strftime('%b')} {d.day}, {d.year}"


def render_time(t, tz, ko):
    if ko:
        ampm, h = ("오후", t.hour - 12) if t.hour >= 12 else ("오전", t.hour)
        h = h or 12
        s = f"{ampm} {h}시" + (f" {t.minute}분" if t.minute else "")
    else:
        s = t.strftime("%-I:%M %p" if t.minute else "%-I %p")
    return f"{s} {tz}" if tz else s


def validate(payload, ko=False):
    """(facts, errors). facts carries RENDERED strings, ready for fact_lines().

    Errors are returned rather than raised so a form can show all of them at once.
    """
    p = payload or {}
    facts = {n: None for n, *_ in FIELDS}
    facts["topics"] = []
    errors = {}

    for name, kind, required, *_ in FIELDS:
        raw = p.get(name)
        if kind == "list":
            facts["topics"] = [str(t).strip() for t in (raw or []) if str(t).strip()]
            continue
        if raw is None or str(raw).strip() == "":
            if required:
                errors[name] = "required"
            continue
        raw = str(raw).strip() if not isinstance(raw, (_dt.date, _dt.time)) else raw
        try:
            if kind == "date":
                facts[name] = _coerce_date(raw)
            elif kind == "time":
                facts[name] = _coerce_time(raw)
            elif kind == "tz":
                if raw.upper() not in TIMEZONES:
                    raise FieldError(f"timezone must be one of {', '.join(TIMEZONES)}")
                facts[name] = raw.upper()
            elif kind == "url":
                if not _URL_RE.match(raw):
                    raise FieldError("link must start with http:// or https://")
                facts[name] = raw
            else:
                facts[name] = raw
        except FieldError as e:
            errors[name] = str(e)

    # A time without a zone publishes an ambiguous hour, which is a grounding
    # defect even though every individual field validated.
    if facts.get("time") and not facts.get("timezone"):
        errors.setdefault("timezone", "required when a time is given")

    out = dict(facts)
    if isinstance(facts.get("date"), _dt.date):
        out["date"] = render_date(facts["date"], ko)
    if isinstance(facts.get("time"), _dt.time):
        out["time"] = render_time(facts["time"], facts.get("timezone"), ko)
    out.pop("timezone", None)
    return out, errors
