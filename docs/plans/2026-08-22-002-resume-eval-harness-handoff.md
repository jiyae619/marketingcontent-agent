---
title: "handoff: Eval harness — resume after reboot"
type: handoff
status: blocked-on-environment
date: 2026-08-22
branch: feat/llm-judge-pipeline
pr: https://github.com/jiyae619/marketingcontent-agent/pull/3
---

# Resume point — eval harness

## Read this first

**The code is finished and committed. The machine could not run it.**

All six architecture gaps from the graphcheck are closed, every fix is unit-tested,
the working tree is clean. What is missing is a single successful end-to-end run,
which failed because this 8GB M3 was at 8% free memory with 13.4GB of swap consumed.
That is an environment problem, not a code problem — the same KakaoTalk generation
took 3s earlier the same day.

**Do not start new work until step 1 below passes.** Everything above it is
unit-verified only.

---

## Step 1 — prove it runs (do this first, ~5 min)

```bash
cd ~/dev/marketingcontent
python3 scripts/preflight.py          # must print PREFLIGHT OK with no ollama warning
```

If preflight warns `ollama unreachable`, the machine has not recovered. A 4B model
needs 3.3–4.2GB resident; with 8GB total there is very little headroom and the
generator/judge pair cannot co-reside (Ollama swaps between them).

Then one live generation through the real server:

```bash
python3 server.py &                   # port 8081, from API_PORT in .env
curl -s -X POST http://localhost:8081/api/gemini \
  -H "Content-Type: application/json" -H "x-app-password: $APP_PASSWORD" \
  -d '{"platform":"kakaotalk","messages":[{"content":"PKNIC 커리어 코칭 세션 — 박 코치, 2026년 8월 30일 토요일 2PM, Seattle Public Library"}]}'
```

**Pass criteria:** a `generation_id` comes back, and within ~60s that generation has a
`judge_results` row that reaches a terminal status:

```bash
sqlite3 testing/results/feedback.db \
  "select generation_id, judge_model, status, overall from judge_results order by id desc limit 3"
```

`status` should be `graded`, `abstained`, or `failed` — **not** `pending`. A `pending`
row that never resolves means the judge thread died; that is now visible rather than
silent, which is the point of the change.

KakaoTalk is the fastest channel (3s generation, ~3 sentence output). Use it for the
smoke test, not LinkedIn or Circle.

---

## Step 2 — push (blocked, needs you)

5 commits are unpushed. Two separate things broke mid-session:

```
gh:   The token in default is invalid   (BOTH jypknic and jiyae619)
curl: https://github.com returns 000    (DNS resolves, IP pings, TLS blocked)
```

```bash
gh auth login -h github.com
gh auth switch --user jiyae619        # jypknic has NO push access -> 403
git -c credential.helper='!gh auth git-credential' push origin feat/llm-judge-pipeline
```

PR #3 already exists; pushing updates it.

---

## What was done (9 commits, all on feat/llm-judge-pipeline)

```
20f0b53  fix(cache): a rejected generation stops being the cache entry
11733a4  fix(judge): gate on cost, not on quality
09befb0  fix(ui): poll the judge until it answers, not until 8s
7c4e0a5  fix(judge): claim the verdict row before judging, not after
5ea35f1  feat(eval): golden set with negative labels by construction
ee2efaf  docs: project rules + preflight
926416e  feat(models): swappable generators, local-only mode, judge abstention
f56c28e  fix(prompts): remove markdown rules that contradicted each other
2ab4ac7  fix(eval): score Korean output against Korean targets
```

### The three findings that mattered

1. **The eval harness was measuring itself, not the models.** Prompts asked for Korean
   lengths ~2.5x shorter than the scorers' English bands, and the three tone criteria
   were English keyword lists graded against Korean text. linkedin lost 30%+20% of its
   weight and scored exactly 50.0; circle lost 30%+25% and scored exactly 45.0. Fixed:
   bilingual bands selected by `is_korean()`. Same stored outputs re-scored 65.0 → 92.2
   (Gemini) and 64.6 → 90.9 (gemma3:4b).

2. **45 of 49 eligible generations were never judged, silently.** The judge ran in a
   `daemon=True` thread with no queue or retry; a daemon thread is killed without
   unwinding, so anything written only on the success path vanished. Fixed by claiming
   the `judge_results` row on dispatch with a `status` column.

3. **The escalation gate cannot work at any threshold.** Measured on the golden set,
   16 of 17 defective samples score above the *lowest clean* sample; at the shipped
   T=70 it caught 1 of 4 hallucinations. The heuristic never receives the brief, so
   grounding defects are invisible by construction. Fixed by gating on *cost* — a free
   local judge is never skipped. Known-bad reaching the judge: 6/17 → 17/17.

---

## Current state

| | |
|---|---|
| Branch | `feat/llm-judge-pipeline`, tree clean, 5 commits unpushed |
| Generator | `gemma3:4b` local, $0 |
| Judge | `llama3.2:3b` local, $0 — **different model, enforced** |
| Billing | `LOCAL_ONLY=true`; the 3 paid providers refuse outright |
| DB | 92 generations, 10 feedback_events, 4 judge_results |
| Golden set | 34 samples (17 clean / 17 defective), `testing/golden/golden_set_v1.json` (gitignored, rebuildable) |
| Human negatives | **0 rejects** — still the critical path |

### Verified

SIGKILL mid-judge leaves a recoverable `pending` row · 5 re-judges produce 1 row not 5 ·
reject releases the cache key and a replacement claims it · the gate never skips a free
judge (both provider paths, all 34 samples) · poller reaches every terminal state (6/6
simulated timelines) · 0 label violations across 17 defective samples · migration
preserved 92/10/4.

### NOT verified

- **The whole pipeline through the HTTP server.** Attempted, timed out on memory. This
  is step 1.
- **Anthropic / OpenAI / Gemini schema paths.** Wired but never executed — `LOCAL_ONLY`
  blocks paid calls by design. `claude-sonnet-4-6` may reject `output_config`;
  structured outputs are documented for Haiku 4.5 / Sonnet 5 / Opus 5.
- **UI states in a browser.** Logic tested against mocked responses only.
- `MAX_LOCAL_GB = 4.0` in preflight is a judgement call from one measurement, not a
  limit tested to failure.

---

## Next work, in order

1. **Step 1 above.** Nothing else counts until one live run passes.
2. **Label 10–15 real generations** against `docs/labeling-guideline.md`. Path A
   negatives are the last input Stage 1 needs. Note the cache fix in `20f0b53` matters
   here: rejecting now releases the cache key, so you will not be handed the rejected
   post back. That gap was dormant only because there were 0 rejects.
3. **Run Stage 1** — judge meta-eval against the golden set. Free, local. It answers
   whether `llama3.2:3b` is usable: it returned **79, 80, 80 and 100 on identical
   input**, and passed a post containing an invented `가격: (정보 없음)` row as safe.
   Expect the answer to be no; the value is having measured it.
4. **Fill three empty golden-set cells** — `kakaotalk/en`, `whatsapp/ko`, `x/ko` have
   zero bases. Do this *before* the set becomes a baseline, since filling them changes
   the frozen sample ids.

Deliberately **not** started: the auto-revise loop (agreed K=5). Iterating against a
metric you cannot yet trust would optimise noise.

---

## Gotchas that cost time this session

- **`.env` has fallbacks that hide what actually runs.** Never describe the config from
  `.env` — run `scripts/preflight.py` and read the *resolved* values. This is rule 1 in
  `CLAUDE.md` and it exists because a silent `LOCAL_JUDGE_MODEL` → `LOCAL_LLM_MODEL`
  fallback made a model grade its own output.
- **Never hand-type `generator_model` when calling `judge.judge()`.** A false value
  defeats the `judge != generator` guard. Pass the real one.
- **`qwen3:4b` is a reasoning model** — 357s for one post, times out at 120s as a judge.
  Do not use it. `gemma3:4b` generates, `llama3.2:3b` judges.
- **`server.py:570` still gates `/api/gemini` on `GEMINI_API_KEY`** even under
  `LOCAL_ONLY`. The key is set so it does not block today, but it is inconsistent.
- **`/api/generator/models` reports `default: "gemini-flash"`** which is not in the
  list under `LOCAL_ONLY`. Resolution falls through to local correctly, but the UI
  dropdown may show nothing selected. Minor, unfixed.
- **`tools/abstention-checker/`** is untracked and dated Aug 15 — not from this
  session's work, deliberately left unstaged.

## Reference

- Architecture review + flow diagram: `~/dev/documents/html-previews/marketing-agent-pipeline-flow.html`
- Current status: `~/dev/documents/html-previews/marketing-agent-status.html`
- Channel rule conflicts: `~/dev/documents/html-previews/marketing-agent-channel-rule-conflicts.html`
- Harness design (v2): `~/dev/documents/html-previews/marketing-agent-eval-harness-orchestration.html`
