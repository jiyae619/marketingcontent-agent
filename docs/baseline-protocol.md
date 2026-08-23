# Manual "Before" Baseline Protocol

The agent's efficiency claim compares hands-on content-creation time **with** the
agent against a **manual** baseline. The manual number cannot come from the
database — the tool didn't exist in that workflow — so it must be measured
directly, once, with the team. This doc is that protocol.

Related: the instrumented "after" number is computed by
`feedback_db.hands_on_time_stats()` and surfaced at `/api/admin/stats`.

## Why measure it now

The manual baseline is recoverable at any time (anyone can write a multi-channel
set with a timer), but capturing it **before** the team's speed is shaped by the
tool avoids a learning-curve confound. If a long gap opens between this baseline
and when the instrumented cohort has enough real sessions, re-capture a small
baseline near that point so the two numbers describe the same team.

## Protocol

1. **Participants:** 3–5 team members who write marketing content.
2. **Task:** each participant writes **one full multi-channel content set** for a
   single real event/brief — the same channels the agent targets
   (LinkedIn, Instagram, CIRCLE, KakaoTalk, WhatsApp, X) — **without the agent**,
   using whatever tools they'd normally use.
3. **Timing:** start the timer when they begin working the brief; stop when the
   content set is finished to the point they'd hand it off. One timed session per
   participant (run 2–3 if time allows for a tighter median).
4. **Record:** each participant's total minutes, the channels covered, and the
   date. Compute the **median** across sessions — not the mean (robust to one
   slow or fast run).

## Metric boundary (must match the instrumented number)

Decide and record which boundary you're measuring, because the in-tool metric
(`hands_on_time_stats`) measures **content creation time** — first generation to
final approval inside the tool. It excludes the post-approval work of pasting
into each platform.

- **Creation time (default):** stop the manual timer at "content written and
  approved, ready to post." This lines up 1:1 with the instrumented metric.
- **End-to-end:** include the manual posting/scheduling into each platform. Only
  use this if the instrumented side also captures publish time (a later phase —
  scheduling/publish is not built yet). Do **not** compare an end-to-end manual
  number against the creation-only instrumented number.

## Recording the result

Record the baseline where the team tracks project metrics (e.g., append a short
row here or in your metrics sheet):

| Date | Participants | Channels | Median minutes | Boundary |
|------|--------------|----------|----------------|----------|
| _TBD_ | _n_ | _list_ | _e.g. 28_ | creation |

Until both the manual median and enough instrumented sessions exist, describe the
result as **"significantly reduced content-creation time"** rather than a specific
percentage. A specific number (e.g., "30 → 5 min, 83%") is only defensible once
it's a measured median on each side.
