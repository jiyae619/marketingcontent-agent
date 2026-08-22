# Labeling guideline

You are the only labeler, and you label across weeks. Without a fixed rule, today's
standard drifts from last month's — and because the golden set is the measuring stick,
that drift moves every downstream number silently. Decide the rule once, here.

Use this for **path A** (human verdicts in the review UI). Path B samples are labeled
by construction in `scripts/golden_set.py` and need no judgement.

## The verdict

Pick exactly one. Judge the post **as it would publish**, not as a draft you could fix.

| Verdict | Use when |
|---|---|
| **approve** | You would post this unchanged. |
| **edit** | You would post it after changes, and you make them. The diff is the signal — it says what was wrong better than a score. |
| **reject** | You would not post it. Something is wrong that editing would not fix cheaply — the wrong topic, invented facts, wrong language. |

**Never approve something you would not actually publish.** The whole set is calibrated
off this, and an approve you didn't mean makes a real defect look acceptable forever.

## The four flags

Flag the **single most serious** problem, not everything you notice. One flag per event
keeps categories comparable; a post with three flags tells you nothing about which
matters. If two are equally bad, prefer the `grounding` one — those are trust failures.

### `hallucination` — grounding
**Test:** point at the exact word in the brief that supports each specific claim.
Flag if you cannot, for any speaker name, title, date, time, location, price, or number.

- Flag: brief gives no price, post says "45달러" or "Price: (정보 없음)"
- Flag: brief says 12PM, post says 3PM
- Not this: vague-but-true phrasing that invents no fact

A placeholder announcing a missing fact (`(정보 없음)`, `[링크]`, `TBD`) **is** a
hallucination — the rule is to omit, not to narrate the gap.

### `irrelevant` — grounding
**Test:** could this post be about a different event with the nouns swapped?
Flag if yes.

- Flag: generic filler that never says what is notable about *this* session
- Flag: the event is re-characterised — career coaching described as a marketing seminar
- Not this: a short post. Brief ≠ irrelevant.

### `ai_slop` — voice
**Test:** would a real person write this sentence to a colleague?
Flag stacked clichés, hollow hype, or template phrasing.

- Flag: "In today's fast-paced world", "game-changer", "take it to the next level",
  "we are thrilled to announce", "don't miss out"
- Not this: one enthusiastic line. Slop is density, not the presence of energy.

### `kr_en_register` — voice
**Test:** does the output language match the brief's language, and does the formality
fit the channel?

- Flag: Korean brief, English body (or an English block inside a Korean post)
- Flag: 하십시오체 stiffness in a KakaoTalk message, or banmal on LinkedIn
- Not this: an English proper noun inside Korean text — `Seattle Public Library` is
  the venue's actual name, not a register break

## When you are unsure

**Leave it unlabeled.** An uncertain label is worse than no label: it enters the golden
set with the same weight as a confident one and quietly moves the accuracy number the
whole harness reports.

This is the same rule the judge follows — a `confidence: low` verdict is discarded and
routed to a human rather than guessed. Hold yourself to it too.

## Do not flag

- Formatting the pipeline already fixes — markdown, `**`, stray `#`.
  `strip_markdown()` removes those before you ever see the post.
- Length. The heuristic scores it; your judgement adds nothing.
- Style preferences you would not actually change. If you would ship it, approve it.
