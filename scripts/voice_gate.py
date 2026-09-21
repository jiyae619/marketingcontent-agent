#!/usr/bin/env python3
"""Stage 4 — the regression gate on a learned voice profile.

The loop can now write a profile (see server._maybe_synthesize_voice). Nothing
checked whether the profile it wrote was an improvement. That gap is worse than it
sounds: a profile is injected into EVERY later generation for its platform, and
installing one bumps voice_version, which invalidates the cached rows you would
otherwise have compared against. So a bad profile degrades everything downstream
AND destroys the evidence in the same motion.

_clean_voice_profile() in server.py guards the SHAPE of a profile — non-empty, not
a regurgitated sample, within a word band. This guards its EFFECT: regenerate the
same briefs under the previous profile and the new one, score both with the free
heuristic, and compare.

    python3 scripts/voice_gate.py --platform linkedin
    python3 scripts/voice_gate.py --platform linkedin --rollback

Deliberately offline and deliberately not on the request path. A run is 2-8 local
generations (2 per golden brief for the platform), which is minutes on a 4B — an
approve must not block on that. Run it after synthesis reports a new profile.

Sampling is pinned to temperature 0. At the server default the gap between two
generations is mostly sampling noise, and the gate would be measuring the sampler
instead of the profile. That also means this measures the profile's effect on ONE
deterministic draft per brief, not its effect in expectation — a real estimate
would need N samples per condition, which the 8GB budget does not buy.
"""
import argparse
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testing/core"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(HERE, ".env"))

import feedback_db      # noqa: E402
import generators       # noqa: E402
from evaluators import evaluate as run_eval, strip_markdown  # noqa: E402

GOLDEN = os.path.join(HERE, "testing/golden/golden_set_v1.json")

# How far the median may fall before the new profile is called a regression. Not
# tuned — there is no run history to tune against yet. It is a starting line that
# exists so the decision is written down rather than made ad hoc each time.
REGRESSION_TOLERANCE = 2.0


def channel_prompt(platform):
    """The `## AI Prompt` slice — the same artifact server.py sends, not the whole file."""
    path = os.path.join(HERE, f"docs/{platform}.md")
    content = open(path, encoding="utf-8").read()
    start = content.find("## AI Prompt")
    if start == -1:
        raise ValueError(f"no '## AI Prompt' section in {path}")
    start += len("## AI Prompt")
    nxt = content.find("\n##", start)
    return (content[start:nxt] if nxt != -1 else content[start:]).strip()


def with_profile(base, style):
    """Mirror server._with_voice_examples' synthesized branch, for an ARBITRARY profile.

    The gate has to inject a profile the database does not consider active, so it
    cannot call the server helper (which reads the active one). Kept byte-identical
    to that branch on purpose: a gate that assembles the prompt differently from
    production is measuring a prompt that never ships.
    """
    if not style:
        return base
    return base + ("\n\n## Your Voice Style\n"
                   "Write in this user's established voice and style:\n\n" + style)


def golden_briefs(platform):
    """Distinct clean briefs for a platform. Reuses the golden set's BRIEFS, not its
    labels: expect_fail describes an injected defect and says nothing about how well
    a generator writes."""
    if not os.path.exists(GOLDEN):
        return []
    data = json.load(open(GOLDEN, encoding="utf-8"))
    seen, out = set(), []
    for s in data["samples"]:
        if s["platform"] != platform or s["expect_fail"]:
            continue
        b = (s.get("brief") or "").strip()
        if b and b not in seen:
            seen.add(b)
            out.append({"brief": b, "language": s.get("language")})
    return out


def generate(platform, brief, style, model_key=None):
    """One deterministic generation under `style`. Returns (score, text, error)."""
    system = with_profile(channel_prompt(platform), style)
    key, label, model_id, fn = generators.resolve(model_key)
    res = fn(f"User content to transform:\n{brief}", model=model_id,
             system=system, temperature=0)
    if not res.get("ok") or not res.get("text"):
        return None, None, res.get("error") or "empty response"
    # Strip on the generation path, as server.py does, so the score is computed on
    # the bytes that would actually ship.
    text = strip_markdown(res["text"])
    return run_eval(platform, text)["total"], text, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True)
    ap.add_argument("--model", default=None, help="generator registry key; default resolves from env")
    ap.add_argument("--tolerance", type=float, default=REGRESSION_TOLERANCE)
    ap.add_argument("--rollback", action="store_true",
                    help="on regression, reinstate the previous profile as a new version")
    args = ap.parse_args()

    hist = feedback_db.voice_profile_history(args.platform, limit=2)
    if not hist:
        print(f"no voice profile for {args.platform} — nothing to gate.")
        return 0
    new = hist[0]
    prev = hist[1] if len(hist) > 1 else None
    if prev is None:
        # The first profile has no predecessor, so there is no regression to measure.
        # Saying that plainly beats inventing a baseline of "no profile at all",
        # which is a different comparison than the one this gate is for.
        print(f"{args.platform}: profile v{new['version']} is the first — no predecessor "
              f"to compare against. Nothing gated.")
        return 0

    briefs = golden_briefs(args.platform)
    if not briefs:
        print(f"{args.platform}: no clean golden briefs — cannot gate. "
              f"(rebuild: scripts/golden_set.py)")
        return 0

    print(f"\nVOICE GATE — {args.platform}: v{prev['version']} -> v{new['version']} "
          f"on {len(briefs)} golden brief(s), temperature 0\n")

    rows, failures = [], []
    for i, b in enumerate(briefs, 1):
        before, _, e1 = generate(args.platform, b["brief"], prev["style_text"], args.model)
        after, _, e2 = generate(args.platform, b["brief"], new["style_text"], args.model)
        if e1 or e2:
            # A generation that never ran is not evidence of a regression. Say which
            # side failed and exclude the pair, rather than scoring a missing draft 0
            # and reporting a collapse that did not happen.
            failures.append(f"brief {i} ({b['language']}): {e1 or e2}")
            print(f"  {i}. {b['language']:>2}  SKIPPED — {e1 or e2}")
            continue
        rows.append((before, after))
        d = after - before
        print(f"  {i}. {b['language']:>2}  {before:5.1f} -> {after:5.1f}   "
              f"{d:+5.1f}  {'WORSE' if d < 0 else ('same' if d == 0 else 'better')}")

    if not rows:
        print(f"\n  INCONCLUSIVE — every generation failed. The profile is unchanged.")
        for f in failures:
            print(f"    {f}")
        return 2

    m_before = statistics.median(r[0] for r in rows)
    m_after = statistics.median(r[1] for r in rows)
    delta = m_after - m_before
    print(f"\n  median {m_before:.1f} -> {m_after:.1f}   ({delta:+.1f}, "
          f"tolerance {args.tolerance:.1f})")
    if failures:
        print(f"  {len(failures)} of {len(briefs)} briefs could not be generated — "
              f"this verdict rests on {len(rows)}.")

    if delta < -args.tolerance:
        print(f"\n  REGRESSION: profile v{new['version']} scores worse than v{prev['version']}.")
        if args.rollback:
            feedback_db.save_voice_profile(args.platform, prev["style_text"],
                                           based_on=prev.get("based_on"))
            restored = feedback_db.voice_profile_history(args.platform, limit=1)[0]
            print(f"  ROLLED BACK — v{prev['version']}'s text reinstated as "
                  f"v{restored['version']} (append-only; nothing was deleted).")
        else:
            print(f"  Not rolled back. Re-run with --rollback to reinstate "
                  f"v{prev['version']}.")
        return 1

    print(f"\n  PASS — v{new['version']} is not a regression.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
