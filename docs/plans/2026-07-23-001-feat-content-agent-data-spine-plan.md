---
title: "feat: Content Agent Data-Integrity + Instrumentation Spine"
type: feat
status: completed
date: 2026-07-23
origin: docs/brainstorms/2026-07-22-content-agent-data-spine-requirements.md
---

# feat: Content Agent Data-Integrity + Instrumentation Spine

## Summary

Add the data-layer substrate the marketing content agent needs before the HITL review UI, LLM judge, and dashboard exist: an idempotent SQLite migration path, generation provenance, a cache-lineage fix, a unified approve/edit/reject feedback-event stream carrying a shared flag taxonomy, versioned voice profiles, and per-session hands-on-time instrumentation — validated by a stdlib write-path fixture. No UI. The data captured this phase is a clean, attributed substrate: approve vs. edit is derived server-side as a **proxy** signal (a copy fires on click intent, not explicit endorsement), and the flag/reject columns are schema that stays empty until the idea #4 UI writes to them. The value is the substrate being correct and complete before first real use — not a rich labeled corpus on day one.

---

## Problem Frame

The substrate under today's agent silently loses or corrupts the data a production eval-and-learning system depends on: cache-hit responses return no `generation_id` (orphaned approvals), generations record no model/prompt/voice provenance, the feedback path accepts any string (error text can poison voice training), and voice profiles are overwritten in place. The efficiency claim is unmeasurable because nothing computes the time already in the DB. This is the moment to fix it — the team has not yet used the agent for real, so data captured from first use is clean or lossy depending on these decisions. Full context in origin (see Sources & References).

---

## Requirements

- R1. Every draft surfaced to a human carries a stable lineage id back to its generation — including cache-hit responses.
- R2. The feedback path rejects input that is not genuine content (error strings, empty, placeholder) so it cannot enter voice training.
- R3. Every generation records model, prompt version, and voice version.
- R4. Voice profiles are versioned rather than overwritten, so any synthesis can be inspected and rolled back.
- R5. Human feedback is a unified verdict-event stream (approve/edit/reject) linked to its generation.
- R6. A verdict may optionally carry one flag: a category plus its family.
- R7. The v1 flag taxonomy is fixed but extensible — four categories in two families (grounding: hallucination, irrelevant/off-brief; voice: AI slop, KR-EN register) — as one shared source of truth for human flags now and judge criteria later.
- R8. Edit verdicts capture both generated and human-final text so the correction diff is derivable.
- R9. Per-session hands-on time (first generation → final approval) is computed from stored timestamps and surfaced in admin stats.
- R10. A documented manual "before" baseline exists (3–5 timed manual sessions, median recorded).
- R11. A thin write-path fixture exercises the full feedback-event model (each verdict, flagged and unflagged) before real use.

**Origin flows:** F1 (data lifecycle: generation → verdict → learning/measurement)
**Origin acceptance examples:** AE1 (covers R1), AE2 (covers R2), AE3 (covers R5/R6/R8), AE4 (covers R3), AE5 (covers R9)

---

## Scope Boundaries

- No approve/edit/reject/flag UI, no reject-verdict wiring in the live app (idea #4, next phase) — the model and endpoints support all three verdicts; only approve/edit are exercised by the current UI.
- No LLM judge, no eval dashboard (idea #3, next phase). R7's taxonomy is the shared vocabulary the judge will import; the judge is not built here.
- No language-aware rubric implementation (idea #6). The KR-EN register category exists in the taxonomy; scoring it comes later.
- No scheduling/publish integration (idea #7). No finetuning. No grounding fix (structured input / RAG).
- No golden-set regression gating and no rollback/promotion pointer on voice profiles — append-only versioning (inspect prior syntheses) only. The rollback pointer and gating are deferred to when an admin surface exists to drive them.

### Deferred to Follow-Up Work

- Drop the legacy `copies` table: superseded by `feedback_events` this phase (backfilled, reads repointed, writes stopped), but physically retained to avoid data-loss risk. Removal is a later cleanup once `feedback_events` is proven in real use.
- Drop the legacy `generation_cache` table: superseded by `generations.cache_key` in U2 (no longer read or written), physically retained for now; removal is later cleanup.
- Client-issued session id for precise session bounds: this phase derives sessions from timestamps (no client change); an explicit session id is a later refinement if inactivity-gap bounds prove too coarse.

---

## Context & Research

### Relevant Code and Patterns

- `feedback_db.py` — single `SCHEMA` string executed via `executescript` in `init_db()`; every table is `CREATE TABLE IF NOT EXISTS`. Write functions use keyword-only args; all access goes through the `_connect()` contextmanager (auto-commit, `sqlite3.Row` factory); reads return `dict(row)`; upserts use `ON CONFLICT(...) DO UPDATE SET col = excluded.col`. `DB_PATH` honors `FEEDBACK_DB_PATH` env override.
- `server.py` — hand-rolled `ThreadingHTTPServer`; routes matched by `self.path` string; JSON via `self._json(status, body)`; bracketed-tag `print` logging. Key handlers: `/api/gemini` (cache check → generate → `run_eval` → `log_generation` → `cache_set`; cache-hit branch returns content with no `generation_id`), `/api/compare` (thread-pool fan-out over `providers.COMPARE_MODELS`; logs each provider via `log_generation`, already has `r['model']`), `/api/copies` (validation only checks platform + non-empty; calls `log_copy`; spawns voice-synthesis daemon thread), `/api/admin/stats` (pass-through to `stats_by_platform()`).
- `_with_voice_examples()` / `_maybe_synthesize_voice()` — inject `get_voice_profile()` else `recent_copies()` few-shots; synthesis saves via `save_voice_profile()` (destructive upsert on `platform` PK).
- `scripts/scores.py` — closest existing pattern for a standalone DB-touching script: calls `init_db()` then raw queries against `feedback_db.DB_PATH`. Reference for the write-path fixture's DB access shape.
- `providers.py` — uniform `call_*` result dict (`ok/text/model/tokens/cost/latency/error`); `COMPARE_MODELS` ordered `(key, model, fn)` tuples. `/api/gemini` currently hardcodes `gemini-2.5-flash`.

### Institutional Learnings

- `docs/solutions/` does not exist yet — no prior learnings. This spine (single-file SQLite migration strategy, verdict-event model, voice versioning) is a strong `/ce-compound` capture candidate once it lands.

### External References

- None needed — the change follows established local stdlib/SQLite patterns; no external research warranted.

---

## Key Technical Decisions

- **Idempotent additive migration in `init_db()`:** after `executescript(SCHEMA)`, run a `_migrate()` helper that checks `PRAGMA table_info(...)` and issues `ALTER TABLE ... ADD COLUMN` for missing columns, plus a backfill guarded by a **persisted marker** (a `schema_meta` key/value row recording that the `copies`→`feedback_events` backfill ran). Rationale: `CREATE TABLE IF NOT EXISTS` cannot add columns to an existing table, and the gitignored `feedback.db` persists across runs. A marker is mandatory over an emptiness check — once live `feedback_events` rows exist, an emptiness guard would skip an un-run or partially-completed backfill. To serialize concurrent startups (dev server + `scripts/scores.py`), `_migrate()` runs under `BEGIN IMMEDIATE` with a `busy_timeout` and tolerates a duplicate-column error defensively. This preserves data and matches the origin's "avoid a migration under load" intent — chosen over resetting the DB.
- **Cache merged into `generations`, not a separate content table.** A nullable, unique `cache_key` column on the generation row replaces the `generation_cache` table: a cache hit returns an existing generation, so lineage is *structural* — an approval can never be orphaned — and content/eval live once instead of being duplicated across two tables. Chosen over patching the old two-table design (which duplicated content and needed a frontend stale-id guard); it is both simpler (one table, one lookup) and correct by construction. The `generation_cache` table is left unused (drop deferred, like `copies`). Tradeoff: the cache and the generation log now share one lifecycle (no independent cache expiry) — a non-issue for an internal tool at this volume (YAGNI).
- **prompt_version = content hash of the extracted `## AI Prompt` channel template** (sha256, truncated to ~12 hex), computed on the string `load_prompt_from_md` returns **before** `_with_voice_examples` injects voice. Rationale: deterministic, no git dependency. It identifies the *channel template version*, deliberately excluding per-user voice injection (separately tracked by `voice_version`). It is **not** a fingerprint of the full shaped prompt — reconstructing the real model input needs `prompt_version` + `voice_version` + input together.
- **Voice profiles: append-only versioned rows; latest row is active.** Rationale: append-only satisfies R4's "inspect any prior synthesis"; `get_voice_profile` reads the most recent row (latest = active), so no active-pointer column or rollback function is built this phase — both are premature with zero real voice data and no admin surface to drive a rollback. A rollback/promotion pointer is a one-column, one-line follow-up when the admin UI or golden-set gating lands (noted in U4). Golden-set gating explicitly out.
- **Voice-profile versioning uses a new table, not an `ALTER` of `voice_profiles`.** Rationale: the change from `platform`-PK to versioned `(platform, version)` rows is a PRIMARY KEY reshape, which SQLite cannot do via `ALTER TABLE`. A new `voice_profile_versions` table is created via `CREATE TABLE IF NOT EXISTS` in `SCHEMA`; the live `voice_profiles` table is empty today, so there is no data to migrate — the old table is left unused.
- **Unified `feedback_events` table as canonical; `copies` backfilled and superseded — and every `copies` reader repointed.** Rationale: origin Key Decision — one stream for all downstream consumers. Because writes to `copies` stop, **all** readers of `copies` must move to `feedback_events`, not just `recent_copies`: `copy_count()` (which drives the voice-synthesis trigger in `_maybe_synthesize_voice` and the staleness rule in `get_voice_profile`) and the raw `FROM copies` subquery in `scripts/scores.py`. Missing these freezes the voice-synthesis counter (synthesis silently stalls) and desyncs the scores dashboard. See U4.
- **Backfill of unresolvable `copies` rows.** The live DB's existing `copies` rows carry `generation_id`s that do not resolve to a `generations` row (NULL, or dangling ids far above the current max). During backfill, `original_content` is filled by `LEFT JOIN` to `generations` and left NULL when unresolvable (the column is nullable), and `feedback_events.generation_id` is set NULL when it doesn't resolve — so the FK is honest even if `PRAGMA foreign_keys` is later enabled. Backfilled rows are recorded as `verdict='approve'`.
- **Server-side approve/edit classification now, no UI needed — a normalized string comparison.** The copy handler looks up the generation by `generation_id`, and after validating the generation's `platform` matches the request `platform` (400 on mismatch/non-existent), compares `generated_content` to `final_content` after normalizing trailing whitespace/line-endings; equal → `verdict='approve'`, else → `verdict='edit'` (storing both texts). Rationale: yields a real approve/edit **proxy** and genuine in-app edit diffs from day one — but "approve" means "copied without in-app edit," not explicit endorsement, and diffs only capture edits made in the textarea before copying. Reject and flag capture wait for the idea #4 UI.
- **Flag taxonomy as one shared constant** (category → family map) in the backend, imported by the feedback validation now and the judge later. Rationale: origin Key Decision — one vocabulary so each future human flag is a calibration label for the exact future judge criterion. Four flat categories, extensible by adding allowed values without migration. Note: no live caller writes a flag this phase (the UI is deferred), so the `flag_category`/`flag_family` columns stay NULL until idea #4 — this phase ships the columns and the validated constant, not flag data.
- **Session = inactivity-gap bucketing over existing timestamps, cross-platform, computed in Python.** Rationale: honors the no-UI boundary (no client session id); groups a multi-channel batch into one session; hands-on time = last **approve** verdict − first generation within a session. The gap threshold ships as a **provisional named config default**, not tuned from current timestamps (which are dev/test noise, not real sessions) — it is revisited once real usage accrues.
- **Write-path fixture = stdlib `assert` script; `FEEDBACK_DB_PATH` must be set before process start.** Rationale: the repo declares zero Python deps and leans stdlib; a dependency-free script matches convention. `pytest` considered but rejected as heavier footprint with nowhere to declare it. Critical: `feedback_db.DB_PATH` binds `FEEDBACK_DB_PATH` at import time, so the fixture cannot set the env var in-process — it asserts the var is set to a non-default temp path at startup and refuses to run otherwise, so it can never write into the real `testing/results/feedback.db`.

---

## Open Questions

### Resolved During Planning

- Prompt-version identity (origin deferred): content hash of the extracted prompt slice — see Key Technical Decisions.
- Voice-versioning shape (origin deferred): append-only rows + active pointer; golden-set gating deferred.
- Session delimiting (origin deferred): inactivity-gap sessionization over stored timestamps, cross-platform, in Python.
- Grounding sub-distinctions (origin deferred): no — four flat categories + family tag, extensible via allowed values without migration.
- Write-path validation form (origin deferred): stdlib assert script with `FEEDBACK_DB_PATH` temp override.

### Deferred to Implementation

- `PRAGMA foreign_keys` posture: keep FKs declarative this phase (backfill already NULLs unresolvable `generation_id`s so the data would pass a check if it were ever enabled). Enabling `foreign_keys=ON` in `_connect()` is a later hardening step.
- Precise provisional inactivity-gap default — pick a reasonable value (e.g., ~20–30 min) as a named constant; explicitly not fitted to current dev/test timestamps; revisit after real usage.
- Whether `recent_copies` is renamed vs. kept as a thin wrapper when repointed — naming decided at implementation to minimize call-site churn.

### Deferred to Follow-Up (broader validation)

- Minimum-substance / refusal-and-truncation heuristic on feedback input, and guarding the generation-write path (not just the copy path): this phase blocks only the known sentinel strings; model refusals ("I cannot help with that") and truncated stubs are the more likely real-world poison and are a later hardening step.
- The manual baseline (U7) may need re-capture close to when the instrumented cohort has enough sessions, so a team learning-curve doesn't confound the before/after comparison.

---

## Implementation Units

- U1. **Migration scaffolding + generation provenance**

**Goal:** Establish the idempotent migration path and add `model`, `prompt_version`, `voice_version` to `generations`, populated at both generation call sites.

**Requirements:** R3

**Dependencies:** None

**Files:**
- Modify: `feedback_db.py` (add a `schema_meta` key/value table to `SCHEMA` for migration/backfill markers; add `_migrate()` and call it from `init_db()` after `executescript`; extend `generations` schema with `model`, `prompt_version`, `voice_version`, and `cache_key` + a unique index on `cache_key`; extend `log_generation` signature/INSERT)
- Modify: `server.py` (`/api/gemini` passes `model='gemini-2.5-flash'`, computed prompt hash, existing `v_ver`, and the cache key; `/api/compare` passes `r['model']`, prompt hash, `v_ver` (no cache key — compare isn't cached); add a small prompt-hash helper)
- Test: covered by `scripts/test_feedback_db.py` (U6)

**Note:** U1 establishes the migration scaffolding (`schema_meta` marker table + `_migrate()` skeleton under `BEGIN IMMEDIATE`) and all new `generations` columns (provenance + `cache_key`) that U2's cache rewiring and U3's backfill build on.

**Approach:**
- `_migrate()` reads `PRAGMA table_info(generations)`; for each missing column (`model`, `prompt_version`, `voice_version`, `cache_key`), runs `ALTER TABLE generations ADD COLUMN ...` (nullable, no default → no NOT-NULL trap), then `CREATE UNIQUE INDEX IF NOT EXISTS` on `generations(cache_key)`. SQLite treats NULLs as distinct in a unique index, so the many un-cached rows (all `/api/compare` rows, legacy rows) coexist with NULL `cache_key` freely. Idempotent; runs under `BEGIN IMMEDIATE` + `busy_timeout` and tolerates a duplicate-column error so concurrent startups don't crash boot.
- Keep `log_generation` keyword-only; add `model=None, prompt_version=None, voice_version=None, cache_key=None`.
- Prompt hash is computed from the pre-injection channel-template string — the value `load_prompt_from_md(platform)` returns **before** `_with_voice_examples` runs (server.py `/api/gemini` ~lines 333–334; `/api/compare` ~lines 256–260). Do not hash the voice-injected or full prompt. It is a channel-template version, not a shaped-prompt fingerprint.
- `/api/gemini` currently hardcodes `gemini-2.5-flash` in the request URL separately from the model string it will now pass to `log_generation` — keep the two consistent.

**Patterns to follow:** `feedback_db.log_generation` keyword-only style; `make_cache_key` sha256 pattern for the prompt hash; `_connect()` for the migration.

**Test scenarios:**
- Happy path: `log_generation` with provenance persists all three fields; row reads back with correct model/prompt_version/voice_version.
- Covers AE4: two generations logged with different `model` values are each independently attributable.
- Edge case: `_migrate()` run twice in a row is a no-op the second time (columns already present, no error).
- Edge case: provenance args omitted → columns store NULL without error (back-compat).

**Verification:** A fresh DB and a pre-existing DB both end with the three columns present; new generations carry provenance; `/api/compare` rows are model-attributable.

---

- U2. **Merge the cache into `generations` (lineage by construction)**

**Goal:** Replace the separate content-cache with a `cache_key` on the generation row, so a cache hit returns a real generation (content + id + provenance) and an approval can never be orphaned — the bug becomes structurally impossible rather than patched.

**Requirements:** R1

**Dependencies:** U1 (adds the `cache_key` column + unique index)

**Files:**
- Modify: `feedback_db.py` (replace `cache_get`/`cache_set` with a single `generation_by_cache_key(key)` lookup returning the full generation row; stop reading/writing `generation_cache` — the table is left in place, unused, drop deferred)
- Modify: `server.py` (`/api/gemini` computes the key, looks up an existing generation by key; **hit** → return that generation's content + `generation_id` (+ `from_cache`); **miss** → `log_generation(..., cache_key=key)` and return content + `generation_id`)
- Test: `scripts/test_feedback_db.py` (U6)

**Approach:**
- **The generation row *is* the cache entry.** No separate content copy, no bolted-on lineage: a cache hit returns an existing `generations` row, so the `generation_id` is always present and content/eval are stored once. No `src/App.jsx` change is needed — cache hits now always carry a real id, so the stale-id hazard from the old two-table design disappears entirely.
- Lookup-before-insert; on the rare concurrent-insert race, the unique index on `cache_key` plus `INSERT ... ON CONFLICT(cache_key) DO NOTHING` (then re-select) keeps it safe.
- Only `/api/gemini` sets a `cache_key`; `/api/compare`'s four rows have NULL `cache_key` (not cached) and don't collide (NULLs are distinct in a SQLite unique index).
- `voice_version` stays in the key, so a copy still invalidates: a bumped `voice_version` yields a new key → miss → fresh generation. Behavior identical to today, minus the duplicated content table.

**Patterns to follow:** `_connect()` + `dict(row)` return; unique index mirrors the existing `idx_*` indexes.

**Test scenarios:**
- Covers AE1: two identical requests (same key) → the second is a hit returning the first generation's id and content; a copy against it links (non-NULL `generation_id`).
- Happy path: a miss inserts a generation with `cache_key` set and full provenance present.
- Edge case: a request whose `voice_version` changed → different key → miss → new generation (cache correctly invalidated).
- Edge case: multiple `/api/compare` rows with NULL `cache_key` coexist without violating the unique index.

**Verification:** Cache hits return a real generation (content + id); no orphaned approvals are possible by construction; `generation_cache` is no longer read or written.

---

- U3. **Unified feedback-event stream + flag taxonomy + validation**

**Goal:** Introduce `feedback_events` as the canonical verdict stream, a shared flag-taxonomy constant, feedback-input validation, and server-side approve/edit classification.

**Requirements:** R2, R5, R6, R7, R8

**Dependencies:** U1

**Files:**
- Modify: `feedback_db.py` (add `feedback_events` table to `SCHEMA`; `FLAG_TAXONOMY` constant {category → family}; `log_feedback(...)` write fn; validation helper; one-time `copies`→`feedback_events` backfill in `_migrate()`)
- Modify: `server.py` (`/api/copies` validates input, looks up the generation, classifies approve vs edit by comparing `generated_content` to `final_content`, calls `log_feedback` with both texts + optional flag, still bumps voice version)
- Test: `scripts/test_feedback_db.py` (U6)

**Approach:**
- `feedback_events`: `id`, `generation_id` (FK, nullable), `platform`, `verdict` (approve|edit|reject), `flag_category` (nullable), `flag_family` (nullable), `original_content` (generation text at verdict time, nullable), `final_content` (nullable for reject), `created_at`.
- `FLAG_TAXONOMY` is the single source of truth: `{"hallucination":"grounding","irrelevant":"grounding","ai_slop":"voice","kr_en_register":"voice"}`. `log_feedback` validates any provided flag against it (unknown category → raise) and derives family. The future judge imports the same constant. No live caller sends a flag this phase; these columns stay NULL until the idea #4 UI.
- Validation helper rejects empty/whitespace, an `Error:` prefix, and the `Generating...` placeholder → handler returns 400; `log_feedback` also guards (raises) so the fixture can test the guard directly. Note the claim scope: this blocks the known sentinel strings; it does **not** catch model refusals or truncated stubs (a broader minimum-substance heuristic and guarding the generation-write path are deferred — see Open Questions).
- `/api/copies` looks up the generation by the client-supplied `generation_id` and **asserts the generation's `platform` matches the request `platform`** before classifying; a mismatched or non-existent id returns 400 rather than silently cross-linking feedback to the wrong generation (protects R8 diff integrity, and matters in the shared-password multi-operator case).
- Classification: normalize trailing whitespace/line-endings on both sides, then approve when `final_content` equals the generation's `generated_content`, edit otherwise (store both). Normalizing prevents a trailing-newline artifact from being logged as a spurious "edit" that pollutes the diff corpus.
- Reject is supported by the model but not emitted by the current UI. **Reject does not bump `voice_version`** — only approve/edit do, since only they yield content the voice loop should learn from.
- Backfill (in `_migrate()`, marker-guarded): migrate existing `copies` into `feedback_events` as `verdict='approve'`; `original_content` via `LEFT JOIN generations` (NULL when the copy's `generation_id` doesn't resolve — true of every current row); `generation_id` set NULL when unresolvable.

**Technical design:** *(directional guidance, not implementation spec)*

    log_feedback(*, generation_id, platform, verdict,
                 original_content=None, final_content=None,
                 flag_category=None, flag_family=None) -> int
      validate verdict in {approve, edit, reject}
      if flag_category: assert flag_category in FLAG_TAXONOMY; derive family
      validate final_content (when present) is genuine content (else raise)
      INSERT feedback_events(...)
      if verdict in {approve, edit}: bump voice_version(platform)   # reject never bumps

**Patterns to follow:** keyword-only write fn; `ON CONFLICT` upsert style for the voice-version bump (mirror current `log_copy`); `self._json(400, {...})` for handler rejections.

**Test scenarios:**
- Covers AE3: an edit verdict flagged `ai_slop` stores verdict=edit, flag_category=ai_slop, family=voice, both original and final text, linked to the generation.
- Covers AE2: `final_content` of `"Error: quota exceeded"` is rejected by the validation helper (and by `log_feedback`'s guard) and no event is written.
- Happy path: identical `final_content` and generation text → verdict=approve, no flag, voice version bumped.
- Edge case: `final_content` differing only by a trailing newline → normalized → verdict=approve, not edit.
- Happy path: reject verdict with a grounding flag (`hallucination`) writes an event with family=grounding and does **not** bump voice_version.
- Error path: `generation_id` whose generation.platform ≠ request platform → 400, no event written.
- Edge case: unknown flag category (`"foo"`) raises rather than silently storing.
- Edge case: empty / `"Generating..."` `final_content` rejected.
- Integration: backfill migrates existing `copies` into `feedback_events` as approve events; rows with unresolvable `generation_id` get NULL `generation_id` and NULL `original_content`; the persisted marker makes a second `_migrate()` run add nothing; a partially-completed backfill is completed on the next run (marker only set on completion).

**Verification:** All three verdicts persist; flags validate against the shared taxonomy; error/placeholder input never enters the stream; platform-mismatched `generation_id` is rejected; approve vs edit is classified from a normalized comparison with both texts retained on edits; backfill is marker-guarded and orphan-safe against the real DB shape.

---

- U4. **Repoint all `copies` readers to `feedback_events` + append-only versioned voice profiles**

**Goal:** Every consumer of the old `copies` table reads the new event stream, so stopping `copies` writes doesn't freeze the voice-synthesis counter; voice profiles become append-only versioned (inspectable) without destructive overwrite.

**Requirements:** R4

**Dependencies:** U3

**Files:**
- Modify: `feedback_db.py` — repoint **all** `copies` readers to approve+edit `feedback_events`: `recent_copies` (few-shot/synthesis source) **and** `copy_count()` (drives the staleness rule and the synthesis trigger). Add `voice_profile_versions` table to `SCHEMA`; `save_voice_profile` inserts the next version; `get_voice_profile` reads the latest row; `stats_by_platform`'s copies subquery counts `feedback_events`.
- Modify: `scripts/scores.py` — its raw `SELECT COUNT(*) FROM copies` subquery reads a table that stops growing; repoint it to `feedback_events` (approve+edit) or it silently undercounts.
- Modify: `server.py` — `_maybe_synthesize_voice` / `_with_voice_examples` behavior unchanged, but confirm they now sit on the repointed `copy_count`/`recent_copies` and the versioned save path.
- Test: `scripts/test_feedback_db.py` (U6)

**Approach:**
- **The load-bearing fix:** `copy_count()` today does `SELECT COUNT(*) FROM copies`; the staleness rule (`get_voice_profile`: `copy_count - based_on >= 3`) and the synthesis trigger (`_maybe_synthesize_voice`) both depend on it. If `copies` writes stop (U3) and `copy_count` is not repointed, the counter freezes and voice synthesis never re-fires. Repoint `copy_count` (and `based_on`, set from it in `save_voice_profile`) to count approve+edit `feedback_events`.
- Voice-profile versioning: a new `voice_profile_versions` table keyed by `(platform, version)`; `save_voice_profile` computes the next version and inserts (never overwrites); `get_voice_profile` returns the latest version's `style_text` (**latest = active** — no active-pointer column and no rollback function this phase; both are premature with no real voice data and no admin surface). Preserve the 3-new-events staleness rule via the repointed `copy_count`. Add a one-line TODO: a rollback/promotion pointer is a single ALTER + read-path change when the admin UI or golden-set gating lands.
- `recent_copies` (kept as a thin wrapper or renamed at implementation) selects the most recent approve+edit events' `final_content` — edits included, since an edited-then-approved post is the strongest voice signal.

**Patterns to follow:** `_connect()` + `dict(row)`; keep `get_voice_profile`'s staleness semantics intact but sourced from `feedback_events`.

**Test scenarios:**
- Integration (the regression guard): log N approve/edit events via `log_feedback` with **no** `copies` writes; assert `copy_count` reflects them and `get_voice_profile` returns None again at the 3-new-event boundary (synthesis re-triggers). This is the test that proves the counter didn't freeze.
- Happy path: two successive `save_voice_profile` calls produce versions 1 and 2; `get_voice_profile` returns version 2's text; version 1 remains inspectable (no destructive overwrite).
- Edge case: no profile yet → `get_voice_profile` returns None (staleness behavior preserved).
- Integration: after logging an approve and an edit event, `recent_copies` returns both `final_content` values ordered by recency.

**Verification:** Every `copies` reader (`recent_copies`, `copy_count`, `stats_by_platform`, `scripts/scores.py`) is on `feedback_events`; voice synthesis re-triggers after new events with `copies` writes stopped; voice profiles accumulate inspectable versions.

---

- U5. **Per-session hands-on time in admin stats**

**Goal:** Compute and surface per-session hands-on time from stored timestamps.

**Requirements:** R9

**Dependencies:** U3

**Files:**
- Modify: `feedback_db.py` (sessionization + hands-on-time function reading generation `created_at` and approval `created_at`/`copied_at`; extend or add alongside `stats_by_platform`)
- Modify: `server.py` (`/api/admin/stats` includes the session metric in its payload)
- Test: `scripts/test_feedback_db.py` (U6)

**Approach:**
- Approval timestamps come from `feedback_events` (`verdict='approve'`, `created_at`) post-U3, and generation timestamps from `generations.created_at`. "Final approval" is defined as **the last `approve` verdict in the session** (intervening edits/rejects do not end the session).
- Pull generation + approve events ordered by time (cross-platform), bucket into sessions by an inactivity gap, compute each completed session's `last_approve − first_generation`, and return per-session durations plus a median.
- Rules for messy data (the DB has ~67 generations vs. ~8 approvals): a session with generations but **no approve** is excluded from the median (no completion time); if a bucket's `last_approve < first_generation`, drop it. State these rules in code.
- The inactivity-gap threshold is a **named config constant with a provisional default** — not tuned from current timestamps (dev/test noise). Revisit after the first week of real usage.
- Compute in Python (clearer than window-function SQL for gap bucketing).

**Patterns to follow:** `stats_by_platform` return shape (list of dicts); `_connect()` read.

**Test scenarios:**
- Covers AE5: generation at T0 and a single approve at T1 within one session → reported hands-on time ≈ T1−T0.
- Edge case: two event clusters separated by more than the gap threshold → two sessions, not one.
- Edge case: a multi-platform approve burst within ~1s (real DB shape) plus its generations → counts as one session, not many.
- Edge case: a generation with no approve → excluded from the median; a `last_approve < first_generation` bucket → dropped.
- Happy path: median across several completed sessions is computed and returned in the stats payload.

**Verification:** `/api/admin/stats` returns per-session hands-on time and a median; a multi-channel batch counts as one session; incomplete sessions are excluded per the stated rule.

---

- U6. **Write-path validation fixture**

**Goal:** A dependency-free script that exercises the whole feedback data model before any real use.

**Requirements:** R11

**Dependencies:** U1, U2, U3, U4, U5

**Files:**
- Create: `scripts/test_feedback_db.py`

**Approach:**
- The script **requires `FEEDBACK_DB_PATH` to be set to a non-default temp path before process start** and refuses to run against the default `testing/results/feedback.db` — because `feedback_db.DB_PATH` binds the env var at import time, setting it in-process would be ignored and would corrupt the real DB. First lines: assert `os.environ.get("FEEDBACK_DB_PATH")` is set and not the default; abort with a clear message otherwise. Invoke as `FEEDBACK_DB_PATH=/tmp/x python3 scripts/test_feedback_db.py`.
- Then `init_db()` and drive: provenance logging + readback (U1); cache-as-generation lookup — a miss inserts a generation with the key, an identical second request is a hit returning that same generation id, and `/api/compare`-style NULL-`cache_key` rows coexist (U2); `log_feedback` for approve/edit/reject, flagged and unflagged, platform-mismatch rejection, normalized approve/edit, plus validation rejections (U3); append-only voice versioning + `copy_count`/`recent_copies` sourced from events incl. the synthesis-re-trigger regression guard (U4); sessionization / hands-on time on the real-shape burst (U5). Use stdlib `assert`; print a pass summary; non-zero exit on failure.
- Mirror `scripts/scores.py` for standalone DB access; no network, no live API.

**Patterns to follow:** `scripts/scores.py` init + query style; `feedback_db.py` `__main__` convention.

**Test scenarios:**
- This unit *is* the test harness. It must cover every AE (AE1–AE5) and each validation guard at least once, and exit non-zero if any assertion fails.
- Integration: full lifecycle in one run — generate (with provenance) → cache round-trip → approve + edit + reject events (flagged and unflagged) → voice synthesis version + rollback → session hands-on time — all against a throwaway temp DB.

**Verification:** Running `FEEDBACK_DB_PATH=/tmp/x python3 scripts/test_feedback_db.py` exits 0 on a correct build and non-zero if any part of the model regresses.

---

- U7. **Manual "before" baseline protocol (non-code)**

**Goal:** Document the timed manual-baseline protocol so the efficiency comparison has a defensible "before."

**Requirements:** R10

**Dependencies:** None (independent; can run in parallel with code)

**Files:**
- Create: `docs/baseline-protocol.md`

**Approach:**
- Short doc: 3–5 team members each write one multi-channel content set manually (no agent), timed start-to-finish; record each duration and the median; note conditions (channels covered, whether post-copy platform work is included) so it's comparable to the instrumented in-tool metric (U5). State that the claim is "creation time" (in-tool) unless publish work is separately timed.

**Patterns to follow:** existing `docs/*.md` prose style.

**Test scenarios:** Test expectation: none — documentation/process artifact, no behavioral change.

**Verification:** The doc exists, names the protocol and the recording location for the median, and defines the metric boundary so it lines up with U5's instrumented number.

---

## System-Wide Impact

- **Interaction graph:** `/api/copies` now validates input, asserts platform match, looks up the generation, and classifies approve/edit before writing; the voice-synthesis daemon thread now reads `feedback_events` via the repointed `copy_count`/`recent_copies`. `/api/gemini` and `/api/compare` gain provenance args. `/api/admin/stats` gains the session metric.
- **All `copies` readers must move together:** `recent_copies`, `copy_count()` (staleness rule + synthesis trigger), `stats_by_platform`'s copies subquery, and the raw `FROM copies` query in `scripts/scores.py`. Repointing only `recent_copies` (the obvious one) silently freezes the voice-synthesis counter — this is the review's highest-severity finding and is why U4 enumerates every reader.
- **Error propagation:** feedback validation and platform-mismatch surface as a 400 at the handler and a raised guard in `log_feedback`; both fail loudly rather than silently dropping — matching the repo's explicit-error convention.
- **State lifecycle risks:** the `copies`→`feedback_events` backfill is guarded by a **persisted marker** (not an emptiness check, which is unsafe once live rows exist) and completes a partially-run backfill on the next startup. `_migrate()` runs under `BEGIN IMMEDIATE` + `busy_timeout` to serialize concurrent starts, and a migration failure must not silently corrupt boot. Voice-profile versioning preserves the staleness rule via the repointed counter.
- **API surface parity:** the `/api/copies` request contract is unchanged (`platform`, `final_content`, optional `generation_id`). Merging the cache into `generations` (U2) means cache hits now always return a real `generation_id`, so **no frontend change is needed** — this is entirely a backend/data-model change.
- **Unchanged invariants:** channel prompt loading, voice-injection behavior, the 4-model compare fan-out, and the password gate are unchanged. Both the `copies` table (superseded by `feedback_events` in U4) and the `generation_cache` table (superseded by `generations.cache_key` in U2) are retained but have **no remaining readers**, so nothing reads stale data mid-migration.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `ALTER TABLE` migration runs against an existing persistent `feedback.db`, possibly under concurrent startups | Idempotent `PRAGMA table_info` guard before each nullable `ADD COLUMN`; `_migrate()` under `BEGIN IMMEDIATE` + `busy_timeout`, tolerating duplicate-column errors; run once against a copy of `testing/results/feedback.db` before shipping. |
| Backfill skips or duplicates rows on repeated/partial startups | Guard on a **persisted marker** (not an emptiness check); marker set only on completion so a crashed backfill resumes; U6 asserts second-run no-op and partial-resume completion. |
| Backfill can't populate `original_content` — live `copies` rows have unresolvable `generation_id`s | `LEFT JOIN generations`; NULL `original_content` and NULL `generation_id` when unresolvable (columns nullable); FK stays honest if `foreign_keys` is later enabled. |
| **Voice-synthesis counter freezes** when `copies` writes stop but `copy_count` still reads `copies` | Repoint **all** `copies` readers (`copy_count`, `recent_copies`, `stats_by_platform`, `scripts/scores.py`) to `feedback_events`; U4's regression test asserts synthesis re-triggers after new events. |
| Cache hit loses lineage (orphaned approval) | Merge the cache into `generations` (U2): a hit returns a real generation, so lineage is structural — orphaning is impossible by construction, no frontend guard needed. |
| Concurrent identical requests race to insert the same `cache_key` | Unique index on `cache_key` + lookup-before-insert with `ON CONFLICT DO NOTHING` then re-select; U2 covers it. |
| Approve/edit misclassification from whitespace/newline artifacts | Normalize trailing whitespace/line-endings before comparison; U3 test covers trailing-newline → approve. |
| Client-supplied `generation_id` cross-links feedback to the wrong generation | Assert `generation.platform == request.platform`; 400 on mismatch/non-existent; U3 error-path test. |
| Poisoned `final_content` flows into voice synthesis → injected into future system prompts | Named as a threat surface (see Documentation / Operational Notes); sentinel-string validation this phase; length cap / character-class filter on synthesized profile deferred with the note so the implementer doesn't skip it. |
| `voice_profiles` PK reshape attempted via `ALTER` | Use a new `voice_profile_versions` table via `CREATE TABLE IF NOT EXISTS`; live table empty, no data migration. |
| Session inactivity threshold mis-buckets real sessions / tuned against dev noise | Named config constant with a provisional default, revisited after real usage; U5 tests same-session, split-session, and the real-shape approve burst. |

---

## Documentation / Operational Notes

- The persistent local `feedback.db` is gitignored; the migration is additive, but note in the PR that first startup after this change alters `generations` (adds provenance + `cache_key` columns and a unique index), adds `feedback_events` + `voice_profile_versions` + `schema_meta`, retires `generation_cache` (left unused), and backfills `feedback_events`. Run the migration once against a copy of the real DB before shipping.
- **Threat surface to name in the PR:** `final_content` feeds voice synthesis, whose output is injected into every future system prompt (`_with_voice_examples`). A legitimate-looking but adversarial feedback string is an indirect prompt-injection vector that the sentinel-string validation does not catch. Mitigations to weigh (length cap + character-class filter on the synthesized profile before injection; logging the synthesized profile at write time for anomaly detection) are deferred but must not be silently skipped.
- `/api/admin/stats` is intentionally unauthenticated (localhost-only) and now also surfaces session-timing data. This is an accepted tradeoff for a localhost internal tool; if the server is ever exposed beyond localhost, add it to the password gate — cheap to note now, expensive to retrofit.
- Strong `/ce-compound` capture candidate once landed: the single-file SQLite migration strategy, the verdict-event model, and voice versioning are durable, reusable learnings (`docs/solutions/` does not exist yet).

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-07-22-content-agent-data-spine-requirements.md](docs/brainstorms/2026-07-22-content-agent-data-spine-requirements.md)
- Upstream ideation: `docs/ideation/2026-07-22-gap-analysis-production-hitl-eval-ideation.md`
- Core code: `feedback_db.py`, `server.py`, `providers.py`, `scripts/scores.py`, `testing/core/evaluators.py`, `src/App.jsx`, `src/components/ModelCompare/ModelCompare.jsx`
