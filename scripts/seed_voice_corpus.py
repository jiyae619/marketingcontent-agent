"""Parse real published posts into a voice corpus, with a deterministic role split.

Reads testing/test_data/published/<platform>.md (posts separated by `--- POST ---`),
normalizes copy-paste artifacts, and splits each channel into three DISJOINT roles:

    voice_seed  -> synthesized into voice_profile_versions (steers generation)
    anchor      -> held out for pairwise "is the agent as good as a real post?"
    substrate   -> clean base for injecting known defects -> golden-set negatives

The splits must stay disjoint: grading the agent against posts it was voice-trained
on scores it against its own training data. The split is content-hash ordered, so it
is stable across runs and reproducible.

The .md files are the human-owned raw archive — this never writes back to them.

Usage:
    python3 scripts/seed_voice_corpus.py            # dry run: report + split preview
    python3 scripts/seed_voice_corpus.py --json     # emit normalized corpus as JSON
"""
import argparse
import glob
import hashlib
import html
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from dotenv import load_dotenv           # noqa: E402
load_dotenv(os.path.join(HERE, '.env'))

import feedback_db                       # noqa: E402
import providers                         # noqa: E402

CORPUS_DIR = os.path.join(HERE, 'testing/test_data/published')
DELIMITER = '--- POST ---'

# Role split for a channel with enough posts to serve all three roles.
SPLIT_RATIOS = (('voice_seed', 0.4), ('anchor', 0.3), ('substrate', 0.3))

# Below this, a channel is VOICE-ONLY: every post seeds the voice profile and no
# anchor/substrate is carved out. The three roles are not equally urgent — anchors
# and substrate feed evaluation (blocked until the golden set has negatives), while
# voice seeding pays off on the next generation. Splitting a tiny corpus three ways
# produces a weak voice profile AND eval sets too small to mean anything.
# Posts added later become naturally held-out anchors, which is what you want anyway.
VOICE_ONLY_BELOW = 10

# Minimum posts before a channel can seed a voice profile at all.
MIN_FOR_VOICE = 3

# Platform UI labels that get copied along with the post body (Circle renders a
# "Details" section heading above the content). Leading-position only — the word
# is legitimate mid-post.
UI_LABELS = ('Details', 'About', 'Description')

# LinkedIn has no rich text, so authors fake bold with Unicode math alphanumerics
# (U+1D400–U+1D7FF): "𝗙𝗿𝗼𝗺 𝗦𝗲𝗹𝗳-𝗕𝗿𝗮𝗻𝗱𝗶𝗻𝗴". Folded to ASCII because a model reproduces
# these glyphs unreliably — a partial substitution ("𝗙𝗿𝗼𝗺 Self-Branding") looks worse
# than either extreme — and they break screen readers and character counts. The
# stylistic intent still reaches the profile as prose ("uses emphasized headers").
# Set False to preserve the glyphs verbatim.
FOLD_PSEUDO_BOLD = True


def parse_file(path):
    """Split one channel file into raw post strings (header discarded).

    Splits only on the delimiter as a standalone LINE. Splitting on the bare
    substring also matches the `--- POST ---` written inline in each file's own
    header instructions, which silently injects template boilerplate into the
    corpus as if it were a published post.
    """
    raw = open(path, encoding='utf-8').read()
    blocks = re.split(rf'^{re.escape(DELIMITER)}\s*$', raw, flags=re.M)[1:]  # [0] is the header
    return [b.strip() for b in blocks if b.strip('⠀ \n\t')]


def normalize(text):
    """Strip copy-paste artifacts while preserving voice-bearing content.

    Keeps: emoji, line breaks, bullets, hashtags, Korean/English mix, structure.
    Strips: markdown emphasis/heading markers, markdown line-break backslashes,
    braille-blank padding, link syntax (keeps the label), angle-bracketed URLs.

    Markdown markers are stripped rather than kept because they are an artifact of
    how the post was COPIED, not how it was published — and leaving them in teaches
    the model to emit literal `**` into a KakaoTalk message.
    """
    t = html.unescape(text)                        # &#xB300; -> 대, &#xA0; -> nbsp
    t = t.replace(' ', ' ')                   # nbsp -> plain space
    t = t.replace('⠀', '')                         # braille-blank padding
    t = re.sub(r'\\\n', '\n', t)                   # markdown hard-break backslash
    t = re.sub(r'\\$', '', t, flags=re.M)
    t = re.sub(r'^#{1,6}\s+', '', t, flags=re.M)   # heading markers
    t = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', t)  # [label](url) -> label
    t = re.sub(r'<(https?://[^>]+)>', r'\1', t)     # <url> -> url
    t = re.sub(r'<([^@>]+@[^>]+)>', r'\1', t)       # <email> -> email
    t = re.sub(r'\*{1,3}', '', t)                   # bold/italic markers
    t = re.sub(r'^>\s?', '', t, flags=re.M)         # blockquote markers
    if FOLD_PSEUDO_BOLD:
        t = ''.join(unicodedata.normalize('NFKC', ch)
                    if 0x1D400 <= ord(ch) <= 0x1D7FF else ch
                    for ch in t)
    # Platform UI labels copied in with the body. Circle renders "Details" as its
    # own line — sometimes above the post, sometimes under a title — so drop the
    # label wherever it stands alone rather than only at the start.
    t = '\n'.join(ln for ln in t.split('\n') if ln.strip() not in UI_LABELS)
    t = re.sub(r'\n{3,}', '\n\n', t)                # collapse blank runs
    return t.strip()


def quality_flags(text):
    """Problems that make a post unsafe to train voice on."""
    flags = []
    if '�' in text:
        flags.append('LOSSY: contains U+FFFD replacement chars — Korean destroyed, re-paste needed')
    if re.search(r'&#x[0-9A-Fa-f]+;', text):
        flags.append('undecoded HTML entities remain')
    if len(text) < 100:
        flags.append(f'very short ({len(text)} chars) — weak voice signal')
    return flags


def split_roles(posts):
    """Deterministic, disjoint role assignment ordered by content hash.

    Hash ordering (not recency, not length) so the assignment is reproducible across
    runs and carries no selection bias — but note it is arbitrary, not curated.

    Small channels go voice-only; see VOICE_ONLY_BELOW.
    """
    ordered = sorted(posts, key=lambda p: hashlib.sha256(p.encode()).hexdigest())
    n = len(ordered)
    if n < VOICE_ONLY_BELOW:
        return {'voice_seed': ordered, 'anchor': [], 'substrate': []}

    out, start = {}, 0
    for i, (role, ratio) in enumerate(SPLIT_RATIOS):
        # last role absorbs the remainder so nothing is dropped
        end = n if i == len(SPLIT_RATIOS) - 1 else start + max(1, round(n * ratio))
        out[role] = ordered[start:min(end, n)]
        start = min(end, n)
    return out


def build():
    corpus = {}
    for path in sorted(glob.glob(os.path.join(CORPUS_DIR, '*.md'))):
        platform = os.path.splitext(os.path.basename(path))[0]
        if platform == 'README':
            continue
        raw_posts = parse_file(path)
        entries = []
        for raw in raw_posts:
            clean = normalize(raw)
            entries.append({'text': clean, 'chars': len(clean), 'flags': quality_flags(clean)})
        corpus[platform] = entries
    return corpus


def build_prompt(platform, seed_posts):
    """The exact prompt sent to the model. Separated from the call so `--explain`
    can show it verbatim without spending anything."""
    samples = "\n\n---\n".join(f"Sample {i+1}:\n{p}" for i, p in enumerate(seed_posts))
    return (
        f"You are analyzing real published posts from a brand's {platform} channel "
        f"to extract its voice profile.\n\n"
        f"Platform: {platform}\n\n"
        f"Samples:\n{samples}\n\n"
        f"Write a concise voice profile (4-6 sentences, under 160 words) describing:\n"
        f"- Sentence length and rhythm\n"
        f"- Tone (formal/casual, direct/warm, etc.)\n"
        f"- Characteristic words, phrases, or patterns\n"
        f"- Language mix (Korean/English) and formality register "
        f"(존댓말/반말), including when each is used\n"
        f"- What they emphasize and what they avoid\n\n"
        f"Return ONLY the voice profile description, nothing else."
    )


def synthesize(platform, seed_posts):
    """Compress this channel's voice_seed posts into a voice profile.

    Mirrors server.py's _maybe_synthesize_voice prompt, adapted for published brand
    posts rather than approved agent copies, plus an explicit language/formality
    dimension — that is what the kr_en_register judge criterion grades against.
    Uses providers.call_gemini (the newer abstraction) so cost is tracked.
    """
    return providers.call_gemini(build_prompt(platform, seed_posts))


def run_explain(corpus, target):
    """Show exactly which posts land in which role, and the exact prompt sent.

    Everything the synthesis depends on is inspectable here without spending a call.
    """
    for platform, entries in sorted(corpus.items()):
        if target != 'ALL' and platform != target:
            continue
        usable = [e['text'] for e in entries
                  if not any(f.startswith('LOSSY') for f in e['flags'])]
        roles = split_roles(usable)
        mode = 'VOICE-ONLY (below split threshold)' if len(usable) < VOICE_ONLY_BELOW \
               else f'3-way split ({int(SPLIT_RATIOS[0][1]*100)}/'\
                    f'{int(SPLIT_RATIOS[1][1]*100)}/{int(SPLIT_RATIOS[2][1]*100)})'
        print(f'\n{"="*72}\n{platform.upper()} — {len(usable)} usable · {mode}\n{"="*72}')
        for role, posts in roles.items():
            print(f'\n  {role} ({len(posts)})')
            for i, p in enumerate(posts, 1):
                first = ' '.join(p.split())[:88]
                print(f'    [{i}] {first}…')

        if target != 'ALL' and roles['voice_seed']:
            print(f'\n{"-"*72}\nEXACT PROMPT SENT FOR {platform.upper()}\n{"-"*72}')
            print(build_prompt(platform, roles['voice_seed']))
    if target == 'ALL':
        print('\nPass a platform name to also dump the exact prompt, '
              'e.g. --explain kakaotalk')
    return 0


def run_synthesis(corpus, write=False):
    """Generate (and optionally persist) one voice profile per channel."""
    mode = 'WRITE — profiles will be saved' if write else 'PREVIEW — nothing saved'
    print(f'VOICE PROFILE SYNTHESIS  [{mode}]\n')
    total_cost = 0.0
    for platform, entries in sorted(corpus.items()):
        usable = [e['text'] for e in entries
                  if not any(f.startswith('LOSSY') for f in e['flags'])]
        if len(usable) < MIN_FOR_VOICE:
            print(f'{platform}: skipped — only {len(usable)} usable posts '
                  f'(need {MIN_FOR_VOICE})\n')
            continue

        seed = split_roles(usable)['voice_seed']
        res = synthesize(platform, seed)
        if not res.get('ok'):
            print(f'{platform}: FAILED — {res.get("error")}\n')
            continue

        total_cost += res['cost_usd']
        profile = res['text'].strip()
        print(f'── {platform}  ({len(seed)} seed posts → {len(profile)} chars, '
              f'${res["cost_usd"]:.5f}, {res["latency_ms"]}ms)')
        print(f'{profile}\n')

        if write:
            feedback_db.save_voice_profile(platform, profile, based_on=len(seed))
            print(f'   ✓ saved (based_on={len(seed)} published posts)\n')

    print(f'Total cost: ${total_cost:.5f}')
    if not write:
        print('\nRe-run with --write to save these profiles.')
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true', help='emit normalized corpus as JSON')
    ap.add_argument('--synthesize', action='store_true', help='generate voice profiles (preview)')
    ap.add_argument('--write', action='store_true', help='with --synthesize: save profiles to the DB')
    ap.add_argument('--explain', nargs='?', const='ALL', metavar='PLATFORM',
                    help='show role assignment; name a platform to dump its exact prompt')
    args = ap.parse_args()

    corpus = build()
    if args.json:
        print(json.dumps(corpus, ensure_ascii=False, indent=2))
        return 0

    if args.explain:
        return run_explain(corpus, args.explain)

    if args.synthesize:
        return run_synthesis(corpus, write=args.write)

    total_ok = total_bad = 0
    print('VOICE CORPUS — parse + normalize + split (dry run, nothing written)\n')
    for platform, entries in corpus.items():
        usable = [e for e in entries if not any(f.startswith('LOSSY') for f in e['flags'])]
        lossy = [e for e in entries if any(f.startswith('LOSSY') for f in e['flags'])]
        total_ok += len(usable)
        total_bad += len(lossy)

        status = 'ok' if len(usable) >= MIN_FOR_VOICE else f'NEEDS {MIN_FOR_VOICE - len(usable)} MORE'
        print(f'{platform:<12} {len(entries):>2} parsed · {len(usable):>2} usable · {len(lossy):>2} lossy   [{status}]')

        if usable:
            roles = split_roles([e['text'] for e in usable])
            bits = ' · '.join(f'{r} {len(v)}' for r, v in roles.items())
            print(f'{"":<12} split: {bits}')
        for e in lossy:
            print(f'{"":<12}   ⚠ {e["flags"][0]}')
            print(f'{"":<12}     preview: {e["text"][:70]}...')
        other = [(e, f) for e in entries for f in e['flags'] if not f.startswith('LOSSY')]
        for e, f in other:
            print(f'{"":<12}   · {f}')
        print()

    print(f'TOTAL: {total_ok} usable, {total_bad} need re-paste')
    if total_bad:
        print('\nRe-paste the lossy posts before seeding — U+FFFD is unrecoverable,')
        print('and training voice on corrupted Korean teaches corrupted Korean.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
