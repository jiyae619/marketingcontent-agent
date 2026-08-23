"""Compare generator models on the same brief, and render the outputs as HTML.

Runs N generator models across M channels on one brief, using the SAME assembled
prompt each model would get in production (channel template + voice profile), then
scores every output with the free heuristic so the comparison is not vibes-only.

Cloud models need network — run this from a normal terminal, not a sandbox.

    python3 scripts/compare_generators.py --brief "..." \
        --models gpt-4o-mini,claude-haiku,local:qwen3:4b,local:gemma3:4b \
        --platforms instagram,linkedin

A `local:<tag>` model runs through the local endpoint with that Ollama tag, so
several local models can be compared in one run.
"""
import argparse
import html
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "testing/core"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(HERE, ".env"))

import feedback_db      # noqa: E402
import generators       # noqa: E402
import providers        # noqa: E402
from evaluators import evaluate as run_eval, strip_markdown  # noqa: E402

DEFAULT_OUT = os.path.expanduser(
    "~/dev/documents/html-previews/marketing-agent-generator-compare.html")
VOICE_EXAMPLES_LIMIT = 3


def load_channel_prompt(platform):
    """Same extraction server.py uses: the `## AI Prompt` slice of docs/<platform>.md."""
    path = os.path.join(HERE, f"docs/{platform}.md")
    content = open(path, encoding="utf-8").read()
    start = content.find("## AI Prompt")
    if start == -1:
        raise ValueError(f"no '## AI Prompt' section in {path}")
    start += len("## AI Prompt")
    nxt = content.find("\n##", start)
    return (content[start:nxt] if nxt != -1 else content[start:]).strip()


def with_voice(platform, base):
    """Mirror server.py's _with_voice_examples so the comparison is apples-to-apples."""
    style = feedback_db.get_voice_profile(platform)
    if style:
        return base + ("\n\n## Your Voice Style\n"
                       "Write in this user's established voice and style:\n\n" + style)
    return base


def resolve_spec(spec):
    """'local:qwen3:4b' -> a local call bound to that tag; otherwise a registry key."""
    if spec.startswith("local:"):
        tag = spec.split(":", 1)[1]
        return (spec, f"Local — {tag}", tag,
                lambda p, model=None, _t=tag: providers.call_local(p, model=_t))
    return generators.resolve(spec)


def run_one(spec, platform, brief):
    key, label, model_id, fn = resolve_spec(spec)
    prompt = with_voice(platform, load_channel_prompt(platform))
    full = f"{prompt}\n\n---\nUser content:\n{brief}"
    t0 = time.time()
    try:
        res = fn(full, model=model_id)
    except Exception as e:
        res = {"ok": False, "error": str(e), "cost_usd": 0.0}
    # Mirror server.py: strip on the generation path so the comparison scores what
    # would actually ship, not the raw model output.
    out = {"spec": spec, "label": label, "model": model_id, "platform": platform,
           "wall_s": round(time.time() - t0, 1), "ok": bool(res.get("ok")),
           "text": strip_markdown(res.get("text") or ""),
           "error": res.get("error"),
           "cost_usd": res.get("cost_usd") or 0.0}
    if out["ok"] and out["text"]:
        try:
            ev = run_eval(platform, out["text"])
            out["score"] = ev["total"]
            out["criteria"] = ev["criteria"]
        except Exception:
            pass
    return out


def score_class(v):
    if v is None:
        return "none"
    return "good" if v >= 70 else ("mid" if v >= 45 else "bad")


def build_html(brief, platforms, specs, results):
    by = {(r["spec"], r["platform"]): r for r in results}
    sections = []
    for p in platforms:
        cells = []
        for s in specs:
            r = by.get((s, p))
            if not r:
                continue
            if not r["ok"]:
                body = (f'<div class="err">failed<br><span>'
                        f'{html.escape(str(r.get("error"))[:180])}</span></div>')
                meta = ""
            else:
                body = f'<pre class="out">{html.escape(r["text"])}</pre>'
                crit = "".join(
                    f'<div class="c"><span>{html.escape(c["criterion"])}</span>'
                    f'<b class="{score_class(c["score"])}">{round(c["score"])}</b></div>'
                    for c in (r.get("criteria") or []))
                meta = (f'<div class="crit">{crit}</div>'
                        f'<div class="meta">{len(r["text"])} chars · {r["wall_s"]}s · '
                        f'${r["cost_usd"]:.5f}</div>')
            sc = r.get("score")
            cells.append(
                f'<td><div class="mh"><span class="ml">{html.escape(r["label"])}</span>'
                f'<span class="ms {score_class(sc)}">'
                f'{"—" if sc is None else round(sc)}</span></div>{body}{meta}</td>')
        sections.append(
            f'<section><h2>{p}</h2><div class="scroll"><table><tr>'
            f'{"".join(cells)}</tr></table></div></section>')

    total_cost = sum(r["cost_usd"] for r in results)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Generator Comparison</title><style>
:root{{--cream:#F9F8F4;--forest:#1A3C34;--gold:#C5A368;--line:#e6e2d8;--t3:#6b6b6b;
--ok:#10b981;--warn:#f59e0b;--err:#ef4444;--mono:"SF Mono",ui-monospace,Menlo,monospace}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--cream);color:#222;font:15px/1.55 -apple-system,
BlinkMacSystemFont,"Segoe UI",Helvetica,sans-serif}}
.wrap{{max-width:1600px;margin:0 auto;padding:34px 20px 64px}}
h1{{margin:0 0 6px;font-size:27px;color:var(--forest);letter-spacing:-.02em}}
.lede{{margin:0 0 8px;color:var(--t3);font-size:14px}}
.brief{{background:#fff;border:1px solid var(--line);border-left:3px solid var(--gold);
border-radius:0 10px 10px 0;padding:13px 16px;margin:16px 0 28px;font-size:14px}}
.brief b{{display:block;font:600 10px/1 var(--mono);letter-spacing:.09em;
text-transform:uppercase;color:var(--gold);margin-bottom:7px}}
section{{background:#fff;border:1px solid var(--line);border-radius:13px;
margin-bottom:20px;overflow:hidden}}
section h2{{margin:0;padding:13px 18px;background:#fbfaf6;border-bottom:1px solid var(--line);
font:600 11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--forest)}}
.scroll{{overflow-x:auto}} table{{border-collapse:collapse;width:100%}}
td{{vertical-align:top;padding:14px;border-left:1px solid var(--line);
min-width:300px;max-width:360px}}
td:first-child{{border-left:none}}
.mh{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}}
.ml{{font:600 11px var(--mono);color:var(--forest)}}
.ms{{font:700 16px var(--mono)}}
.good{{color:var(--ok)}}.mid{{color:var(--warn)}}.bad{{color:var(--err)}}.none{{color:#bbb}}
pre.out{{margin:0;white-space:pre-wrap;word-break:break-word;font:13px/1.5 -apple-system,
sans-serif;background:#fbfaf6;border:1px solid #f0ece2;border-radius:8px;
padding:11px 12px;max-height:420px;overflow:auto}}
.crit{{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}}
.c{{display:flex;gap:5px;align-items:baseline;background:#f4f2ea;border-radius:5px;
padding:3px 7px;font-size:10.5px}}
.c span{{color:var(--t3)}} .c b{{font:600 10.5px var(--mono)}}
.meta{{margin-top:6px;font:10px var(--mono);color:#a09a8c}}
.err{{background:#fdf1f1;border:1px solid #f3d4d4;border-radius:8px;padding:11px;
color:var(--err);font-size:12.5px}}
.err span{{color:#a06a6a;font-size:11px}}
</style></head><body><div class="wrap">
<h1>Generator Comparison</h1>
<p class="lede">{len(specs)} models × {len(platforms)} channels · same brief, same
assembled prompt (channel template + voice profile) · scored by the free heuristic ·
total cost ${total_cost:.4f} · {datetime.now():%Y-%m-%d %H:%M}</p>
<div class="brief"><b>Brief</b>{html.escape(brief)}</div>
{"".join(sections)}
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", required=True)
    ap.add_argument("--models", default="gpt-4o-mini,claude-haiku,local:qwen3:4b,local:gemma3:4b")
    ap.add_argument("--platforms", default="instagram,linkedin")
    ap.add_argument("-o", "--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    specs = [s.strip() for s in args.models.split(",") if s.strip()]
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]

    jobs = [(s, p) for p in platforms for s in specs]
    cloud = [j for j in jobs if not j[0].startswith("local:") and j[0] != "local"]
    local = [j for j in jobs if j[0].startswith("local:") or j[0] == "local"]
    print(f"running {len(jobs)} generations ({len(specs)} models × {len(platforms)} channels)…")

    results = []
    # Cloud calls are network-bound, so parallelism is free. Local calls are
    # memory-bound: running two 2.5GB models at once on a small machine swaps and
    # both time out. Ollama serialises model loads anyway, so fan-out buys nothing.
    if cloud:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results += list(pool.map(lambda j: run_one(j[0], j[1], args.brief), cloud))
    for j in local:
        print(f"  … {j[0]} / {j[1]} (serial — local models load one at a time)")
        results.append(run_one(j[0], j[1], args.brief))

    for r in results:
        status = f"{r.get('score', 0):.0f}/100" if r["ok"] else f"FAILED: {str(r.get('error'))[:60]}"
        print(f"  {r['platform']:<10} {r['label']:<24} {status}  ({r['wall_s']}s)")

    out = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_html(args.brief, platforms, specs, results))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
