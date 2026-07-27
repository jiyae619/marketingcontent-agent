# Published posts — voice corpus source

Real, already-published PKNIC content. This is **not** the golden set: these are all
positives by definition (published means it passed), so they can't measure whether the
judge is right. They exist to teach the agent the real voice.

## How to add posts

Open the file for a channel and paste posts below, separated by the delimiter:

```
--- POST ---
```

Keep them **verbatim** — line breaks, emoji, hashtags, and spacing all carry voice.
Don't clean them up.

## How many

~14 per channel is plenty. The seeding script splits each channel deterministically:

| Split | Count | Used for |
|---|---|---|
| voice seed | 5 | Synthesized into `voice_profile_versions` v1 |
| held-out anchor | 4 | Pairwise "is the agent as good as a real post?" |
| defect substrate | 5 | Clean base for injecting known flaws → golden-set negatives |

The splits must stay **disjoint** — grading the agent against posts it was voice-trained
on scores it against its own training data. The script enforces this; don't pre-assign
posts yourself.

## Curation matters more than volume

Pick posts that represent the voice you **want**, not everything that shipped. A weak
old post teaches weak voice exactly as effectively as a good one teaches good voice.
This is the part that can't be automated.

## Channels

| File | Status |
|---|---|
| `linkedin.md` | active |
| `instagram.md` | active |
| `circle.md` | active |
| `kakaotalk.md` | active |
| — X | **no PKNIC presence** — voice inherited, see below |
| — WhatsApp | **no PKNIC presence** — voice inherited, see below |

### Channels with no presence yet

X and WhatsApp get no file, because there's nothing authentic to seed from. They are
handled by a deliberate split:

- **Format norms** — length, threading, emoji density, CTA placement — derived from
  reference accounts. These are platform conventions, not anyone's identity.
- **Voice** — transferred from the channels that *do* exist (LinkedIn / KakaoTalk).
  Never borrowed from a reference brand, which would train toward *their* identity and
  push all six channels toward generic sameness.

Their profiles get marked `voice: inherited` so native voice stays distinguishable from
transferred voice later.
