#!/usr/bin/env python3
"""bughunt — detect bugs deterministically, fix them with agents, keep only what verifies.

    python3 tools/bughunt/bughunt.py                 # detect only, report, change nothing
    python3 tools/bughunt/bughunt.py --fix           # detect -> fix on a scratch branch
    python3 tools/bughunt/bughunt.py --fix --loop 3  # keep going while it improves
    python3 tools/bughunt/bughunt.py --review        # + agent hunt for logic bugs in the diff

Two tiers, deliberately separated (CLAUDE.md rule 5):

  detectors.py  facts. Runs commands and asserts invariants. No model, no tokens,
                cannot hallucinate. Everything decidable lives here.
  agents        judgment. Only sees what the detectors already proved is broken,
                plus the diff review, which is the one job code cannot do.

The gate is the whole safety story. An agent's patch is kept only if a full
re-run comes back STRICTLY greener: at least one check repaired, and not a single
check that was passing now failing. Anything else is reverted and recorded as a
failed attempt. The agent does not get to grade its own work — the detectors do.

Nothing here pushes, and nothing runs on main.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import detectors  # noqa: E402

# The user's split: planning is a judgement call worth the better model; the
# mechanical edit that follows a decided plan is not.
PLAN_MODEL = os.getenv("BUGHUNT_PLAN_MODEL", "opus")
WORK_MODEL = os.getenv("BUGHUNT_WORK_MODEL", "sonnet")

PROTECTED = {"main", "master"}


# --------------------------------------------------------------------------
# git helpers — every mutation is local, on a scratch branch, never pushed
# --------------------------------------------------------------------------

def git(*args, check=False):
    p = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def current_branch():
    return git("rev-parse", "--abbrev-ref", "HEAD")[1]


def tree_dirty():
    return bool(git("status", "--porcelain", "--untracked-files=no")[1])


def revert_worktree():
    """Undo whatever the agent just did. Tracked files only — never touches
    untracked files, which may be the user's own work in progress."""
    git("checkout", "--", ".")


# --------------------------------------------------------------------------
# agents
# --------------------------------------------------------------------------

def claude(prompt, model, timeout=900, allow_edits=False):
    """One headless Claude Code call. Returns text, or None if it failed."""
    cmd = ["claude", "-p", prompt, "--model", model]
    if allow_edits:
        cmd += ["--permission-mode", "acceptEdits"]
    else:
        cmd += ["--permission-mode", "plan"]
    try:
        p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"    [agent] TIMEOUT after {timeout}s ({model})")
        return None
    if p.returncode != 0:
        print(f"    [agent] exit {p.returncode} ({model}): {(p.stderr or '')[:300]}")
        return None
    return (p.stdout or "").strip()


def triage(failing):
    """Ask the planning model to order the work and name a root cause per finding.

    Ordering is a judgement call — which failure is causal and which is downstream
    noise is not something a severity constant knows.
    """
    summary = "\n\n".join(
        f"### {f['id']}  [{f['severity']}]\n{f['title']}\n"
        f"reproduce: {f['cmd']}\n---\n{f['detail'][:1200]}"
        for f in failing)
    prompt = f"""You are triaging failures in a repo before other agents fix them.
Read {REPO}/CLAUDE.md first — its rules override general practice, especially:
LOCAL_ONLY means no paid API call ever; output is never markdown; prompts and
scorers are one decision in two files.

{len(failing)} deterministic checks are failing:

{summary}

Return ONLY a JSON array, ordered so causal failures come before ones they may
explain. One object per finding you judge worth fixing:

[{{"id": "<the check id>", "root_cause": "<one sentence, what is actually wrong>",
   "fix": "<the specific change, naming files>", "risk": "low|medium|high"}}]

Drop any finding whose correct action is a human decision rather than an edit.
No prose outside the JSON."""
    out = claude(prompt, PLAN_MODEL, timeout=600)
    if not out:
        return []
    try:
        start, end = out.index("["), out.rindex("]") + 1
        return json.loads(out[start:end])
    except Exception as e:
        print(f"    [triage] could not parse plan: {e}")
        return []


def fix_one(item, finding):
    """Hand one decided item to the working model. It edits files; it does not judge."""
    prompt = f"""Fix exactly one defect in this repo. Read {REPO}/CLAUDE.md first and obey it.

Check id:    {item['id']}
Symptom:     {finding['title']}
Root cause:  {item.get('root_cause', '(not given)')}
Planned fix: {item.get('fix', '(not given)')}
Reproduce:   {finding['cmd']}

Evidence:
{finding['detail'][:2000]}

Rules for this edit:
- Change the minimum that fixes the cause. No refactoring, no drive-by cleanups,
  no touching adjacent code (CLAUDE.md rule 3).
- Match the surrounding style and comment density.
- Do NOT edit the check itself to make it pass. Fix the defect it found.
- Do NOT commit, stage, or push. Leave changes in the working tree.
- If the right fix is a human judgement call rather than an edit, change nothing
  and say why.

Make the edit now."""
    return claude(prompt, WORK_MODEL, timeout=900, allow_edits=True)


def review_diff(base):
    """Agent hunt for logic bugs in the diff, each finding adversarially verified.

    This is the one job the detector tier cannot do: "is this code wrong" is not
    decidable by running a command. Findings are cheap to generate and expensive
    to trust, so a second pass tries to refute each one before it is reported.
    """
    rc, diff, _ = git("diff", f"{base}...HEAD")
    if rc != 0 or not diff.strip():
        return []
    if len(diff) > 60000:
        diff = diff[:60000] + "\n… [diff truncated for review] …"

    find = claude(f"""Hunt for correctness bugs in this diff. Read {REPO}/CLAUDE.md first.

Look for: logic errors, unhandled error paths, state that can go stale, races,
off-by-one, a prompt target that disagrees with its scorer band, and tests that
cannot fail when the behaviour changes.

Ignore: style, naming, formatting, anything cosmetic.

Return ONLY a JSON array (empty if you find nothing real):
[{{"file": "path", "line": 0, "claim": "<the defect in one sentence>",
   "failure": "<concrete inputs -> wrong result>"}}]

DIFF:
{diff}""", WORK_MODEL, timeout=900)
    if not find:
        return []
    try:
        claims = json.loads(find[find.index("["):find.rindex("]") + 1])
    except Exception:
        return []

    confirmed = []
    for c in claims[:8]:
        verdict = claude(f"""Try to REFUTE this bug report about {REPO}. Default to refuted
if you are uncertain — a plausible-sounding bug that is not real costs more than a miss.

Claim:   {c.get('claim')}
File:    {c.get('file')}:{c.get('line')}
Failure: {c.get('failure')}

Read the actual code before deciding. Return ONLY JSON:
{{"refuted": true|false, "why": "<one sentence>"}}""", WORK_MODEL, timeout=600)
        if not verdict:
            continue
        try:
            v = json.loads(verdict[verdict.index("{"):verdict.rindex("}") + 1])
        except Exception:
            continue
        if not v.get("refuted"):
            confirmed.append({**c, "verified": v.get("why", "")})
    return confirmed


# --------------------------------------------------------------------------
# the gate
# --------------------------------------------------------------------------

def compare(before, after):
    b = {f["id"]: f["ok"] for f in before}
    a = {f["id"]: f["ok"] for f in after}
    regressions = sorted(k for k in a if b.get(k) and not a[k])
    repairs = sorted(k for k in a if k in b and not b[k] and a[k])
    return repairs, regressions


def strictly_greener(before, after):
    repairs, regressions = compare(before, after)
    return bool(repairs) and not regressions


# --------------------------------------------------------------------------

def summarize(findings):
    return " ".join(("+" if f["ok"] else "-") + f["id"] for f in findings)


def main():
    ap = argparse.ArgumentParser(description="detect bugs in code, fix them with agents")
    ap.add_argument("--fix", action="store_true", help="let agents attempt fixes (scratch branch)")
    ap.add_argument("--loop", type=int, default=1, help="max detect/fix rounds (default 1)")
    ap.add_argument("--quick", action="store_true", help="skip slow detectors during the loop")
    ap.add_argument("--review", action="store_true", help="also agent-review the diff vs --base")
    ap.add_argument("--base", default="origin/main", help="base ref for --review (default origin/main)")
    ap.add_argument("--report", default=os.path.join(HERE, "report.md"))
    ap.add_argument("--allow-dirty", action="store_true", help="proceed with uncommitted changes")
    args = ap.parse_args()

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    branch = current_branch()
    started_on = branch
    work_branch = None

    print(f"bughunt {stamp}  branch={branch}  plan={PLAN_MODEL}  work={WORK_MODEL}")

    if args.fix:
        # Two rails, both because an agent will be editing files unattended.
        if branch in PROTECTED:
            sys.exit(f"refusing to run --fix on {branch}. Make a branch first.")
        if tree_dirty() and not args.allow_dirty:
            sys.exit("working tree has uncommitted changes — commit or stash them first, "
                     "so a reverted fix cannot take your work with it (--allow-dirty to override).")

    rounds = []
    baseline = detectors.run_all(quick=args.quick)
    print(f"\nround 0  {summarize(baseline)}")
    for f in baseline:
        if not f["ok"]:
            print(f"    FAIL {f['id']:<28} {f['title']}")

    if args.fix and any(not f["ok"] for f in baseline):
        work_branch = f"bughunt/{stamp}"
        git("checkout", "-b", work_branch, check=True)
        print(f"\nworking on {work_branch} (never pushed, never main)")

        for rnd in range(1, args.loop + 1):
            failing = [f for f in baseline if not f["ok"] and f["fixable"]]
            if not failing:
                break
            print(f"\nround {rnd}: triaging {len(failing)} finding(s) with {PLAN_MODEL}")
            plan = triage(failing)
            if not plan:
                print("    no actionable plan returned — stopping")
                break

            progressed = False
            for item in plan:
                finding = next((f for f in baseline if f["id"] == item.get("id")), None)
                if not finding or finding["ok"]:
                    continue
                print(f"  fixing {item['id']} ({item.get('risk','?')} risk) with {WORK_MODEL}")
                fix_one(item, finding)
                if not tree_dirty():
                    print("    agent made no change — skipped")
                    rounds.append({"round": rnd, "id": item["id"], "outcome": "no-change",
                                   "root_cause": item.get("root_cause", "")})
                    continue

                after = detectors.run_all(quick=args.quick)
                repairs, regressions = compare(baseline, after)
                if strictly_greener(baseline, after):
                    # -u, never -A: stage only files git already tracks. -A would
                    # sweep in whatever else is lying around untracked — including,
                    # in this repo right now, a stray nested clone that would commit
                    # as a broken gitlink. A fix that needs a NEW file is therefore
                    # left in the working tree for a human, not silently committed.
                    git("add", "-u")
                    git("commit", "-m",
                        f"fix({item['id']}): {item.get('root_cause','automated fix')[:60]}\n\n"
                        f"Found by tools/bughunt. Kept because a full re-run came back\n"
                        f"strictly greener: repaired {', '.join(repairs)} with no regressions.\n\n"
                        f"Planned fix: {item.get('fix','')}\n")
                    print(f"    KEPT — repaired {', '.join(repairs)}")
                    baseline = after
                    progressed = True
                    rounds.append({"round": rnd, "id": item["id"], "outcome": "kept",
                                   "repairs": repairs})
                else:
                    revert_worktree()
                    why = (f"regressed {', '.join(regressions)}" if regressions
                           else "repaired nothing")
                    print(f"    REVERTED — {why}")
                    rounds.append({"round": rnd, "id": item["id"], "outcome": "reverted",
                                   "why": why})
            if not progressed:
                print("    no progress this round — stopping")
                break

        # The loop may have run with --quick; the final verdict never does.
        if args.quick:
            print("\nfinal full re-run (no --quick)")
            baseline = detectors.run_all(quick=False)

    reviewed = []
    if args.review:
        print(f"\nreviewing diff vs {args.base} with {WORK_MODEL} (find -> refute)")
        reviewed = review_diff(args.base)
        print(f"    {len(reviewed)} finding(s) survived refutation")

    # ---- report ----
    lines = [f"# bughunt {stamp}", "",
             f"- started on `{started_on}`" +
             (f", fixes on `{work_branch}`" if work_branch else " (detect only)"),
             f"- plan model `{PLAN_MODEL}`, work model `{WORK_MODEL}`", ""]
    lines += ["## Checks", ""]
    for f in baseline:
        lines.append(f"- {'PASS' if f['ok'] else '**FAIL**'} `{f['id']}` — {f['title']}")
        if not f["ok"]:
            lines += ["", "  ```", *[f"  {l}" for l in f["detail"].splitlines()[:25]],
                      "  ```", f"  reproduce: `{f['cmd']}`", ""]
    if rounds:
        lines += ["", "## Fix attempts", ""]
        for r in rounds:
            detail = (", ".join(r.get("repairs", [])) or r.get("why", "")
                      or r.get("root_cause", ""))
            lines.append(f"- round {r['round']} `{r['id']}` — **{r['outcome']}** {detail}")
    if args.review:
        lines += ["", "## Diff review (agent, adversarially verified)", ""]
        lines += ([f"- `{c.get('file')}:{c.get('line')}` — {c.get('claim')}  \n"
                   f"  failure: {c.get('failure')}  \n  survived refutation: {c.get('verified')}"
                   for c in reviewed]
                  or ["- nothing survived refutation"])
    lines += ["", "## Not verified", "",
              "- Detectors assert what they run. A passing suite is not proof the app works "
              "end to end; no live generation or judge call happens here.",
              "- Kept fixes are verified only against these checks. A defect no detector "
              "covers can be introduced by a fix and still read as strictly greener."]
    open(args.report, "w").write("\n".join(lines) + "\n")

    failed = [f for f in baseline if not f["ok"]]
    print(f"\nreport: {args.report}")
    print(f"{len(baseline) - len(failed)}/{len(baseline)} checks passing")
    if work_branch:
        print(f"review the work:  git log --oneline {started_on}..{work_branch}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
