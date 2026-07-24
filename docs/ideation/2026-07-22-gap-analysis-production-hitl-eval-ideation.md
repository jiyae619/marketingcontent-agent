---
date: 2026-07-22
topic: gap-analysis-production-hitl-eval
focus: Gap analysis vs target end-state — production HITL multi-channel content system with multi-model LLM evaluation framework grading quality and safety, cutting manual review 83% (30 → 5 min)
mode: repo-grounded
---

# Ideation: Closing the Gap to a Production HITL Content Agent with a Multi-Model Eval Framework

## Grounding Context

**Codebase Context** (repo: marketingcontent, branch include-new-platform):
- React 18 + Vite frontend; single-file Python backend `server.py`; SQLite `feedback_db.py`; `providers.py` multi-model abstraction (Gemini, GPT-4o mini, Claude Haiku/Sonnet).
- 6 channels (LinkedIn, Instagram, CIRCLE, KakaoTalk, WhatsApp, X); channel prompts live in `docs/*.md` (`## AI Prompt` sections parsed by `load_prompt_from_md`).
- Flow: one prompt → generate for all selected channels → preview → user copies content out (copy = implicit approval → SQLite → voice-profile synthesis injected into future prompts).
- Heuristic evaluator (`testing/core/evaluators.py`, 15+ criteria per platform, 0–100) runs on **every** generation but: score never returned to the main UI (console print only), never gates anything, content cached unconditionally, per-criterion `suggestion` strings never consumed.
- `/api/compare` fans one prompt to 4 models; all outputs logged **without model attribution** (no `model` column); winner-pick is UI-only.
- Cache-hit path returns no `generation_id` → copies of cached content are logged orphaned (`generation_id NULL`).
- `generations.created_at` + `copies.copied_at` exist but no query computes handling time — the 30→5 min claim is currently unfalsifiable.
- Verified during ideation: `App.jsx:367` (`onContentChange`) means in-app edits DO flow into `copies.final_content`; the generated-vs-final diff is stored but never computed.
- No safety criteria exist anywhere (grep `safety|claim|banned|pii` in evaluators.py = 0 hits).

**External Context** (web research, 2026-07): production evals are tiered (deterministic → flash-tier LLM judge → human residue); judge biases (position, verbosity, self-preference, authority) are design requirements; "a weak judge on a great rubric outperforms a great judge on a weak rubric"; judge calibration consensus ≈500 human-labeled cases, Spearman >0.8; HITL failure mode is vigilance decrement, mitigated by confidence-gated routing + random spot-checks; review-time claims require instrumented session-level before/after logging (TSPA "handling time"); QUEST review-value routing (reach × severity / cost); market gap — no product combines brand-voice generation + LLM-judge quality/safety + HITL queue; IAB AI-transparency (Jan 2026) / EU AI Act / C2PA push provenance metadata for published AI content; flash-tier judges ≈1/30 frontier cost.

**Past Learnings:** none — `docs/solutions/` does not exist yet.

## Target Workflow Journey (owner's vision, added 2026-07-22)

1. **One prompt** (event/content info) + channel selection → channel-tailored content with visual preview options. *Exists today; the preview is the "creativity" showcase pillar.*
2. **Approve / edit / reject with flag categories** (too long, misinformation, hallucination, inappropriate content, …). *Maps to idea 4; the flag taxonomy is new and doubles as the label schema for judge calibration (idea 5) — design ONE taxonomy shared by human flags and judge criteria so human labels calibrate the judge per category.*
3. **Approve → agent posts at user-scheduled time**, or manual upload fallback. *Maps to idea 7 + a scheduling addition (scheduler-intermediary first is the pragmatic path).*
4. **Edit/reject → backend diffs generated vs final** and learns user preferences into voice/content. *Maps to idea 5 + the existing voice loop; the diff substrate is verified present, unmined.*
5. **Backend judge/eval with a user-facing dashboard**: prompt instruction, content guardrails/safety guidelines, per-content confidence score, model, logs, and the ability to improve outputs — enterprise evals/data-labeling style. *Maps to ideas 1+3+6 surfaced as UI. Hard dependency: model attribution (idea 1) — a per-content "model" field is impossible today because no model column exists. Guardrails become displayable if rubrics are data (idea 6).*
6. **Open question — finetuning / RAG:** deferred (see assessment in conversation). Capturing preference data now (ideas 1, 5) preserves finetuning optionality without committing; RAG only becomes warranted if content must be grounded in a real document corpus.

**Showcase goal mapping:** efficiency → ideas 1 (measured) + 4 (routing); evaluation framework → idea 3 + the dashboard; content safety/guidelines → ideas 3 + 6; creativity → preview feature (exists; polish).

## Ranked Ideas

### 1. Data-integrity + instrumentation spine (two-sided measurement of the time-savings claim)
**Description:** Two halves. **(a) Instrument the "after":** fix the cache-hit path that returns no `generation_id` (orphaned copies); add `model`, `prompt_hash`, `voice_version` columns to `generations`; validate what enters `/api/copies` (an `Error: ...` string can currently be copied into voice-profile training); version voice profiles instead of destructive `ON CONFLICT` overwrite; compute per-session hands-on time (first generation → last approval, `copied_at − created_at` + lightweight session events) and surface it in admin stats. **(b) Measure the "before" with the team:** the manual baseline cannot come from the DB — the tool didn't exist in that workflow. Run 3–5 timed manual sessions (team members write one multi-channel content set without the agent, timed) and record the median as the documented baseline.
**Warrant:** `direct:` server.py:328 cache-hit payload omits `generation_id`; `feedback_db.log_generation()` has no model param (model name survives only in a `print()`); App.jsx:164 stores failures as content with a copy guard that only excludes empty/`'Generating...'`; `save_voice_profile` destructively overwrites with no history. `external:` TSPA handling-time methodology — reduction claims need instrumented before/after measurement.
**Rationale:** The 30→5 claim is speculative today because only one side of it is even measurable. The DB produces the "after"; the "before" is a counterfactual that must be measured with humans. Claim structure once both exist: "median hands-on time per multi-channel set: ~X min manual (timed baseline, n=4) → ~Y min with the agent (instrumented, all real usage)." Until then, phrase as "significantly reduced" — a specific unmeasured number is the weakest form of the claim. Caveat to decide: in-tool time excludes post-copy work per platform; claim "creation time" (fine as-is) or "end-to-end" (needs idea 7 or self-reported session end).
**Downsides:** Invisible work; no demo value; baseline sessions need ~an afternoon of team time.
**Confidence:** 90%
**Complexity:** Low
**Status:** Explored (brainstormed 2026-07-22, with flag taxonomy design)

### 2. Make the evaluator act: score-gate + auto-repair + cache admission control
**Description:** Below-threshold generations get one auto-repair pass feeding the evaluator's own `suggestion` strings back as corrective instructions; sub-threshold output is never cached (today a 12/100 generation is cached and re-served until the voice version bumps); eval score + failing criteria are returned to the UI.
**Warrant:** `direct:` server.py:368–383 computes the score, gates nothing, caches unconditionally (`cache_set(cache_key, platform, text, score)`); `evaluators.py` emits imperative fixes ("Trim ~140 chars.") that no code reads.
**Rationale:** Cheapest path from "eval exists" to "eval reduces review burden" — the deterministic tier of the production cascade, built from code that already exists.
**Downsides:** Repair passes add latency; thresholds need per-channel tuning.
**Confidence:** 85%
**Complexity:** Low-Medium
**Status:** Unexplored

### 3. Multi-model LLM judge tier: judge ≠ generator, safety included
**Description:** Tiered cascade — heuristics always; flash-tier LLM judge (G-Eval chain-of-thought before scoring, position-randomized) on flagged or novel content; human for the residue. Hard invariant: the judge never grades its own generator's output (cross-provider judging via the existing fan-out plumbing). Add safety/brand criteria (claims, PII, banned terms, platform policy) — zero exist today. Persist judge verdict + judge identity as the audit record.
**Warrant:** `direct:` providers.py uniform 4-provider interface + in-repo `PRICING` showing the 40–50× cost spread that justifies tiering; evaluators.py contains no safety criteria. `external:` documented judge self-preference bias; flash judges ≈1/30 frontier cost.
**Rationale:** This is the literal noun phrase in the target claim — "multi-model LLM evaluation framework grading quality and safety" — and today it is 0% built.
**Downsides:** Per-generation cost and 1–2s latency; judge needs calibration (see idea 5).
**Confidence:** 80%
**Complexity:** Medium
**Status:** Unexplored

### 4. Explicit HITL workflow: approve/edit/reject + confidence-gated routing + spot-checks
**Description:** Replace copy-as-approval with explicit approve / edit-then-approve / reject-with-reason events and a draft→approved state machine. Confidence-gated routing: passing content renders collapsed (pre-approved, one click), flagged content renders expanded with failing criteria highlighted; a random spot-check fraction of auto-approved items stays expanded to counter rubber-stamping. Where feasible, present channel variants as diffs from the base input rather than six cold reads.
**Warrant:** `direct:` feedback_db.py docstring — "copied (= approved)" — and no rejections table; `/api/gemini` strips `eval_score` from its response. `external:` vigilance-decrement literature; QUEST review-value routing.
**Rationale:** The 83% cut comes from not reviewing the routine 80%, not from reading faster — this is the mechanism that makes the number honest, and reject-reasons are the negative labels the judge needs.
**Downsides:** Biggest UX change; auto-approve thresholds and spot-check rate are a risk-tolerance decision the owner must make.
**Confidence:** 85%
**Complexity:** Medium
**Status:** Unexplored

### 5. Calibration data flywheel: mine edit-diffs + compare preference pairs
**Description:** Compute the generated-vs-final diff on every edited copy (verified: already stored, never joined); log every copy-after-compare as a (chosen, rejected×3) preference tuple; cluster recurring corrections into proposed prompt/rubric amendments. The ≈500-label judge calibration set accumulates as a side effect of normal use; later payoff — per-channel model win rates drive model routing.
**Warrant:** `direct:` App.jsx:367 `onContentChange` → edited content flows into `copies.final_content` with `generation_id`; `/api/compare` logs all 4 providers' outputs with joinable generation_ids. `external:` Braintrust/LangSmith human-correction capture; LMSYS arena pairwise-preference pattern.
**Rationale:** Turns daily use into the dataset that makes the eval framework credible instead of vibes-based.
**Downsides:** Depends on idea 1 (model column + lineage fix) landing first.
**Confidence:** 85%
**Complexity:** Low-Medium
**Status:** Unexplored

### 6. One rubric per channel, as data — and language-fair
**Description:** Add an `## Eval Rubric` section to each `docs/<channel>.md` (parsed exactly like `## AI Prompt`) that compiles into both the generation prompt's constraint block and the evaluator/judge criteria, killing prompt↔evaluator drift. Make criteria language-aware: normalize length thresholds and keyword lists for Korean (prompts mandate language matching; docs note Korean compresses ≈2.5×).
**Warrant:** `direct:` docs/kakaotalk.md mandates 50–150 chars but `KakaotalkEvaluator` has no length criterion; evaluators.py:441–454 tone keyword lists are 100% English while LinkedIn's length criterion zeroes out below 600 chars — a well-formed Korean post loses up to ~50 points by construction. `external:` "weak judge on a great rubric outperforms a great judge on a weak rubric"; HealthBench hierarchical sub-rubrics.
**Rationale:** Without this, ideas 2–4 systematically mis-route Korean content — the eval layer would increase review work for the home market. New channel = one file, forever.
**Downsides:** Requires deciding the rubric schema up front.
**Confidence:** 80%
**Complexity:** Medium
**Status:** Unexplored

### 7. Close the last mile: publish integration with provenance
**Description:** Replace clipboard hand-carry with Approve → Publish/Schedule against at least one real platform API (or a scheduler intermediary such as Buffer), attaching provenance metadata — model, prompt version, voice version, judge verdict, approver — per IAB/C2PA direction.
**Warrant:** `direct:` the product's terminal step is `navigator.clipboard.writeText`. `external:` IAB AI-transparency framework (Jan 2026), EU AI Act labeling, Meta third-party brand-safety verification; Copy.ai approval-gate pattern.
**Rationale:** "Communications system" and "upload the content" are not true while the last mile is a clipboard; also completes the audit trail with an approval event whose payload is what actually shipped.
**Downsides:** Platform API auth/app-review friction; highest external dependency.
**Confidence:** 70%
**Complexity:** Medium-High
**Status:** Unexplored

## Rejection Summary

| # | Idea | Reason Rejected |
|---|------|-----------------|
| 1 | Voice-loop "echo chamber by construction" | Refuted by code — App.jsx:367 edits do reach `final_content` |
| 2 | Brief-first two-stage generation architecture | High-cost rewrite; idea 4's diff-review captures most value — brainstorm variant |
| 3 | Campaign firehose (1,000 posts/day async queue) | Over-engineering at current volume; revisit at real scale |
| 4 | Multi-user identity / client review links | Real fork-in-the-road but beyond the stated end-state scope; flag, don't build |
| 5 | TIP-style vigilance probes (planted bad content) | Strong follow-on, premature until idea 4's queue exists |
| 6 | Replay harness for prompt edits | Valuable; mostly covered by adopting promptfoo within ideas 3/6 |
| 7 | Per-platform reroll + async generation | Real friction; supportive UX, not gap-closing — idea 4 backlog |
| 8 | Image upload placebo (bytes never reach the model) | Real trust bug — just fix (wire Gemini multimodal or remove upload); not a strategic idea |
| 9 | Kill compare grid / judge-picks-best | Folded into idea 3 |
| 10 | Chatbot-Arena per-channel model routing | Folded into idea 5 (later payoff) |
| 11 | Voice profile as flagship editable surface | Partially folded into idea 1 (versioning); rest deferred |
