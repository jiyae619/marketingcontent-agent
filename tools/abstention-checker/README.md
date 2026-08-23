# Should Your LLM Judge Have Answered That?

A pre-flight check for LLM-as-judge rubrics. Paste your criteria, tick what you
actually pass the judge at call time, and it tells you which criteria are
**structurally unverifiable** — plus emits the abstention guard as code.

Single self-contained HTML file. No build, no backend, no API key, no signup.
Runs entirely client-side.

```
open index.html
# or, to serve it:
python3 -m http.server 8899
```

## The idea

A rubric contains two kinds of criteria:

- **Intrinsic** — judgable from the artifact alone. Grammar, tone, toxicity.
  The text in front of the judge is the whole evidence base.
- **Relative** — defined *against something else*. "Accurate" means accurate
  *to a source*. "Complete" means complete *relative to a request*. If that
  referent is not in the judge's context, the criterion isn't hard to judge,
  it's impossible to judge.

The tool adds two more verdicts that come up constantly in real rubrics:

- **Unobservable** — outcome criteria (engagement, conversion, satisfaction).
  No judge reading text can see these. Measure them, don't grade them.
- **Vague** — evaluative words with no shared definition ("quality", "helpful",
  "natural"). Not a blocker, but the scores will be unstable across models,
  across runs, and across teammates.

## Why it has to be enforced in code

The judge will score an unverifiable criterion anyway, confidently.

This tool was extracted from a production content-evaluation harness where
exactly that happened: a local model asked to grade grounding with
`source_brief=None` returned `confidence: "medium"` and `overall: 80` — a
confident number for a property it had no way to observe. It did not hedge, and
nothing downstream could distinguish that verdict from a real one.

Prompting harder does not fix this. Asking a model to notice its own blind spot
is asking the blind spot to report itself. **Whether the referent was supplied is
a fact the calling code already knows**, so the calling code enforces the
abstention — deterministically, before any score is trusted.

The second-order consequence is the one people miss: a contaminated criterion
doesn't just invalidate itself. If you average criteria into an overall score, or
gate a safety decision on a family of them, one unverifiable criterion
contaminates the aggregate — and the aggregate is usually the number that ships.
So `apply_abstention()` nulls `overall` and `safety_pass`, not just the
offending sub-score.

## Provenance

The abstention rule this emits is the one that shipped in `judge.py` after the
incident above. See `../../CLAUDE.md` for the full incident list.

## Extracting this

Self-contained by design — `cp -r` this folder and it is its own repo. It has no
dependency on anything else in `marketingcontent`, and contains no PKNIC brand
data, voice corpus, or client content.
