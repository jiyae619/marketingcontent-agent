---
date: 2026-07-22
topic: content-agent-data-spine
---

# Content Agent Data-Integrity + Instrumentation Spine (with Flag Taxonomy)

## Summary

Build the data-layer substrate the marketing content agent needs before the human-in-the-loop review UI, the LLM judge, and the eval dashboard can exist: fix the copy-lineage bug, attach provenance to every generation, model human feedback as one verdict-event stream carrying a two-family flag taxonomy, instrument hands-on time, and define a manual "before" baseline. No UI in this phase — the goal is a clean, attributed, labeled dataset that starts accumulating the moment the team uses the agent for real.

---

## Problem Frame

The agent generates channel-tailored content today, but the substrate underneath it silently loses or corrupts the data a production eval-and-learning system depends on. Copies of cached content are logged with no link back to the generation that produced them, so the approval signal is orphaned exactly on the most common path. Generations record nothing about which model, prompt, or voice version produced them, so no one can ask "which model is best for KakaoTalk?" or "did that prompt edit regress quality?" The feedback path accepts any non-empty string, so an `Error: ...` message can be copied and fed into the voice profile that shapes every future generation. Voice profiles are overwritten in place with no history, so a bad synthesis is unrecoverable. And the headline claim the project wants to make — that the agent cuts content-creation time — is unmeasurable, because nothing computes the time already sitting in the database.

This matters now because the team has not yet used the agent for real content generation. Everything captured from first real use is either clean or permanently lossy depending on decisions made before that first session. Two failure modes already seen in testing — grounding failures (hallucinations and irrelevant content about the speaker/event) and voice failures (AI slop that needs humanizing) — will only be diagnosable and improvable if each human correction is captured as attributed, categorized data from day one. There is also a cold-start reality: with no reference content, early output will be rough, and the voice loop can only climb out of that as corrections accumulate. The substrate is what makes that climb possible and measurable.

---

## Key Flows

- F1. Data lifecycle (generation → verdict → learning/measurement)
  - **Trigger:** User generates content for one or more channels from a prompt.
  - **Actors:** Human reviewer (produces verdicts), the agent (generates + learns), downstream consumers (voice loop now; judge, dashboard, metrics later).
  - **Steps:**
    1. Agent generates content; the generation is recorded with full provenance (model, prompt version, voice version) and a lineage id — including on cache hits.
    2. Human issues a verdict on that generation: approve, edit, or reject. An edit or reject may carry a flag (category + family).
    3. Verdict is written to a unified feedback-event stream, linked to the generation by lineage id; edits capture before/after so the correction diff is derivable.
    4. Validated approve/edit events feed voice-profile synthesis (versioned); flags and diffs accumulate as labeled examples; timestamps feed the hands-on-time metric.
  - **Outcome:** Every human judgment is a clean, attributed, categorized record that the voice loop consumes now and the judge/dashboard/metrics consume later.
  - **Covered by:** R1, R3, R5, R6, R8, R9

```
generation ──(provenance + lineage id)──► FEEDBACK EVENT ──► voice loop (now)
   ▲                                       (approve/edit/reject          │
   │                                        + optional flag)             ├─► judge criteria (later)
 cache hit ── still carries lineage id ─────┘   │                        ├─► eval dashboard (later)
                                                │                        └─► hands-on-time metric
                              flag family split │
                       grounding (hallucination, irrelevant) ─► signal: needs facts/RAG (later phase)
                       voice   (AI slop, KR-EN register)      ─► improves as diffs accumulate
```

---

## Requirements

**Data integrity**
- R1. Every draft surfaced to a human carries a stable lineage id back to its generation, with no exceptions — including cache-hit responses, which currently return none.
- R2. The feedback path rejects input that is not genuine approved content (e.g., error strings, empty/placeholder text) so it cannot enter voice-profile training.

**Provenance**
- R3. Every generation records which model, prompt version, and voice version produced it.
- R4. Voice profiles are versioned rather than overwritten in place, so any synthesis can be inspected and rolled back.

**Feedback event model + flag taxonomy**
- R5. Human feedback is modeled as a unified verdict-event stream capturing approve, edit, and reject — generalizing today's approvals-only model — with each event linked to its generation.
- R6. A verdict may optionally carry one flag: a category plus its family.
- R7. The v1 flag taxonomy is fixed but extensible — four categories in two families: **grounding** (hallucination; irrelevant / off-brief) and **voice/style** (AI slop / robotic; wrong tone / Korean–English register). The same taxonomy is the schema for human flags now and the judge's scoring criteria later.
- R8. Edit verdicts capture both the generated text and the human-final text so the correction diff is derivable without a separate step.

**Instrumentation + baseline**
- R9. Per-session hands-on time (first generation to final approval) is computed from stored timestamps and surfaced in admin stats.
- R10. A documented manual "before" baseline exists: 3–5 timed manual content-creation sessions by team members, with the median recorded as the comparison point.

**Substrate validation**
- R11. A thin write-path test or fixture exercises the full feedback-event model (each verdict type, flagged and unflagged) so the schema is validated before any real use, since no UI writes to it in this phase.

---

## Acceptance Examples

- AE1. **Covers R1.** Given an input whose content is served from cache, when the response is returned, it includes the same lineage id a fresh generation would, and a subsequent approval links to that generation rather than being orphaned.
- AE2. **Covers R2.** Given a generation failed and the surfaced text is an error message, when the user attempts to approve/copy it, the feedback path rejects it and it does not enter voice-profile training.
- AE3. **Covers R5, R6, R8.** Given a user edits then approves a draft and flags it "AI slop," when the verdict is written, the stream records an edit event with the flag (voice family), the original text, and the final text — all linked to the generation.
- AE4. **Covers R3.** Given the same prompt is run through the compare path across four models, when the generations are recorded, each is attributable to the specific model that produced it.
- AE5. **Covers R9.** Given a session where a user generates at T0 and approves the last channel at T1, when admin stats are viewed, the session's hands-on time reflects T1−T0.

---

## Success Criteria

- From the first real team use, every human judgment is captured as a clean, attributed (model/prompt/voice version), categorized (flag + family) record linked to its generation — no orphaned approvals, no corrupted training inputs.
- The grounding-vs-voice family split is present in the data so the two failure classes can be counted and routed differently (voice → learn over time; grounding → evidence that structured input/RAG is needed).
- Hands-on time per session is queryable, and a documented manual baseline exists, so the time-savings story can be stated as measured data ("~X min manual → ~Y min with the agent") rather than asserted — with cold-start understood as a lagging indicator, not a launch metric.
- A downstream implementer (`ce-plan`) can build the approve/edit/reject UI, the judge, and the dashboard by writing into and reading from this model without inventing new feedback structure.

---

## Scope Boundaries

- No approve/edit/reject flag-capture UI in this phase (that is ideation idea #4, next phase). This phase delivers the data model and taxonomy schema the UI will write into.
- No LLM judge and no eval dashboard (idea #3, next phase) — R7 defines the shared taxonomy so the judge inherits it later; it does not build the judge.
- No language-aware rubric implementation (idea #6, next phase) — the taxonomy captures the KR-EN register category; the rubric that scores it comes later.
- No scheduling or publish/upload integration (idea #7, next phase).
- No finetuning.
- No fix for grounding failures themselves (structured event/speaker input or retrieval/RAG). Deliberately excluded here but flagged as the investment the cold-start reality makes urgent; the grounding flags in R7 are what will justify and prioritize it.

---

## Key Decisions

- **Unified verdict-event stream over an approvals-only model:** approve, edit, and reject are one linked stream rather than a separate rejections table bolted alongside copies. Rationale: idea #4's UI, idea #5's diff-learning, and the dashboard all read the same data; a split model forces every downstream consumer to reconcile two sources, which is the split-brain the dashboard exists to avoid.
- **One taxonomy for humans and the judge:** human flag categories and judge scoring criteria are the same set. Rationale: this is what makes each human flag a calibration label for the exact criterion the judge will score — the "enterprise evals / data labeling" property the project wants to showcase. Two vocabularies would waste every label.
- **Two-family tagging (grounding vs voice):** each category carries a family. Rationale: the families have different fixes and different cold-start behavior — voice improves as data accumulates; grounding needs upstream facts and cannot be waited out. The tag is the routing key for that difference.
- **Pure plumbing before UI:** architect and validate the whole substrate first, then test on real cases. Rationale: production is not scheduled; getting the model right before first real use avoids a migration under load and prevents lossy early data.
- **Success is data quality, not immediate content quality:** given cold-start, this phase is judged on whether the captured data is clean and complete, not on whether early output is good.

---

## Dependencies / Assumptions

- Assumes the existing single-file Python backend, SQLite store, and React frontend remain the stack for this phase (`server.py`, `feedback_db.py`, `src/`).
- The manual baseline (R10) depends on team availability for a few timed sessions; it is a process task, recoverable at any time, and does not block the code work.
- The value of the captured data depends on the team actually using the agent for real generation after this phase ships; the substrate enables the payoff but does not itself produce content-quality gains.
- Verified during brainstorm against the codebase: the cache-hit lineage gap, the approvals-only feedback model, the missing generation provenance, the unvalidated feedback input, and the destructive voice-profile overwrite all exist as described.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R3][Technical] How is "prompt version" identified — content hash of the channel prompt, git-tracked version, or a stored revision? Answer during planning from repo context.
- [Affects R4][Technical] Voice-profile versioning shape — full history vs last-N vs promote/rollback pointer — and whether golden-set regression gating is in this phase or deferred.
- [Affects R9][Technical] Which lightweight session events (beyond generation and approval timestamps) are needed to bound a "session," and how a session is delimited.
- [Affects R7][Needs research] Whether "irrelevant / off-brief" and "hallucination" need sub-distinctions in the schema now, or a single category each suffices until the judge is built.
- [Affects R11][Technical] Form of the write-path validation — unit test, seed script, or fixture — chosen during planning.
