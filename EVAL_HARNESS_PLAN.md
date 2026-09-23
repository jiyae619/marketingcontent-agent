# Plan v2 — a tool with a learning loop, and one evaluation that happens once

Rewritten 2026-09-20. Replaces v1, which was built around a runtime LLM judge and a
four-model cloud bake-off. Grounded in the repo at this commit and the live DB at
`testing/results/feedback.db`; every number is a query result.

---

## 0. What changed from v1, and why

v1 was wrong in two ways and I am correcting both rather than re-litigating them.

1. **It kept the LLM judge in the runtime.** At 102 lifetime generations the judge costs
   more than it saves, and `preflight` already reports `judge on generate: OFF` — it is
   not in the production path today. v1 proposed measuring a component that isn't running.

2. **Its Phase 4 violated CLAUDE.md rule 2.** A four-model cloud generator bake-off
   cannot run under `LOCAL_ONLY=true`, and the rule says stop and ask rather than
   disable the flag. The plan required breaking the project's own hard constraint.

**The architecture in this plan:** generator is a local model · the reviewer is a human ·
the human's *edits* are the learning signal · and evaluation is an **offline, one-time
decision procedure** for choosing the generator, not standing runtime infrastructure.

One consequence worth stating up front: v1 argued the shared `FLAG_TAXONOMY` mattered
because it made human flags and judge scores comparable. With no runtime judge, that is
no longer the goal. The human vocabulary's job now is to **route the learning signal**,
so §3 gives it a richer vocabulary of its own that keeps the same two families.

---

## 1. Ground truth

```
generations        102 rows   (67 have NULL model — predate the `model` column)
judge_results       14 rows   (7 graded / 5 failed / 1 abstained on llama3.2:3b)
feedback_events     10 rows   (9 approve, 1 edit, 0 reject, 0 flags)
golden_set_v1       34 samples — 17 clean / 17 defect-injected, 8 distinct briefs
```

Four facts this plan is built on:

1. **The loop reads the wrong half of the data it stores.** `feedback_events` holds both
   `original_content` and `final_content` (`feedback_db.py:120`), but `recent_copies()`
   selects only `final_content` and `server.py:202` formats only `ex['final_content']`.
   **The diff is captured and never read.**

2. **Under `LOCAL_ONLY=true`, voice synthesis cannot run.** It is hard-wired to
   `providers.call_gemini` (`server.py:222`). Verified:
   `call_gemini under LOCAL_ONLY → {'ok': False, 'error': 'LOCAL_ONLY=true — refused a paid API call'}`.
   It degrades silently to raw few-shot (`recent_copies`, limit 3) and prints
   `[voice] synthesis returned nothing`. The staleness rule itself works — `get_voice_profile`
   returns None after 3+ new events, which re-triggers — so the loop is throttled, not frozen.

3. **Nothing guards the loop.** Grepped for a quality check on a voice bump: there is none.
   `save_voice_profile` bumps `voice_versions` and invalidates the cache, so a bad profile
   degrades every later generation *and* removes the cached rows you would compare against.

4. **Zero human flags exist.** The flag ships only on `reject` (`ReviewPanel.jsx:155`) and
   there have been no rejects. The label-producing path is the one nobody uses.

---

## 2. The architecture

```
brief ─► local generator ─► draft ─► HUMAN reviews
                                       │
                          ┌────────────┼────────────┐
                       approve       edit         reject
                          │            │             │
                          │     what changed (computed diff)
                          │     why it changed (one chip + optional note)
                          │            │
                          └────────────┴──► feedback_events
                                                  │
                                    family = voice ──► voice corpus ──► prompt
                                    family = grounding ──► brief/prompt defect list
                                                  │
                                         voice_version bump
                                                  │
                                         REGRESSION GATE (§5)
```

No LLM judge anywhere in that path. The only model call is generation.

---

## 3. Capturing what changed, and why

Two halves, deliberately split by who is cheap at what. **The machine computes *what*.
The human says *why*, in one click.**

### 3a. What changed — computed, never asked

Word-level diff (char-level is noise on prose, line-level is too coarse):

```python
import difflib

def diff_ops(original, final):
    """Structured record of the human's edit. Computed from data already stored."""
    a, b = (original or "").split(), (final or "").split()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = [{"op": tag, "from": " ".join(a[i1:i2]), "to": " ".join(b[j1:j2])}
           for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]
    return {"ops": ops,
            "n_edits": len(ops),
            "pct_changed": round((1 - sm.ratio()) * 100, 1)}
```

This costs the human nothing and it is the richer signal: it says *which words* were
cliché, not merely that some were.

### 3b. Why it changed — one chip

The routing rule is what the chip exists for: **a `voice` edit teaches the voice corpus,
a `grounding` edit never does.** Mixing them is how a loop learns a factual correction as
a style rule — feed it "changed the date to Nov 3" and it starts writing Nov 3 into every
post. So the chip is not decoration; it is the guard on the corpus.

```python
# Why a human changed a draft. Family decides routing, and the two families are the
# same ones FLAG_TAXONOMY already uses, so `flag_family` needs no new values.
EDIT_REASONS = {
    # voice — the diff FEEDS the voice corpus
    "ai_slop":        "voice",      # cliché, hype, template phrasing
    "kr_en_register": "voice",      # wrong language or formality for the channel
    "tone":           "voice",      # right facts, wrong warmth or directness
    "length":         "voice",      # outside the channel's band
    "convention":     "voice",      # emoji, hashtags, line breaks, markdown leak,
                                    # or a MISSING channel convention (CTA, sign-off)
    # grounding — the diff NEVER feeds the voice corpus
    "hallucination":  "grounding",  # a fact that is not in the brief
    "wrong_detail":   "grounding",  # the fact is in the brief, transcribed wrong
    "omission":       "grounding",  # dropped a fact the brief DID provide
    "irrelevant":     "grounding",  # generic; missed what is notable about THIS event
}
```

**`convention` and `omission` exist because the real data demanded them.** The single edit
event in the DB is an *addition*, not a correction:

```
event 10 [linkedin]  pct_changed=1.7%  n_edits=1
   insert  '' -> 'P.S. Register early — seats are limited.'
```

A first draft of this vocabulary framed every chip as "what was wrong" and had nowhere to
put that. Real edits add as often as they fix, and the two kinds of omission route
differently: a missing CTA is a channel convention the model **should** learn, while a
dropped date from the brief is a prompt failure it **must not** learn as style.

**Kept separate from `FLAG_TAXONOMY` on purpose.** The verdict schema is derived from
`FLAG_TAXONOMY` (`judge.py:146`) and the golden set has its own hard-coded `DEFECTS`
(`scripts/golden_set.py:50`), so every added category would force golden-set churn. The
two vocabularies answer different questions. They share the *families*, which is the part
that routes.

### 3c. The UI

On save-after-edit, one required chip in two visually separated rows, plus free text:

```
You changed 23% of this draft.          ← computed, shown not asked

Reads wrong   [ ai slop ] [ register ] [ tone ] [ length ] [ convention ]
Facts wrong   [ invented ] [ wrong detail ] [ dropped ] [ off-brief ]

Anything else? ________________________________________  (optional, ≤200 chars)
```

Three notes on why it is shaped this way:

- **One chip, not multi-select** — `docs/labeling-guideline.md` already rules that a
  single flag keeps categories comparable, and its existing tiebreak ("if two are equally
  bad, prefer the `grounding` one") happens to be exactly the conservative routing this
  needs: a mixed edit lands on `grounding` and stays out of the voice corpus. Reuse the
  rule rather than inventing a second one.
- **Showing `pct_changed` back** makes the metric legible to the person generating it,
  and it is the number §4 is built on.
- **The free-text box is the escape hatch** for the mixed edit the single chip flattens.
  It is not parsed; it is read by a human later. Do not build anything that reads it.

### 3d. Schema

```sql
ALTER TABLE feedback_events ADD COLUMN edit_ops    TEXT;  -- JSON from diff_ops()
ALTER TABLE feedback_events ADD COLUMN pct_changed REAL;
ALTER TABLE feedback_events ADD COLUMN edit_note   TEXT;  -- free text, unparsed
```

`flag_category` holds the chip and `flag_family` its family — both columns already exist.
Validate the chip against `EDIT_REASONS` the way `log_feedback` already validates against
`FLAG_TAXONOMY` (`feedback_db.py:515`).

---

## 4. The metric: how much the human had to fix

`pct_changed` is the one quality number obtainable **with no judge, no rubric and no
labeling effort**, because it is a by-product of work the human is doing anyway. Median
percent of a draft rewritten is behavioural ground truth: it measures what the generator
actually cost its reader.

Report it by platform, by generator model, and over time. A loop that is working pushes it
down.

**Its confounds, stated so they are not discovered later:** it conflates a weak draft with
a fussy editor; long drafts change more in absolute terms (which is why the ratio is
normalized); an approve-without-reading registers 0%; and it cannot tell a rescue from a
polish. It is a good *ongoing health* metric and a weak *experiment* metric — which is why
model selection in §6 uses blind rubric scoring instead, and uses `pct_changed` only to
check the two agree.

---

## 5. The one place eval belongs in the runtime: a gate on the loop

Not a judge on every draft. A regression check on the thing that can silently rot.

When `voice_version` bumps for a platform: re-run that platform's golden briefs through
the current generator, score with the existing heuristic (`testing/core/evaluators.py`),
and compare against the previous voice version's scores. If the median drops beyond a
threshold, flag the new profile rather than adopting it silently.

Free, local, rule-compliant, minutes to run. It is also the only thing standing between
"the loop learns" and "the loop learned something wrong and nothing noticed."

---

## 6. Choosing the generator — the evaluation that happens once

This is an offline decision procedure, run when you pick a model and when you seriously
consider changing it. It is not a service.

**Prompt set.** Harvest the **8 distinct briefs** from `golden_set_v1.json`, which span 9
platform×language cells (20 en / 14 ko). Reuse the *briefs*, not the labels — `expect_fail`
describes injected defects and says nothing about generator quality. State that reuse
plainly in the writeup.

**Candidates.** Local 4B tier only, per CLAUDE.md rule 1 — `gemma3:4b` and the other
tier-legal options. Not `qwen3:4b`: the handoff doc records 357s for one post and a 120s
judge timeout.

**Scoring — you, blind.** There is no judge in this architecture, the heuristic is
documented as blind to grounding (`server.py:33`), and a cloud judge breaks rule 2. So:
shuffle the outputs, strip model identity, score against the §3b rubric categories. 3
models × 8 briefs = 24 outputs. One focused afternoon, once.

*"I scored 24 outputs blind against a written rubric"* is more defensible than any
LLM-judge number available at this N, and it costs nothing.

**Frame the question correctly.** The golden set's clean bases were written by
`gemini-2.5-flash` (16) and `claude-sonnet-4-6` (4) — cloud models. Your candidates are 4B.
The likely finding is that every local option clusters below that baseline. So ask
**"is a local 4B good enough for this job?"** rather than "which local model wins." The
first question has an actionable answer either way, including *"no, and here is what
`LOCAL_ONLY` costs in quality"* — which is the most decision-relevant result available and
the only evidence that could justify revisiting rule 2.

**Cross-check.** After a month of real use, confirm the model you picked also has the
lowest median `pct_changed`. If the blind ranking and the edit-distance ranking disagree,
one of the two instruments is wrong and that is worth knowing.

---

## 7. Sequence

**P1 — Read the half of the data you already store.** (~1 day)
`diff_ops()`, the three columns in §3d, persist on every edit. Backfill the existing rows —
`original_content` and `final_content` are both there. Nothing user-facing changes yet.

**P2 — The chip.** (~1 day)
`EDIT_REASONS`, validation in `log_feedback`, the UI in §3c. Critically: the chip ships on
**edit**, not only on reject. Route the diff into the voice corpus only when
`family == "voice"`.

**P3 — Make the loop run under `LOCAL_ONLY`.** (~half day)
Voice synthesis currently calls `providers.call_gemini` and is refused. Either route it
through the local model or drop synthesis and keep few-shot as the loop. Decide, and make
the failure loud instead of a print line.

**P4 — The regression gate.** (~half day) §5.

**P5 — Model selection.** (one afternoon, free) §6.

**P6 — Rewrite the case study** around what this actually is.

P1–P4 are the product. P5 is the study. They are independent after P1.

---

## 8. What to claim, and what not to

**Claimable:** the loop reads what the human changed, not just what they kept · voice and
grounding edits are routed differently, and why that matters · median `pct_changed` by
model and over time · a blind, rubric-scored model selection with N stated · a regression
gate that can veto a learned profile · and that the LLM judge was **removed from the
product** because its reliability could not be demonstrated.

**Not claimable, and say so:** that the loop improves output — that needs `pct_changed`
over time and you have 1 edit today · any judge accuracy number (N=8, and 5 of 13 local
judge calls failed) · that golden-brief performance predicts live performance · any
efficiency percentage, which v1's protocol already declined to claim.

**The line worth leading with:** *I took the LLM judge out of the product because I could
not show it was reliable, and I kept evaluation exactly where it paid for itself — one
offline decision, scored blind.* Right-sizing is rarer than shipping a platform.

**And name the trigger that would reverse it.** The judge is not wrong forever, it is wrong
at 102 generations with one reviewer. State the volume — drafts per week, or reviewers —
at which a human reading everything stops being viable, because that is the number that
turns the judge back on.

---

## 9. Codex review — defect status

Independent read-only review (session `01a0c184`), each item re-verified against source.

**Fixed and verified in this session:**

- **Missing-category abstention never fired.** `judge.py:256` — the isinstance guard was
  inverted, so a category absent from `scores` counted as reasoned. Fixed; a fourth probe
  `missing-category` added to `tools/bughunt/detectors.py`. Verified old-code-fails /
  new-code-passes.
- **`judge != generator` bypassable over HTTP.** `server.py:441` consulted the data spine
  only when the client omitted `generator_model`. The recorded model is now authoritative
  and an unknown `generation_id` is a 400. Verified against the running server.
- **Cache key omitted the generator.** `feedback_db.py:568` keyed on input only, so a
  second model's request returned the first model's post under its name. Model and
  prompt version are now required key components, with two regression tests.
  *Not verified end-to-end:* a live two-model miss needs a paid call under `LOCAL_ONLY`.

**Open, in rough priority for this architecture:**

- Judge claims are not exclusive (`feedback_db.py:353`, `server.py:266`) — duplicate paid
  calls and a lost-update race. Low urgency now the judge is offline-only.
- Scores are unbounded; `overall=999` parses and persists as `graded` (`judge.py:146`).
- `scripts/export_eval_log.py:41` drops judge `status`, so abstained / failed / never-
  dispatched all render as "not graded" in the artifact a reader would actually open.
- A generation can be returned after logging failed (`server.py:618`), creating an
  approved post with no `generation_id` — an unlinked decision. **This one matters more in
  the new architecture, not less:** the edit loop is the product, and an unlinked edit is
  a lost training example.
- Hard-coded 2025-11 prices rendered as per-run cost in the compare UI (`providers.py:1`).
- Golden-set taxonomy can drift from `FLAG_TAXONOMY`; assert equality in CI.
- `eslint` is red solely from the untracked stale copy at `marketingcontent-agent/src/App.jsx:131`.
  Deleting or gitignoring that directory turns the check green.
