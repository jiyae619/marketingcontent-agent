# CLAUDE.md — marketingcontent

Project rules. These override defaults. Every rule below exists because it was
already broken once — the note in parentheses is the incident.

## Before doing anything

Run `python3 scripts/preflight.py` and paste its output. It prints the resolved
generator, judge, and billing state, and exits non-zero on a violation. Do this before
any generation, judge run, or model comparison. Do not describe the config from memory
or from `.env` — print the *resolved* values, because `.env` has fallbacks that hide
what actually runs.

## Hard constraints — check, never assume

1. **Machine is an 8GB M3.** Local models: **4B tier only** (~3.3GB max). Never propose
   7B or larger. A 4B at ctx 8192 uses ~3.6GB and leaves ~16% free; two models cannot
   co-reside. (I recommended qwen2.5:7b and gemma2:9b without checking the RAM.)

2. **`LOCAL_ONLY=true`. No paid API call, ever — including for testing.** If a task
   seems to need one, stop and ask; do not disable the flag. (I set
   `JUDGE_MODEL=claude-haiku` after being told local-only.)

3. **Generator and judge must be different models.** Set `LOCAL_JUDGE_MODEL`
   explicitly; never rely on its fallback to `LOCAL_LLM_MODEL`. When calling
   `judge.judge()`, pass the **real** `generator_model` — never a hand-typed value.
   (I passed `generator_model="gemini-2.5-flash"` for content gemma3:4b wrote, which
   disabled the judge != generator guard and let a model grade its own output.)

4. **Output is never markdown. Instructions may be.** `strip_markdown()` takes no
   platform argument and has no exceptions. If a scorer seems to require markdown, fix
   the scorer — not the content rule. (I kept `##` on circle to protect a scorer.)

5. **Prompts and scorers must agree.** A prompt target and its scorer band are one
   decision in two files; changing either alone is a bug. Korean and English have
   separate length bands — check both. (Korean targets sat below the scorer's zero
   floor on 5 of 6 channels, zeroing 30–55% of the weight.)

## Evidence rules

6. **Show the command and its real output.** Never report a conclusion without the
   output that produced it.

7. **Show the reasoning chain, not just the verdict.** Write it as
   *checked X → output showed Y → therefore Z*, so the logic can be followed and
   challenged. A bare conclusion is not reviewable. If a step is an assumption rather
   than a measurement, label it as one.

8. **Never truncate evidence when claiming absence.** No `head -N` on a search whose
   result is "nothing found" or "the rest are clean." (I claimed 5 docs were clean
   from a grep piped through `head -6`; WhatsApp had a direct contradiction.)

9. **Measure the artifact actually sent to the model.** The prompt is the `## AI Prompt`
   slice plus the voice profile — not the whole `.md` file. (I measured whole files and
   raised a context-truncation risk that did not exist.)

10. **State what was NOT verified.** Say plainly which paths are untested and why,
    especially anything behind `LOCAL_ONLY`.

## Corrections

When a claim turns out wrong, correct it in one line at the top of the reply and move
on. No re-litigating. If a correction changes an earlier recommendation, say which one.
