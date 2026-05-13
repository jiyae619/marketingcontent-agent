#!/usr/bin/env python3
"""
Show eval scores from the feedback DB.

Usage:
  python3 scripts/scores.py             # recent 20 generations
  python3 scripts/scores.py --detail    # show per-criterion breakdown
  python3 scripts/scores.py --platform x        # filter by platform
  python3 scripts/scores.py --runs              # run eval on test_cases.json (uses API)
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import feedback_db

PASS_THRESHOLD = 70.0

BAR_WIDTH = 30
PLATFORM_COLORS = {
    "linkedin":  "\033[34m",   # blue
    "instagram": "\033[35m",   # magenta
    "circle":    "\033[95m",   # bright magenta
    "kakaotalk": "\033[33m",   # yellow
    "whatsapp":  "\033[32m",   # green
    "x":         "\033[97m",   # white
}
RESET = "\033[0m"
BOLD  = "\033[1m"
RED   = "\033[31m"
GREEN = "\033[32m"
DIM   = "\033[2m"


def bar(score: float, width: int = BAR_WIDTH) -> str:
    filled = int((score / 100) * width)
    color = GREEN if score >= PASS_THRESHOLD else RED
    return f"{color}{'█' * filled}{'░' * (width - filled)}{RESET} {score:5.1f}"


def platform_label(p: str) -> str:
    c = PLATFORM_COLORS.get(p, "")
    return f"{c}{BOLD}{p.upper():10}{RESET}"


def show_recent(platform_filter=None, detail=False, limit=20):
    import sqlite3
    conn = sqlite3.connect(feedback_db.DB_PATH)
    conn.row_factory = sqlite3.Row

    where = f"WHERE platform = '{platform_filter}'" if platform_filter else ""
    rows = conn.execute(
        f"SELECT platform, eval_score, eval_detail, original_input, created_at "
        f"FROM generations {where} ORDER BY created_at DESC LIMIT {limit}"
    ).fetchall()

    if not rows:
        print("No generations in DB yet. Run the app and generate some content first.")
        return

    print(f"\n{BOLD}Recent eval scores ({len(rows)} generations){RESET}\n")

    for r in rows:
        score = r["eval_score"] or 0.0
        label = platform_label(r["platform"])
        snippet = (r["original_input"] or "")[:50].replace("\n", " ")
        print(f"{label}  {bar(score)}  {DIM}\"{snippet}\"{RESET}")

        if detail and r["eval_detail"]:
            criteria = json.loads(r["eval_detail"])
            for c in criteria:
                icon = "✓" if c["passed"] else "✗"
                col  = GREEN if c["passed"] else RED
                name = c["criterion"].ljust(20)
                s    = f"{c['score']:5.1f}"
                ws   = f"w={c['weight']:.2f}"
                sug  = c.get("suggestion", "")
                print(f"    {col}{icon}{RESET} {name} {s}  {DIM}{ws}  {sug}{RESET}")
            print()


def show_platform_summary():
    import sqlite3
    conn = sqlite3.connect(feedback_db.DB_PATH)
    conn.row_factory = sqlite3.Row

    print(f"\n{BOLD}Platform averages (all time){RESET}\n")
    rows = conn.execute(
        """
        SELECT platform,
               COUNT(*) as gens,
               AVG(eval_score) as avg,
               MIN(eval_score) as low,
               MAX(eval_score) as high,
               (SELECT COUNT(*) FROM copies c WHERE c.platform = g.platform) as copies
        FROM generations g
        GROUP BY platform ORDER BY avg DESC
        """
    ).fetchall()

    if not rows:
        print("No data yet.")
        return

    for r in rows:
        avg = r["avg"] or 0.0
        label = platform_label(r["platform"])
        copies_str = f"{DIM}copies={r['copies']:3}{RESET}"
        range_str  = f"{DIM}min={r['low']:.0f} max={r['high']:.0f}{RESET}"
        print(f"{label}  {bar(avg)}  gens={r['gens']:3}  {copies_str}  {range_str}")

    print()
    print(f"  {GREEN}■{RESET} = ≥{PASS_THRESHOLD:.0f}/100  {RED}■{RESET} = <{PASS_THRESHOLD:.0f}/100")


def show_criterion_breakdown():
    """Aggregate per-criterion pass rates across all generations."""
    import sqlite3
    conn = sqlite3.connect(feedback_db.DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT platform, eval_detail FROM generations WHERE eval_detail IS NOT NULL"
    ).fetchall()
    if not rows:
        print("No eval detail yet.")
        return

    from collections import defaultdict
    stats = defaultdict(lambda: {"total": 0, "passed": 0, "score_sum": 0.0})

    for r in rows:
        platform = r["platform"]
        criteria = json.loads(r["eval_detail"])
        for c in criteria:
            key = f"{platform}/{c['criterion']}"
            stats[key]["total"] += 1
            stats[key]["score_sum"] += c["score"]
            if c["passed"]:
                stats[key]["passed"] += 1

    print(f"\n{BOLD}Criterion breakdown (pass rate + avg score){RESET}\n")
    last_platform = None
    for key in sorted(stats):
        platform, criterion = key.split("/", 1)
        if platform != last_platform:
            print(f"\n  {platform_label(platform)}")
            last_platform = platform
        s = stats[key]
        avg = s["score_sum"] / s["total"]
        pass_rate = s["passed"] / s["total"] * 100
        icon = GREEN + "✓" + RESET if pass_rate >= 70 else RED + "✗" + RESET
        print(f"    {icon} {criterion.ljust(20)} avg={avg:5.1f}  pass={pass_rate:5.1f}%  n={s['total']}")


def main():
    parser = argparse.ArgumentParser(description="Eval score viewer")
    parser.add_argument("--detail",   action="store_true", help="show per-criterion breakdown per generation")
    parser.add_argument("--platform", help="filter to one platform")
    parser.add_argument("--summary",  action="store_true", help="platform-level averages")
    parser.add_argument("--criteria", action="store_true", help="aggregate pass rates per criterion")
    parser.add_argument("--limit",    type=int, default=20)
    args = parser.parse_args()

    feedback_db.init_db()

    if args.summary:
        show_platform_summary()
    elif args.criteria:
        show_criterion_breakdown()
    else:
        show_recent(args.platform, args.detail, args.limit)
        print()
        show_platform_summary()


if __name__ == "__main__":
    main()
