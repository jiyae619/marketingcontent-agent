"""Stage 2 — evaluate the escalation gate as the classifier it actually is.

JUDGE_TRIGGER_THRESHOLD decides whether a generation is escalated to the LLM judge.
That is a routing decision, and it was never measured. Replay the golden set through
the heuristic ONLY, compare its verdict against the known labels, and read the
confusion matrix. Costs nothing: evaluators.py is free and the labels already exist.

The two error types are not comparable:

    FALSE NEGATIVE   bad content skips the judge and reaches a human unflagged.
                     Recall is the guardrail metric — this is what erodes trust.
    FALSE POSITIVE   good content pays for a judge call it did not need.
                     Costs money (or, on a local judge, only latency).

    python3 scripts/tune_threshold.py
    python3 scripts/tune_threshold.py --target-recall 0.90
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testing/core"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(HERE, ".env"))

from evaluators import evaluate as run_eval  # noqa: E402

GOLDEN = os.path.join(HERE, "testing/golden/golden_set_v1.json")


def confusion(rows, t):
    """escalate when score < t."""
    tp = sum(1 for bad, _, s in rows if bad and s < t)
    fn = sum(1 for bad, _, s in rows if bad and s >= t)
    fp = sum(1 for bad, _, s in rows if not bad and s < t)
    tn = sum(1 for bad, _, s in rows if not bad and s >= t)
    return tp, fn, fp, tn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-recall", type=float, default=0.90)
    ap.add_argument("--golden", default=GOLDEN)
    args = ap.parse_args()

    if not os.path.exists(args.golden):
        print(f"No golden set at {args.golden} — run scripts/golden_set.py first.")
        return 1
    data = json.load(open(args.golden, encoding="utf-8"))
    rows = [(s["expect_fail"], s["category"],
             run_eval(s["platform"], s["content"])["total"])
            for s in data["samples"]]
    clean = sorted(s for bad, _, s in rows if not bad)
    bad = sorted(s for bad, _, s in rows if bad)
    if not clean or not bad:
        print("Golden set needs both clean and defective samples.")
        return 1

    print(f"\nGATE EVALUATION — {len(rows)} golden samples "
          f"({len(clean)} clean / {len(bad)} defective)\n")

    # Separability first. If the classes overlap, no threshold can work and the
    # sweep below is only measuring where you would rather be wrong.
    overlap = sum(1 for b in bad if b > min(clean))
    print(f"  clean      min={min(clean):5.1f}  median={clean[len(clean)//2]:5.1f}  max={max(clean):5.1f}")
    print(f"  defective  min={min(bad):5.1f}  median={bad[len(bad)//2]:5.1f}  max={max(bad):5.1f}")
    print(f"  SEPARABILITY: {overlap}/{len(bad)} defective samples score above the "
          f"lowest clean sample")

    print(f"\n  {'T':>3} {'recall':>7} {'precis':>7} {'escal':>6}   {'TP':>2} {'FN':>2} {'FP':>2} {'TN':>2}")
    best = None
    for t in range(50, 101, 5):
        tp, fn, fp, tn = confusion(rows, t)
        rec = tp / (tp + fn) if tp + fn else 0.0
        pre = tp / (tp + fp) if tp + fp else 0.0
        esc = (tp + fp) / len(rows)
        mark = ""
        if rec >= args.target_recall and best is None:
            best, mark = t, "  <- first T hitting target recall"
        print(f"  {t:>3} {rec:7.2f} {pre:7.2f} {esc:6.0%}   {tp:2} {fn:2} {fp:2} {tn:2}{mark}")

    # Which defect families the gate is structurally blind to. This is the actionable
    # half: a category the heuristic cannot see is not a tuning problem.
    print("\n  recall by category at T=70 (the shipped default)")
    cats = sorted({c for bad_, c, _ in rows if bad_ and c})
    for c in cats:
        sub = [(b, cc, s) for b, cc, s in rows if cc == c]
        tp, fn, _, _ = confusion(sub, 70)
        print(f"    {c:16} {tp}/{tp+fn} caught")

    print()
    if best is None:
        print(f"  VERDICT: no threshold in 50-100 reaches {args.target_recall:.0%} recall.")
    else:
        tp, fn, fp, tn = confusion(rows, best)
        print(f"  VERDICT: T={best} is the lowest threshold hitting "
              f"{args.target_recall:.0%} recall — it escalates "
              f"{(tp+fp)/len(rows):.0%} of all content.")
    if overlap > len(bad) * 0.5:
        print("  The classes overlap, so the gate cannot separate them at any value.\n"
              "  The heuristic never receives the brief, so grounding defects are\n"
              "  invisible to it by construction — that is not fixable with a number.\n"
              "  When the judge is free, do not gate; see JUDGE_TRIGGER_THRESHOLD\n"
              "  handling in server.py._maybe_judge.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
