"""Export the eval log as a readable HTML table.

Joins the three spine tables into one review surface — for each brief, every
channel's output side by side with its heuristic score, LLM judge grade, and human
verdict. The DB is the source of truth; this is the human-readable view of it.

    generations     the brief + what each channel produced (+ provenance)
    judge_results   the machine grade
    feedback_events the human verdict

Usage:
    python3 scripts/export_eval_log.py                 # last 20 briefs
    python3 scripts/export_eval_log.py --limit 50
    python3 scripts/export_eval_log.py -o ~/somewhere.html
"""
import argparse
import html
import json
import os
import sqlite3
import sys
from collections import OrderedDict
from datetime import datetime

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import feedback_db  # noqa: E402  (for DB_PATH — single source of truth)

DEFAULT_OUT = os.path.expanduser(
    "~/dev/documents/html-previews/marketing-agent-eval-log.html")
PLATFORM_ORDER = ["linkedin", "instagram", "circle", "kakaotalk", "whatsapp", "x"]


def fetch(limit):
    conn = sqlite3.connect(feedback_db.DB_PATH)
    conn.row_factory = sqlite3.Row

    gens = conn.execute(
        """
        SELECT g.*,
               (SELECT json_group_array(json_object(
                        'judge_model', j.judge_model, 'overall', j.overall,
                        'safety_pass', j.safety_pass, 'scores', j.scores,
                        'summary', j.summary))
                  FROM judge_results j WHERE j.generation_id = g.id) AS judges,
               (SELECT f.verdict FROM feedback_events f
                 WHERE f.generation_id = g.id ORDER BY f.created_at DESC LIMIT 1) AS verdict,
               (SELECT f.flag_category FROM feedback_events f
                 WHERE f.generation_id = g.id ORDER BY f.created_at DESC LIMIT 1) AS flag
          FROM generations g
         ORDER BY g.created_at DESC
        """
    ).fetchall()
    conn.close()

    # Group by brief: one row per brief, its channels beside each other. Briefs are
    # what a person actually reviews — a flat generation list buries that.
    briefs = OrderedDict()
    for row in gens:
        key = row["original_input"]
        briefs.setdefault(key, []).append(dict(row))
        if len(briefs) > limit:
            briefs.popitem()
            break
    return briefs


def score_class(v):
    if v is None:
        return "none"
    return "good" if v >= 70 else ("mid" if v >= 45 else "bad")


def render_judge(raw):
    if not raw:
        return '<span class="nojudge">not judged</span>'
    try:
        entries = [e for e in json.loads(raw) if e]
    except Exception:
        return '<span class="nojudge">unparseable</span>'
    if not entries:
        return '<span class="nojudge">not judged</span>'
    out = []
    for e in entries:
        overall = e.get("overall")
        safe = e.get("safety_pass")
        # A row with no overall means the judge ran but its output could not be
        # parsed — that is "unknown", NOT a failing grade. Rendering NULL as
        # "safety FAIL" misreports a broken judge as unsafe content.
        if overall is None:
            out.append(
                f'<div class="judge"><div class="jhead">'
                f'<span class="unknown">not graded</span>'
                f'<span class="jm">{html.escape(str(e.get("judge_model") or ""))}</span>'
                f'</div><div class="jsum unknown-note">Judge ran but returned no '
                f'parseable scores — small local models often fail the JSON format. '
                f'This is not a safety failure.</div></div>')
            continue
        cats = ""
        try:
            scores = json.loads(e["scores"]) if isinstance(e.get("scores"), str) else (e.get("scores") or {})
            cats = "".join(
                f'<div class="cat"><span>{html.escape(c)}</span>'
                f'<b class="{score_class(d.get("score"))}">{d.get("score")}</b>'
                f'<i>{html.escape(str(d.get("reason", ""))[:150])}</i></div>'
                for c, d in scores.items())
        except Exception:
            pass
        out.append(
            f'<div class="judge">'
            f'<div class="jhead"><b class="{score_class(overall)}">{overall}</b>'
            f'<span class="jm">{html.escape(str(e.get("judge_model") or ""))}</span>'
            f'<span class="safe {"pass" if safe else ("fail" if safe is not None else "unknown")}">'
            f'{"safety pass" if safe else ("safety FAIL" if safe is not None else "safety n/a")}</span></div>'
            f'{cats}'
            + (f'<div class="jsum">{html.escape(str(e.get("summary") or ""))}</div>'
               if e.get("summary") else "")
            + '</div>')
    return "".join(out)


def build_html(briefs):
    rows = []
    for brief, gens in briefs.items():
        by_plat = {g["platform"]: g for g in gens}
        when = datetime.fromtimestamp(max(g["created_at"] for g in gens))
        cells = []
        for p in PLATFORM_ORDER:
            g = by_plat.get(p)
            if not g:
                cells.append(f'<td class="empty"><div class="plat">{p}</div>—</td>')
                continue
            verdict = g.get("verdict")
            vbadge = (f'<span class="verdict v-{verdict}">{verdict}'
                      + (f' · {html.escape(g["flag"])}' if g.get("flag") else "")
                      + "</span>") if verdict else ""
            cells.append(
                f'<td><div class="plat">{p}'
                f'<span class="hscore {score_class(g["eval_score"])}">'
                f'{"" if g["eval_score"] is None else round(g["eval_score"])}</span>'
                f'{vbadge}</div>'
                f'<pre class="out">{html.escape(g["generated_content"] or "")}</pre>'
                f'<div class="prov">model {html.escape(str(g["model"] or "?"))} · '
                f'prompt {html.escape(str(g["prompt_version"] or "?"))} · '
                f'voice v{g["voice_version"]}</div>'
                f'{render_judge(g["judges"])}</td>')
        rows.append(
            f'<section class="brief"><header><div class="when">'
            f'{when:%Y-%m-%d %H:%M}</div><h2>{html.escape(brief[:400])}</h2></header>'
            f'<div class="scroll"><table><tr>{"".join(cells)}</tr></table></div></section>')

    total = sum(len(v) for v in briefs.values())
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eval Log — Marketing Content Agent</title>
<style>
:root{{--cream:#F9F8F4;--forest:#1A3C34;--gold:#C5A368;--line:#e6e2d8;
--t3:#6b6b6b;--ok:#10b981;--warn:#f59e0b;--err:#ef4444;
--mono:"SF Mono",ui-monospace,Menlo,monospace}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--cream);color:#222;
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,sans-serif}}
.wrap{{max-width:1500px;margin:0 auto;padding:36px 20px 64px}}
h1{{margin:0 0 6px;font-size:27px;color:var(--forest);letter-spacing:-.02em}}
.lede{{margin:0 0 26px;color:var(--t3);font-size:14px}}
.brief{{background:#fff;border:1px solid var(--line);border-radius:13px;
margin-bottom:22px;overflow:hidden}}
.brief>header{{padding:15px 18px;background:#fbfaf6;border-bottom:1px solid var(--line)}}
.when{{font:600 10px/1 var(--mono);letter-spacing:.09em;text-transform:uppercase;
color:var(--gold);margin-bottom:6px}}
.brief h2{{margin:0;font-size:15px;font-weight:650;color:var(--forest)}}
.scroll{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%}}
td{{vertical-align:top;padding:14px;border-left:1px solid var(--line);
min-width:290px;max-width:340px}}
td:first-child{{border-left:none}}
td.empty{{color:#bbb;font-size:13px}}
.plat{{display:flex;align-items:center;gap:7px;flex-wrap:wrap;
font:600 10.5px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;
color:var(--forest);margin-bottom:9px}}
.hscore{{font-weight:700;padding:2px 7px;border-radius:5px;background:#f0ede5}}
.good{{color:var(--ok)}} .mid{{color:var(--warn)}} .bad{{color:var(--err)}}
.none{{color:#bbb}}
.verdict{{font:600 9.5px var(--mono);padding:2px 7px;border-radius:99px}}
.v-approve,.v-edit{{background:#e7f6ef;color:#0b7a58}}
.v-reject{{background:#fdecec;color:var(--err)}}
pre.out{{margin:0;white-space:pre-wrap;word-break:break-word;font:13px/1.5
-apple-system,sans-serif;background:#fbfaf6;border:1px solid #f0ece2;
border-radius:8px;padding:11px 12px;max-height:340px;overflow:auto}}
.prov{{margin-top:7px;font:10px var(--mono);color:#a09a8c}}
.judge{{margin-top:10px;border-top:1px dashed var(--line);padding-top:9px}}
.jhead{{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:6px}}
.jhead b{{font-size:15px}}
.jm{{font:10px var(--mono);color:var(--t3)}}
.safe{{font:600 9px var(--mono);padding:2px 6px;border-radius:4px}}
.safe.pass{{background:#e7f6ef;color:#0b7a58}}
.safe.fail{{background:#fdecec;color:var(--err)}}
.safe.unknown{{background:#f0ede5;color:#8a8578}}
.unknown{{font:600 10px var(--mono);color:#8a8578;background:#f0ede5;
padding:3px 8px;border-radius:5px}}
.unknown-note{{border-left-color:#cfc9ba!important;color:#8a8578!important;
font-size:11px!important}}
.cat{{display:grid;grid-template-columns:88px 32px 1fr;gap:6px;align-items:baseline;
font-size:11px;margin-bottom:3px}}
.cat span{{color:var(--t3)}} .cat b{{font:600 11px var(--mono)}}
.cat i{{color:#8a8578;font-style:normal;font-size:10.5px}}
.jsum{{margin-top:6px;font-size:11.5px;color:#4a5a54;background:#f7f5ef;
border-left:2px solid var(--gold);padding:7px 9px;border-radius:0 6px 6px 0}}
.nojudge{{font:10px var(--mono);color:#bbb}}
</style></head><body><div class="wrap">
<h1>Eval Log</h1>
<p class="lede">{len(briefs)} briefs · {total} generations · one row per brief,
channels side by side. Heuristic score, LLM judge grade, and human verdict per cell.
Generated {datetime.now():%Y-%m-%d %H:%M}.</p>
{"".join(rows) or "<p>No generations logged yet.</p>"}
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20, help="number of briefs (default 20)")
    ap.add_argument("-o", "--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    briefs = fetch(args.limit)
    out = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_html(briefs))
    total = sum(len(v) for v in briefs.values())
    print(f"wrote {out}\n  {len(briefs)} briefs · {total} generations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
