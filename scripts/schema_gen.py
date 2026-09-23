#!/usr/bin/env python3
"""Fact/prose split for all six channels: code writes the facts, the model writes prose.

Generalised from scripts/prototype_schema_gen.py after it proved out on LinkedIn.
The reasoning, and the two failed iterations behind it, are in that file's header —
the short version is that a rule in a prompt is a request, and at the 2-3B tier it
is not reliably obeyed, so the rules that CAN be made structural are.

Three stages, and the order is the point:

  1. parse_brief()   code reads `key: value` lines and `- ` bullets. No model, so
                     nothing can be reformatted or invented.
  2. model           writes hook / body / cta / hashtags under a JSON schema. It is
                     never shown a date field, so it has none to fill.
  3. assemble()      code emits the details block from the parsed facts, per channel.

What this makes structurally impossible, rather than merely forbidden:
  invented weekday · invented price · "[Insert Price]" · restyled event type
The event type comes from a code-filled field, which is why restyle — the one class
strip_ungrounded can only FLAG — stops happening here.

What it does not fix: invented characterisations in the prose ("legendary",
"once-in-a-lifetime"). Those are voice defects and belong to the ai_slop flag.

    python3 scripts/schema_gen.py --platform kakaotalk
    python3 scripts/schema_gen.py --all
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "testing/core"))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(HERE, ".env"))
import providers  # noqa: E402
import brief_fields  # noqa: E402
from evaluators import (evaluate as run_eval, strip_markdown,  # noqa: E402
                        strip_ungrounded, is_korean)
from prototype_schema_gen import (BRIEF, FACTS_SCHEMA, EXTRACT_SYS,  # noqa: E402
                                  PROSE_SCHEMA, call, parse_brief, ground_facts)

# Per-channel assembly. Each entry states what the CODE emits, so the model's brief
# stays the same everywhere and only the template differs. `bullets` False means the
# facts are folded into one line — KakaoTalk and WhatsApp are chat, not posters.
CHANNELS = {
    "linkedin":  dict(body=3, bullets=True,  tags=(3, 5), sentences=None,
                      details="labels", marker="•", links="full", header=True),
    "instagram": dict(body=2, bullets=True,  tags=(3, 5), sentences=None,
                      details="emoji", links="bio", header=False),
    "circle":    dict(body=4, bullets=True,  tags=(0, 0), sentences=None,
                      para=200, details="labels", marker="•", links="full", header=True),
    "kakaotalk": dict(body=1, bullets=False, tags=(0, 0), sentences=3,
                      prose_max=180, total_max=320,
                      details="labels", marker="▶", links="full", header=True),
    "whatsapp":  dict(body=1, bullets=False, tags=(0, 0), sentences=4,
                      prose_max=180, total_max=320,
                      details="labels", marker="•", links="full", header=True),
    # body=0: X's layout never shows one, and asking for it was where
    # hyperclovax fell into a repetition loop ("Sign up now and get a free
    # resource book…" × N) that ran to the timeout three runs in a row.
    "x":         dict(body=0, bullets=False, tags=(2, 3), sentences=None, cap=280,
                      prose_max=140,
                      details="emoji", links="inline", header=False),
}

# Reader-facing labels. Date and time share one "When" line — a reader asks
# "when is it", not "what date" then "what time" — and topics sit under ONE
# heading instead of repeating "Topics:" on every item.
LABELS_EN = {"when": "When", "where": "Where", "person": "Speaker", "price": "Price",
             "topics": "What we'll cover", "register": "Register", "map": "Map",
             "details": "{} details", "details_plain": "Event details",
             "bio": "Link in bio to register"}
LABELS_KO = {"when": "일시", "where": "장소", "person": "연사", "price": "참가비",
             "topics": "주제", "register": "신청", "map": "지도",
             "details": "{} 안내", "details_plain": "행사 안내",
             "bio": "신청은 프로필 링크에서"}
# Emoji-led lines are how Instagram and X readers expect logistics; each is
# still a structured line (has_structured_lines accepts an emoji lead).
EMOJI = {"when": "🗓", "where": "📍", "person": "🎤"}

# --- event type as an enum -------------------------------------------------
# `restyle` (a briefed "coaching session" shipping as 세미나 / 워크샵 / 마스터클래스)
# is the last defect class strip_ungrounded can only FLAG, and it survives because
# the event type reaches the model as a free string it is free to paraphrase.
# An enum removes the freedom: the brief selects a key, and the label is looked up.
# Same move as date and location — the model is never asked to produce the value.
#
# Aliases are matched longest-first so "info session" does not resolve via "session".
# Trimmed from 9 keys to 3 on request — the smaller the enum, the less a
# reviewer has to think about before picking one. A brief that doesn't match
# any alias gets event_type=None, which is the SAME safe behavior as any other
# unknown fact: detail_lines() omits the line rather than guessing a label.
EVENT_TYPES = {
    "seminar":    ("Seminar", "세미나",
                   ["seminar", "세미나", "workshop", "워크숍", "워크샵", "talk",
                    "강연", "특강", "coaching", "코칭", "info session", "설명회"]),
    "webinar":    ("Webinar", "웨비나",
                   ["webinar", "웨비나", "online seminar", "온라인 세미나"]),
    "conference": ("Conference", "컨퍼런스",
                   ["conference", "summit", "컨퍼런스", "콘퍼런스", "meetup",
                    "networking", "네트워킹", "모임"]),
}
_ALIASES = sorted(((a, k) for k, (_, _, al) in EVENT_TYPES.items() for a in al),
                  key=lambda x: -len(x[0]))
# "coaching session with 박운영" / "박운영과 함께하는 코칭" -> the name, and the rest.
_WITH = re.compile(r"\s+(?:with|w/|featuring|feat\.?)\s+(.+)$", re.I)
_KO_WITH = re.compile(r"^(.+?)(?:\s*(?:님)?\s*(?:와|과)\s*함께(?:하는)?)\s*(.+)$")


def classify_event_type(raw):
    """Map a briefed phrase onto an enum key. Code only — no model, no inference
    beyond a literal alias match. Returns None when nothing matches, and a None
    event_type emits no line, exactly like any other unknown fact."""
    if not raw:
        return None
    low = str(raw).lower()
    for alias, key in _ALIASES:
        if alias in low:
            return key
    return None


def canonicalize(facts):
    """Split the free-text first line into (person, event_type key).

    parse_brief() puts the whole line in event_type, so "coaching session with
    박운영" left person null and the name buried in a string the model then
    paraphrased. Pulling the name out and resolving the rest to an enum key makes
    both fields code-written.
    """
    raw = facts.get("event_type")
    if isinstance(raw, str) and raw.strip():
        rest = raw.strip()
        m = _KO_WITH.match(rest)
        if m:
            if not facts.get("person"):
                facts["person"] = m.group(1).strip()
            rest = m.group(2).strip()
        else:
            m = _WITH.search(rest)
            if m:
                if not facts.get("person"):
                    facts["person"] = m.group(1).strip()
                rest = _WITH.sub("", rest).strip()
        facts["event_type"] = classify_event_type(rest)
    return facts


def event_label(key, ko):
    en, kr, _ = EVENT_TYPES.get(key or "", (None, None, None))
    return kr if ko else en


def flag_restyle(text, key, ko):
    """After the enum, a rival event-type label in the prose is a restyle by
    definition: the canonical label is the only correct one."""
    if not key:
        return []
    mine = (event_label(key, ko) or "").lower()
    hits = []
    for k, (en, kr, _) in EVENT_TYPES.items():
        if k == key:
            continue
        for lab in (en, kr):
            if lab.lower() != mine and re.search(re.escape(lab), text, re.I):
                hits.append(("restyle", lab))
    return hits


def prose_system(platform, spec):
    """One short instruction per channel. Short on purpose: the ablation measured
    gemma2:2b grounding perfectly at 120 chars and failing at 3,321."""
    s = [f"You write {platform} prose for an UPCOMING event.",
         "You are NOT given the date, time, location or price, and a details "
         "block carrying them is appended after your text. Never state or guess "
         "them, and never name a venue. Never write a URL, and never write a "
         "bracketed placeholder such as [link] or [링크] — the link is appended "
         "too. End the cta with a period, never a colon.",
         "hook: one complete sentence. "
         + ("body: return an empty list. " if not spec["body"] else
            f"body: {spec['body']} "
            + (f"paragraph(s) of about {spec['para']} characters each. "
               if spec.get("para") else "short paragraph(s). "))
         + "cta: one sentence inviting the reader to register or reply."]
    lo, hi = spec["tags"]
    s.append(f"hashtags: {hi} tags, no '#'." if hi else "hashtags: return an empty list.")
    if spec.get("sentences"):
        s.append(f"Keep the whole thing under {spec['sentences']} sentences.")
    if spec.get("prose_max"):
        s.append(f"Keep each of hook, body and cta under {spec['prose_max']} "
                 "characters — short messages, not paragraphs.")
    if spec.get("cap"):
        s.append(f"Keep the whole thing under {spec['cap']} characters.")
    s.append("Write in the SAME language as the facts. Keep names, venues and "
             "time-zone codes exactly as given. Plain text only.")
    return "\n".join(s)


def prose_schema(spec):
    """Per-channel PROSE_SCHEMA with the body length bound in the schema itself.

    Only the CAPS are bound. minItems=4 on body was measured forcing
    hyperclovax:1.5b into filler entries ("click: [") rather than more prose —
    constrained decoding makes a shape reachable, not a capability appear.

    `prose_max`, when a channel sets it, bounds hook/body-item/cta length too.
    Added after a live whatsapp generation shipped 836 characters against docs'
    own 50-150 ideal / 300 acceptable ceiling — "sentences: 4" bounds sentence
    COUNT, not length, and a run-on sentence sails straight past it. maxLength
    is enforced by the decoder's grammar, the same mechanism that already makes
    minItems/maxItems real rather than a request.
    """
    sc = json.loads(json.dumps(PROSE_SCHEMA))
    n = spec["body"]
    sc["properties"]["body"].update(maxItems=n)
    if spec.get("prose_max"):
        m = spec["prose_max"]
        sc["properties"]["hook"]["maxLength"] = m
        sc["properties"]["body"]["items"]["maxLength"] = m
        sc["properties"]["cta"]["maxLength"] = m
    lo, hi = spec["tags"]
    sc["properties"]["hashtags"].update(minItems=lo, maxItems=hi)
    return sc


def detail_lines(facts, ko, spec, keys=("when", "where", "person", "price")):
    """The logistics block, one line per KNOWN fact. A null field emits nothing —
    which is where '[Insert Price]' stays unrepresentable: no branch writes a
    placeholder."""
    L = LABELS_KO if ko else LABELS_EN
    when = " · ".join(v.strip() for v in (facts.get("date"), facts.get("time"))
                      if isinstance(v, str) and v.strip())
    values = {"when": when,
              "where": (facts.get("location") or "").strip(),
              "person": (facts.get("person") or "").strip(),
              "price": (facts.get("price") or "").strip()}
    out = []
    for k in keys:
        v = values[k]
        if not v:
            continue
        if spec["details"] == "emoji":
            if k == "price":
                # Folded onto the date line rather than a 4th emoji — Instagram's
                # scorer wants 1-3, and "free" is read together with "when".
                if out and out[0].startswith(EMOJI["when"]):
                    out[0] += f" · {v}"
                continue
            out.append(f"{EMOJI[k]} {v}")
        else:
            out.append(f"{spec['marker']} {L[k]}: {v}")
    return out


def topic_lines(facts, ko, spec):
    topics = [str(t).strip() for t in (facts.get("topics") or []) if str(t).strip()]
    if not topics:
        return []
    L = LABELS_KO if ko else LABELS_EN
    item = "•" if spec.get("marker", "•") == "•" else "-"
    return [f"{L['topics']}:"] + [f"{item} {t}" for t in topics]


def link_lines(facts, ko, spec):
    L = LABELS_KO if ko else LABELS_EN
    link = (facts.get("link") or "").strip()
    map_url = (facts.get("map_url") or "").strip()
    if spec["links"] == "bio":
        # Instagram captions don't render links; a URL there is dead text.
        return [L["bio"]] if link else []
    if spec["links"] == "full":
        return ([f"{L['register']}: {link}"] if link else []) + \
               ([f"{L['map']}: {map_url}"] if map_url else [])
    return []


def _cap(s, n):
    """Hard character cap at a word boundary, so nothing ships as 'this val'."""
    if not s or len(s) <= n:
        return s
    cut = s[:n]
    sp = cut.rfind(" ")
    if sp > n * 0.5:
        cut = cut[:sp]
    return cut.rstrip(" ,.!?、。:;—-") + "…"


def _join(sections):
    """Sections separated by a blank line, lines within a section by one newline.
    The blank lines are the point: a phone reader scans blocks, not sentences."""
    blocks = ["\n".join(l for l in sec if l) for sec in sections]
    return "\n\n".join(b for b in blocks if b.strip())


def _prose(prose, spec):
    cta = (prose.get("cta") or "").strip()
    # Stripping "[링크]" out of "지금 등록하세요: [링크]" leaves a sentence pointing at
    # nothing. The prompt now forbids the placeholder, but a prompt is a request,
    # so the dangling colon is closed in code.
    cta = re.sub(r"[:：]\s*$", ".", cta)
    hook = (prose.get("hook") or "").strip()
    # hyperclovax emitted the literal string "cta" as a body element, which shipped
    # into the post. A body paragraph that is just a schema key name is never prose.
    _KEYS = {"hook", "body", "cta", "hashtags"}
    # A single-token "paragraph" ("clickHere", "cta") is decoder debris, never prose.
    body = [b.strip() for b in (prose.get("body") or [])
            if b.strip() and b.strip() != cta
            and b.strip().strip("':\"").lower() not in _KEYS
            and len(b.split()) > 1]
    # The model routinely ends the body with the same ask as the cta ("Register
    # now to secure your spot…" twice, a few lines apart). A reader sees the
    # repeat; drop a body paragraph that opens with the cta's first three words.
    lead = " ".join(cta.lower().split()[:3])
    if lead:
        body = [b for b in body if not b.lower().startswith(lead)]
    body = body[:spec["body"]]
    # Backstop for `prose_max`: the schema's maxLength (prose_schema()) is the
    # primary defense, but is only as real as the backend's grammar support.
    # Measured cause: a live whatsapp generation shipped 836 chars ("sentences: 4"
    # bounds a COUNT, and a run-on sentence sails past it).
    if spec.get("prose_max"):
        m = spec["prose_max"]
        hook, cta = _cap(hook, m), _cap(cta, m)
        body = [_cap(b, m) for b in body]
    lo, hi = spec["tags"]
    tags = [t.lstrip("#").strip().replace(" ", "")
            for t in (prose.get("hashtags") or []) if t.strip()][:hi] if hi else []
    tags_line = " ".join("#" + t for t in tags) if tags and len(tags) >= lo else ""
    return hook, body, cta, tags_line


def _assemble_x(facts, hook, body, cta, tags_line, ko, spec):
    """X reads in one glance: hook, when, where, the ask. Built by PRIORITY under
    the 280 cap instead of slicing a long draft — slicing is what shipped
    'Don't miss out on this val' with no date or place at all."""
    link = (facts.get("link") or "").strip()
    details = detail_lines(facts, ko, spec, keys=("when", "where", "price"))
    ask = " ".join(x for x in (cta, link) if x)
    cap = spec["cap"]
    # Drop the least essential piece first until it fits.
    for sections in (
        [[hook], details, [ask], [tags_line]],
        [[hook], details, [ask]],
        [[hook], details, [link]],
        [[hook], details],
        [[hook], details[:1]],
    ):
        text = _join(sections)
        if len(text) <= cap:
            return text
    rest = _join([details[:1]])
    return _join([[_cap(hook, cap - len(rest) - 2)], details[:1]])


def assemble(platform, facts, prose):
    spec = CHANNELS[platform]
    hook, body, cta, tags_line = _prose(prose, spec)
    ko = is_korean(hook + " ".join(body))
    L = LABELS_KO if ko else LABELS_EN

    if platform == "x":
        return _assemble_x(facts, hook, body, cta, tags_line, ko, spec)

    ev = event_label(facts.get("event_type"), ko)
    header = []
    if spec.get("header"):
        # Ends in a colon: that is what has_headers() reads as a section header,
        # and it is where the code-written event type lands.
        header = [(L["details"].format(ev) if ev else L["details_plain"]) + ":"]

    details = header + detail_lines(facts, ko, spec)
    topics = topic_lines(facts, ko, spec)
    closing = [cta] + link_lines(facts, ko, spec)

    def build(body_paras):
        return _join([[hook]] + [[b] for b in body_paras]
                     + [details, topics, closing, [tags_line]])

    text = build(body)
    if spec.get("total_max") and len(text) > spec["total_max"] and body:
        # Only the body is elastic. hook, facts, topics, cta and links are what
        # a chat reader acts on; the body is "why attend" colour. Trim it to the
        # remaining budget, or drop it — never the logistics.
        fixed = len(build([])) + 2
        budget = spec["total_max"] - fixed
        body = [_cap(body[0], budget)] if budget > 40 else []
        text = build(body)
    return text


def flag_prose_contradictions(text, facts, brief):
    """Catch prose that states a fact contradicting the code-written block.

    The split guarantees the FACTS block. It does not stop the prose ALSO stating
    facts, and the prose invents them: on one run the block correctly said
    "장소: seattle university" while the prose above it said 세인트루이스 대학교
    (St. Louis) on instagram and "Seoul University" on circle. Internally
    contradictory output is arguably worse for a reader than a single wrong value,
    because both readings look authoritative.

    The prompt already says "do NOT restate date, time, location" and was ignored —
    the same lesson as everywhere else, so this checks in code. Flagged rather than
    rewritten: which of the two is wrong is a judgement, and guessing is the thing
    this whole design avoids.
    """
    out, nb = [], (brief or "").lower()
    loc = (facts.get("location") or "").strip()
    if loc:
        head = loc.split()[0].lower()
        # A university/campus/school named in prose that is not the briefed venue.
        for m in re.finditer(r"([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+(?:University|College|School)|"
                             r"[가-힣]{2,10}\s*(?:대학교|대학))", text):
            cand = m.group(0).strip()
            if cand.lower() not in nb and head not in cand.lower():
                out.append(("venue_contradiction", cand))
    # A profession or title attached to the person, absent from the brief.
    person = (facts.get("person") or "").strip()
    if person:
        for m in re.finditer(r"(?:renowned|legendary|famous|top-tier|leading|expert)\s+"
                             r"([a-z ]{3,30}?)\s*" + re.escape(person), text, re.I):
            out.append(("invented_credential", m.group(0).strip()))
    return out


def facts_from_fields(payload, ko):
    """The form path: typed fields in, rendered facts out, no model and no regex.

    strip_ungrounded() tests each term against the brief, so with no free text to
    test against, the grounded set IS the submitted fields — joined here into the
    string the guard checks. A weekday still cannot survive it, because no field
    produces one.
    """
    facts, errors = brief_fields.validate(payload, ko=ko)
    if errors:
        return None, None, errors
    facts = canonicalize(facts)
    grounded = "\n".join(str(v) for v in facts.values() if v and not isinstance(v, list))
    grounded += "\n" + "\n".join(facts.get("topics") or [])
    # canonicalize() turned the event type into an enum KEY ("seminar"), so the
    # displayed label ("세미나" / "Seminar") was absent from this string and the
    # restyle guard flagged the event's own name on every channel.
    ev = facts.get("event_type")
    if ev in EVENT_TYPES:
        grounded += "\n" + "\n".join(EVENT_TYPES[ev][:2])
    return facts, grounded, {}


def generate(platform, brief, model_id, fields=None):
    if fields is not None:
        facts, brief, errors = facts_from_fields(fields, ko=bool(fields.get("ko")))
        if errors:
            return None, None, None, f"field errors: {errors}"
        return _finish(platform, facts, brief, model_id)
    facts = canonicalize(parse_brief(brief))
    missing = [k for k, v in facts.items()
               if k not in ("topics", "event_type") and not v]
    if missing:
        mf, err = call(model_id, EXTRACT_SYS, f"Input:\n{brief}", FACTS_SCHEMA)
        if not err:
            mf, _ = ground_facts(mf, brief)
            for k in missing:
                if mf.get(k):
                    facts[k] = mf[k]
    facts, _ = ground_facts(facts, brief)
    return _finish(platform, facts, brief, model_id)


def _finish(platform, facts, brief, model_id):
    spec = CHANNELS[platform]
    # The prose is shown ONLY what it needs to write around: who, what kind of
    # thing, and the topics. Date, time, location, price and link are withheld
    # because code emits them — and because the model cannot contradict a fact it
    # was never given. The instruction not to restate them was measured being
    # ignored on 6/6 channels, which is the usual result for a rule in a prompt.
    payload = {"event_type": event_label(facts.get("event_type"), is_korean(brief))
                             or facts.get("event_type"),
               "person": facts.get("person"),
               "topics": facts.get("topics") or []}
    prose, err = call(model_id, prose_system(platform, spec),
                      "Facts:\n" + json.dumps(payload, ensure_ascii=False),
                      prose_schema(spec))
    if err:
        return None, facts, None, err
    text = assemble(platform, facts, prose)
    text, flags = strip_ungrounded(strip_markdown(text), brief)
    flags += flag_prose_contradictions(text, facts, brief)
    flags += flag_restyle(text, facts.get("event_type"), is_korean(text))
    return text, facts, flags, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--model", default=os.getenv("LOCAL_LLM_MODEL", "hyperclovax:1.5b"))
    ap.add_argument("--brief", default=BRIEF)
    ap.add_argument("--fields", default=None, help="path to a JSON file of typed fields")
    a = ap.parse_args()
    fields = json.load(open(a.fields)) if a.fields else None
    plats = list(CHANNELS) if a.all else [a.platform or "linkedin"]
    for p in plats:
        text, facts, flags, err = generate(p, a.brief, a.model, fields=fields)
        print(f"\n{'='*70}\n  {p.upper()}  ·  {a.model}\n{'='*70}")
        if err:
            print(f"  FAILED: {err}"); continue
        print("\n".join("  " + l for l in text.split("\n")))
        ev = run_eval(p, text)
        print(f"\n  rubric {ev['total']}/100 · {len(text)} chars · flags {flags or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
