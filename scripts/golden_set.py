"""Build the frozen golden set — the labelled measuring stick for judge accuracy.

Nothing downstream is falsifiable without this. Judge calibration (Stage 1), the
router confusion matrix (Stage 2) and the pairwise regression gate (Stage 4) all need
content whose correct verdict is already known, including content that is known-BAD.
The database has 9 approve / 1 edit / 0 reject, so there is no negative ground truth
at all and recall cannot be computed.

Two label sources, per the harness design:

  path A  human verdicts from the review UI  -> feedback_events (needs your time)
  path B  defect injection, truth by construction (this script, free, instant)

Path B is pure code on purpose. Injecting a defect with a model would make the label a
model's opinion; a literal string insertion makes it a fact. Every mutation is recorded
verbatim so a human can audit whether the label is fair.

    python3 scripts/golden_set.py                # build + freeze
    python3 scripts/golden_set.py --dry-run      # show composition, write nothing

The output is FROZEN: same sample_ids every run, so scores are comparable across
prompt versions. Rebuilding after the DB changes will produce a different set —
that is why the file is the artifact, not the query.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testing/core"))

import feedback_db                                  # noqa: E402  (for DB_PATH)
from evaluators import is_korean                    # noqa: E402  (one language rule)

OUT = os.path.join(HERE, "testing/golden/golden_set_v1.json")
SET_VERSION = "v1"

# Per (platform, language) cell. Small on purpose: a golden set is reviewed by hand,
# and 2 bases x 2 variants x 12 cells is already more than a person will label well.
BASES_PER_CELL = 2
MIN_CHARS = 80
PLATFORMS = ["linkedin", "instagram", "circle", "kakaotalk", "whatsapp", "x"]


# --- defects -----------------------------------------------------------------
# One per FLAG_TAXONOMY category. Each is a literal insertion, so the label is a fact
# about what we did, not a judgement about what the text means.
#
# `guard` strings prevent a muddy label: if the base or brief already contains the
# thing we are about to "invent", the sample is skipped rather than mislabelled.
DEFECTS = {
    "hallucination": {
        "family": "grounding",
        "note": "appends logistics absent from the brief — a price and a start time",
        "en": "\n\nTickets are $45 per person and the session starts at 3:00 PM sharp.",
        "ko": "\n\n참가비는 1인당 45달러이며, 세션은 오후 3시 정각에 시작합니다.",
        "guard": ["45", "3:00", "3시", "$", "달러"],
    },
    "irrelevant": {
        "family": "grounding",
        "note": "prepends generic filler that says nothing specific about this event",
        "en": "We are excited to share an amazing opportunity with our wonderful "
              "community today. There is something here for everyone.\n\n",
        "ko": "오늘 우리 멋진 커뮤니티와 함께 놀라운 기회를 나누게 되어 기쁩니다. "
              "모두에게 좋은 자리가 될 것입니다.\n\n",
        "guard": [],
        "prepend": True,
    },
    "ai_slop": {
        "family": "voice",
        "note": "appends stacked cliches — the exact register the voice work removes",
        "en": "\n\nIn today's fast-paced world, this is a true game-changer that will "
              "take your career to the next level. Don't miss out on this journey!",
        "ko": "\n\n빠르게 변화하는 오늘날, 이것은 여러분의 커리어를 한 단계 "
              "끌어올릴 진정한 게임 체인저입니다. 이 여정을 놓치지 마세요!",
        "guard": ["game-changer", "게임 체인저", "next level"],
    },
    "kr_en_register": {
        "family": "voice",
        # Language is set by the brief ("write in the SAME language as the input"), so
        # a block in the other language is a register break by construction.
        "note": "appends a block in the opposite language to the rest of the post",
        "en": "\n\n지금 바로 신청하시기 바랍니다. 자세한 사항은 아래를 참고해 주시기 바랍니다.",
        "ko": "\n\nRegister now to secure your spot. See below for full details.",
        "guard": [],
    },
}
CATEGORIES = list(DEFECTS)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def fetch_bases(conn):
    """Candidate substrate: real generations with content and a brief to judge against.

    Ordered deterministically (score desc, then id) so the same rows are picked every
    run — a golden set that reshuffles is not a measuring stick.
    """
    rows = conn.execute(
        """
        SELECT id, platform, original_input, generated_content, eval_score,
               model, prompt_version
        FROM generations
        WHERE generated_content IS NOT NULL
          AND length(generated_content) >= ?
          AND original_input IS NOT NULL
          AND length(original_input) >= 10
        ORDER BY eval_score DESC, id ASC
        """,
        (MIN_CHARS,),
    ).fetchall()
    return [dict(r) for r in rows]


def inject(content, brief, category, korean):
    """Apply a defect. Returns (mutated_text, inserted_string), or (None, None) when
    the label would not hold.

    The guard checks the BRIEF as well as the content, and the brief is the load-bearing
    half: "hallucination" means a fact absent from the brief. One base here has a brief
    reading "marketing event - Oct 10th, 2026, 3PM EST" — appending a 3PM start time to
    that is grounded, not invented, and would have been labelled a hallucination.
    Checking only the content would have shipped a wrong label into the measuring stick.
    """
    d = DEFECTS[category]
    piece = d["ko"] if korean else d["en"]
    haystack = (content + "\n" + (brief or "")).lower()
    for g in d["guard"]:
        if g.lower() in haystack:
            return None, None
    if d.get("prepend"):
        return piece + content, piece.strip()
    return content + piece, piece.strip()


def build(bases):
    """Stratify by (platform, language), then emit a clean and a defective sample per
    base. Defect categories rotate by index so coverage stays even across cells rather
    than piling one category onto one platform."""
    cells = {}
    for b in bases:
        lang = "ko" if is_korean(b["generated_content"]) else "en"
        cells.setdefault((b["platform"], lang), []).append(b)

    samples, skipped, cat_i = [], [], 0
    for (platform, lang), rows in sorted(cells.items()):
        for b in rows[:BASES_PER_CELL]:
            content = b["generated_content"]
            common = {
                "source_generation_id": b["id"],
                "platform": platform,
                "language": lang,
                "brief": b["original_input"],
                "base_eval_score": b["eval_score"],
                "base_model": b["model"],
                "base_prompt_version": b["prompt_version"],
            }
            # Clean: expected to PASS. Without these the set only measures recall.
            samples.append({
                "sample_id": f"gs{SET_VERSION}-{platform}-{lang}-{b['id']}-clean",
                **common,
                "content": content,
                "content_sha256": sha(content),
                "expect_fail": False,
                "category": None,
                "family": None,
                "mutation": None,
            })
            # Defective: expected to FAIL on exactly one known category.
            for _ in range(len(CATEGORIES)):          # try each until one is clean-able
                cat = CATEGORIES[cat_i % len(CATEGORIES)]
                cat_i += 1
                mutated, inserted = inject(content, b["original_input"], cat, lang == "ko")
                if mutated:
                    samples.append({
                        "sample_id": f"gs{SET_VERSION}-{platform}-{lang}-{b['id']}-{cat}",
                        **common,
                        "content": mutated,
                        "content_sha256": sha(mutated),
                        "expect_fail": True,
                        "category": cat,
                        "family": DEFECTS[cat]["family"],
                        "mutation": {"type": "insertion", "category": cat,
                                     "inserted": inserted,
                                     "note": DEFECTS[cat]["note"]},
                    })
                    break
            else:
                skipped.append((b["id"], platform, "every defect already present"))
    return samples, skipped


def report(samples, skipped, cells_available):
    n_clean = sum(1 for s in samples if not s["expect_fail"])
    n_bad = len(samples) - n_clean
    print(f"\nGOLDEN SET {SET_VERSION} — {len(samples)} samples "
          f"({n_clean} clean / {n_bad} defective)\n")

    print("  by platform x language")
    grid = {}
    for s in samples:
        grid.setdefault((s["platform"], s["language"]), [0, 0])
        grid[(s["platform"], s["language"])][1 if s["expect_fail"] else 0] += 1
    for (p, l), (c, b) in sorted(grid.items()):
        print(f"    {p:10} {l}   clean={c}  defective={b}")

    print("\n  negative labels by category (was 0 before this set)")
    for cat in CATEGORIES:
        n = sum(1 for s in samples if s["category"] == cat)
        fam = DEFECTS[cat]["family"]
        flag = "" if n else "   <-- NO COVERAGE"
        print(f"    {cat:16} ({fam:9}) {n}{flag}")

    # Absent cells matter more than thin ones and are easy to miss: a cell with zero
    # bases never appears in any per-cell loop, so the set looks balanced across the
    # rows it happens to have. Enumerate the full grid instead.
    expected = {(p, l) for p in PLATFORMS for l in ("ko", "en")}
    missing = sorted(expected - set(cells_available))
    if missing:
        print(f"\n  MISSING cells (0 bases — unmeasurable): "
              f"{', '.join(f'{p}/{l}' for p, l in missing)}")

    thin = [f"{p}/{l}" for (p, l), rows in sorted(cells_available.items())
            if len(rows) < BASES_PER_CELL]
    if thin:
        print(f"  UNDERFILLED cells (<{BASES_PER_CELL} bases available): {', '.join(thin)}")
    if missing or thin:
        print("    Generate more locally to fill them — free, no API cost:")
        print("      python3 scripts/compare_generators.py --brief \"<a KR brief>\" \\")
        print("        --models local:gemma3:4b --platforms kakaotalk,x,whatsapp")
    if skipped:
        print(f"\n  skipped {len(skipped)} base(s): {skipped}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="show composition, write nothing")
    ap.add_argument("-o", "--out", default=OUT)
    args = ap.parse_args()

    conn = sqlite3.connect(feedback_db.DB_PATH)
    conn.row_factory = sqlite3.Row
    bases = fetch_bases(conn)
    if not bases:
        print("No usable generations — need content plus a brief to judge against.")
        return 1

    cells = {}
    for b in bases:
        lang = "ko" if is_korean(b["generated_content"]) else "en"
        cells.setdefault((b["platform"], lang), []).append(b)

    samples, skipped = build(bases)
    report(samples, skipped, cells)

    if args.dry_run:
        print("\n  --dry-run: nothing written\n")
        return 0

    payload = {
        "set_version": SET_VERSION,
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_db": os.path.basename(feedback_db.DB_PATH),
        "label_source": "path B — defect injection, truth by construction",
        "taxonomy": {c: DEFECTS[c]["family"] for c in CATEGORIES},
        "counts": {
            "total": len(samples),
            "clean": sum(1 for s in samples if not s["expect_fail"]),
            "defective": sum(1 for s in samples if s["expect_fail"]),
        },
        "samples": samples,
    }
    os.makedirs(os.path.dirname(os.path.expanduser(args.out)), exist_ok=True)
    with open(os.path.expanduser(args.out), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n  wrote {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
