# bughunt

Detects bugs with code, fixes them with agents, and keeps only the fixes that verify.

```bash
python3 tools/bughunt/bughunt.py                 # detect only — changes nothing
python3 tools/bughunt/bughunt.py --fix           # fix on a scratch branch
python3 tools/bughunt/bughunt.py --fix --loop 3  # keep going while it improves
python3 tools/bughunt/bughunt.py --review        # + agent hunt for logic bugs in the diff
```

Writes `tools/bughunt/report.md`. Exits non-zero if any check fails, so it works as a
pre-push hook or a CI step.

## Two tiers, and why they are separate

**`detectors.py` — facts.** Runs commands, asserts invariants, reports pass/fail with the
output that produced it. No model is involved, so a detect-only run costs nothing and
cannot invent a finding.

**Agents — judgment.** They only ever see what the detectors already proved is broken.
The one exception is `--review`, which hunts logic bugs in a diff, because "is this code
wrong" is not decidable by running a command.

That split is CLAUDE.md rule 5. Wiring an agent into `npm run build` would be using a
language model for routing, which the rule exists to prevent.

## What it checks

| id | what it proves |
|---|---|
| `env.preflight` | the resolved config obeys the hard constraints (`scripts/preflight.py`) |
| `build.clean_clone` | the repo builds from a pristine clone **with no `.env`** |
| `data.feedback_db` | the 25-check write-path fixture passes |
| `judge.abstention_contract` | an abstained verdict does not also carry a score |
| `judge.stuck_rows` | no `judge_results` stuck at `pending`, no abstained row with an `overall` |
| `eval.gate_metrics` | golden-set numbers have not silently moved since the baseline |
| `env.eslint` | lint is clean |

`build.clean_clone` exists because of a specific 19-day miss: `vite.config.js` threw on a
missing `API_PORT`, but that value only feeds the dev-server proxy. `npm run build` passed
locally, where `.env` is present and gitignored, and failed in every clean environment.
Nothing ever built the repo as a stranger, so the Netlify deploy stayed red and nobody
noticed. This check builds it as a stranger.

`judge.abstention_contract` swaps `providers.call_local` for a canned response, so it makes
no model call. It loads `.env` and pins `LOCAL_ONLY=true` first — a bare `python3 -c` does
not load `.env`, and `resolve_judge` then falls through the local entry to the first *cloud*
one. The first draft of that probe resolved to `claude-sonnet-4-6` and was saved from a paid
call only by a missing API key. It also stubs the paid provider functions to raise, so the
detector cannot be the thing that reaches a paid API.

It probes **both** routes into abstention — no source brief, and the model self-reporting
`confidence: "low"` — not just one. The first version probed only the no-brief route; an
agent's first fix nulled the score inside that branch alone, the single-route check went
green, and the low-confidence route still shipped `abstained=true` alongside `overall=80`.
A contract test has to cover every path in, or a partial fix reads as complete.

## The gate

A patch is kept only if a full re-run comes back **strictly greener**:

- at least one previously-failing check now passes, **and**
- not a single previously-passing check now fails.

Anything else is reverted and recorded as a failed attempt. The agent does not grade its own
work — the detectors do. This is the entire safety argument for letting an agent edit code
unattended.

## Rails

- **Never runs `--fix` on `main`/`master`.** Refuses outright.
- **Never pushes.** Fixes land on a local `bughunt/<timestamp>` branch for you to review.
- **Refuses to start with a dirty tree** unless `--allow-dirty`, so a reverted fix cannot
  take your uncommitted work with it.
- **Stages with `git add -u`, never `-A`** — only files git already tracks. A fix that needs
  a new file is left in the working tree rather than silently committed.
- Reverting touches tracked files only; untracked work in progress is never destroyed.

## Models

Planning runs on the stronger model, mechanical edits on the cheaper one:

```bash
BUGHUNT_PLAN_MODEL=opus BUGHUNT_WORK_MODEL=sonnet python3 tools/bughunt/bughunt.py --fix
```

Deciding which failure is causal and which is downstream noise is a judgement call worth the
better model. Executing a decided plan is not.

## Running it on a schedule

`--loop N` is the inner loop: detect → fix → re-check, repeated while it keeps improving.
For a recurring outer loop, drive it from the `/loop` skill or cron:

```bash
python3 tools/bughunt/bughunt.py --fix --loop 3 --quick
```

`--quick` skips `build.clean_clone` (cold `npm ci` dominates a run) during the loop. The final
verdict always re-runs the full suite regardless.

## What this does not do

- It does not prove the app works. Every check is a unit-level fact; no live generation or
  judge call happens here. See `docs/plans/` for the end-to-end smoke test.
- A kept fix is verified only against these checks. A defect no detector covers can be
  introduced and still read as strictly greener. The branch is for review, not for merging
  unread.
