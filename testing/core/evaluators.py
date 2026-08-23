"""
Weighted 0-100 evaluators for marketing content quality.

Each platform defines a list of Criterion objects with a weight and a scorer.
Total score is the weighted sum of criterion scores (each 0-100).

Result format is backwards-compatible with report_generator.py:
{
    'criterion': str,
    'passed': bool,        # score >= 70 → passed
    'message': str,
    'score': float,        # 0-100
    'suggestion': str,
    'actual': str,
    'expected': str,
    'weight': float,       # 0-1, sums to 1.0 per platform
    'weighted_score': float,  # score * weight
}
"""

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002600-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA70-\U0001FAFF"
    "]+",
    flags=re.UNICODE,
)

HASHTAG_RE = re.compile(r"#\w+")
SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
THREAD_MARKER_RE = re.compile(r"\b\d+/\d*\b|🧵")


def count_chars(content: str) -> int:
    return len(content)


def count_words(content: str) -> int:
    return len(content.strip().split())


def count_sentences(content: str) -> int:
    return len([s for s in SENTENCE_SPLIT_RE.split(content) if s.strip()])


def count_hashtags(content: str) -> int:
    return len(HASHTAG_RE.findall(content))


def count_emojis(content: str) -> int:
    return sum(len(m) for m in EMOJI_RE.findall(content))


ORPHAN_MAX_CHARS = 12

# Most of these channels don't render markdown — "**일시:**" publishes with the
# asterisks visible. Models echo markdown because the prompt itself is written in it,
# so this has to be caught, not just forbidden. Only linkedin and instagram apply this
# via format_quality_scorer; circle is excluded on purpose (see RENDERS_MARKDOWN).
MARKDOWN_LEAK_RE = re.compile(r"\*\*|^#{1,6}\s|\[[^\]]+\]\([^)]+\)", re.M)

def strip_markdown(content: str) -> str:
    """Delete every markdown artifact from generated content. One rule, all channels.

    Instructions may be written in markdown; published output never is. There are no
    per-platform exceptions — an exception is what let `##` and `*bold*` back into the
    prompts and put them in conflict with each other.

    The prompts already forbid markdown, but asking is not enough: on one 6-channel
    brief gemma3:4b emitted 33 `**` artifacts to Gemini's 5. Removing them is a pure
    text transform, so code does it rather than a model.

    Deliberately NOT touched:
      - Single-asterisk bullets — has_bullets() accepts `*` as valid, so rewriting
        them would fight the format scorer.
      - Hashtags — `#PKNIC` has no space after the hash, so the heading rule below
        cannot match it.
    """
    if not content:
        return content
    # Links first: they contain the brackets and parens the later rules would split.
    # Keep the URL — the cta scorer looks for a link, and a post needs the address.
    s = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: (m.group(2) if m.group(1).strip() in ("", m.group(2).strip())
                   else f"{m.group(1)}: {m.group(2)}"),
        content,
    )
    s = s.replace("**", "")                          # bold, paired or orphaned
    return re.sub(r"^#{1,6}\s+", "", s, flags=re.M)  # ATX headings


HANGUL_RE = re.compile(r"[가-힣]")


def is_korean(content: str) -> bool:
    """True when the content is Korean-dominant.

    Every prompt says "write in the SAME language as the input" and then gives TWO
    length targets — an English one and a Korean one ~2.5x shorter. A single band
    therefore cannot be right for both; scoring Korean output against the English
    band is what zeroed `length` on 5 of 6 channels. 10% Hangul is well clear of a
    Korean post that quotes an English venue name, and of English copy that carries
    one Korean word.
    """
    if not content:
        return False
    letters = [c for c in content if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if HANGUL_RE.match(c)) / len(letters) > 0.10


EVENT_INFO_RE = re.compile(
    r"\d{1,2}\s*월\s*\d{1,2}\s*일|\d{1,2}/\d{1,2}|"
    r"\d{1,2}(:\d{2})?\s*(AM|PM|am|pm)|\d{1,2}\s*시\b|"
    r"📅|🗓|📍|⏰|🎟|장소|일시|참가비"
)


def find_orphan_lines(content: str) -> List[str]:
    """Lines holding a single short stranded word — the widow/orphan problem.

    Only counts a lone word as orphaned when the PREVIOUS line has text: that is a
    wrapped continuation that got stranded. A lone word after a blank line is a
    deliberate standalone line, not an orphan. Skips URLs, hashtags, bullets, and
    emoji-only lines, which are legitimately alone.
    """
    lines = content.split("\n")
    orphans = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or i == 0 or not lines[i - 1].strip():
            continue
        tokens = stripped.split()
        if len(tokens) != 1:
            continue
        word = tokens[0]
        if len(word) > ORPHAN_MAX_CHARS or URL_RE.search(word) or word.startswith("#"):
            continue
        if word[0] in "-*·•✅✔▸▶":
            continue
        if not EMOJI_RE.sub("", word).strip():      # emoji-only line
            continue
        orphans.append(word)
    return orphans


def has_event_info(content: str) -> bool:
    """Content carries logistics (date / time / location / price)."""
    return len(EVENT_INFO_RE.findall(content)) >= 2


def has_structured_lines(content: str, minimum: int = 2) -> bool:
    """Content presents items one-per-line with a leading marker.

    Broader than has_bullets() on purpose: an emoji-led line (🗓 7월 12일 / 📍 Impact
    House) is a bullet in social copy, and it is the style these channels actually
    use. Judging that as "prose" would penalise the exact formatting the prompt asks
    for.
    """
    count = 0
    for line in content.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s[0] in "-*·•✅✔▸▶" or re.match(r"^\d+[.)]", s) or EMOJI_RE.match(s):
            count += 1
    return count >= minimum


def has_bullets(content: str) -> bool:
    return bool(re.search(r"^[•\-\*]\s|\n[•\-\*]\s", content))


def has_headers(content: str) -> bool:
    """A section header: a `##` line, or a short standalone line ending in a colon.

    The old fallback was `^[A-Z][^.!?]*:$` — ASCII-only, so a Korean header like
    `이벤트 상세:` never matched and Korean circle posts could satisfy this ONLY by
    emitting `##`. That forced markdown into the output to score structure. The
    pattern below is script-agnostic: any line that is a short label ending in a
    colon, with nothing after it. `날짜: 7월 26일` is a bullet, not a header, and is
    correctly excluded because content follows the colon.
    """
    if "##" in content:
        return True
    return bool(re.search(r"^[^\s#][^\n.!?]{0,40}:[ \t]*$", content, re.MULTILINE))


def has_url(content: str) -> bool:
    return bool(URL_RE.search(content))


def trapezoid_score(value: float, low_zero: float, low_ideal: float,
                    high_ideal: float, high_zero: float) -> float:
    """Trapezoidal scoring:
      0 at value<=low_zero or value>=high_zero
      100 between low_ideal and high_ideal
      linear ramps on the flanks.
    """
    if value <= low_zero or value >= high_zero:
        return 0.0
    if low_ideal <= value <= high_ideal:
        return 100.0
    if value < low_ideal:
        return ((value - low_zero) / (low_ideal - low_zero)) * 100.0
    return ((high_zero - value) / (high_zero - high_ideal)) * 100.0


def ramp_down_score(value: float, ideal_max: float, zero_at: float) -> float:
    """Returns 100 when value <= ideal_max, 0 at value >= zero_at, linear between."""
    if value <= ideal_max:
        return 100.0
    if value >= zero_at:
        return 0.0
    return ((zero_at - value) / (zero_at - ideal_max)) * 100.0


def keyword_density_score(content: str, keywords: List[str],
                          ideal_min: int = 2, ideal_max: int = 5) -> tuple:
    """Returns (score, found_keywords) — score scales with how many keywords appear."""
    content_lower = content.lower()
    found = [k for k in keywords if k in content_lower]
    n = len(found)
    if ideal_min <= n <= ideal_max:
        return 100.0, found
    if n < ideal_min:
        return (n / ideal_min) * 100.0, found
    # Too many — gentle penalty
    return max(0.0, 100.0 - (n - ideal_max) * 10.0), found


# ---------------------------------------------------------------------------
# Criterion + base evaluator
# ---------------------------------------------------------------------------

@dataclass
class CriterionResult:
    criterion: str
    score: float
    weight: float
    message: str
    suggestion: str = ""
    actual: str = ""
    expected: str = ""

    @property
    def passed(self) -> bool:
        return self.score >= 70.0

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight

    def to_dict(self) -> Dict:
        return {
            "criterion": self.criterion,
            "score": round(self.score, 1),
            "weight": self.weight,
            "weighted_score": round(self.weighted_score, 2),
            "passed": self.passed,
            "message": self.message,
            "suggestion": self.suggestion,
            "actual": self.actual,
            "expected": self.expected,
        }


@dataclass
class Criterion:
    name: str
    weight: float  # 0-1
    scorer: Callable[[str], CriterionResult]


class ChannelEvaluator:
    """Base evaluator. Subclasses just define `criteria`."""

    platform: str = ""
    criteria: List[Criterion] = field(default_factory=list)

    def evaluate(self, content: str) -> List[Dict]:
        results = []
        for c in self.criteria:
            r = c.scorer(content)
            r.weight = c.weight  # ensure weight is set
            results.append(r.to_dict())
        return results

    def total_score(self, content: str) -> float:
        results = self.evaluate(content)
        return round(sum(r["weighted_score"] for r in results), 1)


# ---------------------------------------------------------------------------
# Reusable scorer factories
# ---------------------------------------------------------------------------

def char_length_scorer(low_zero, low_ideal, high_ideal, high_zero, weight, ko=None):
    """Character-count band. `ko` is an optional (zero, ideal, ideal, zero) tuple
    used when the content is Korean — the prompts give a separate, ~2.5x shorter
    Korean target, and grading Korean output against the English band zeroed it."""
    def scorer(content: str) -> CriterionResult:
        n = count_chars(content)
        lo_z, lo_i, hi_i, hi_z = (ko if (ko and is_korean(content))
                                  else (low_zero, low_ideal, high_ideal, high_zero))
        score = trapezoid_score(n, lo_z, lo_i, hi_i, hi_z)
        lang = "KR" if (ko and is_korean(content)) else "EN"
        return CriterionResult(
            criterion="length",
            score=score,
            weight=weight,
            message=f"Character count: {n} ({lang} target)",
            actual=str(n),
            expected=f"{lo_i}-{hi_i} chars (acceptable {lo_z}-{hi_z}, {lang})",
            suggestion=(
                f"Add ~{lo_i - n} more chars." if n < lo_i
                else f"Trim ~{n - hi_i} chars." if n > hi_i
                else "Length is in the sweet spot."
            ),
        )
    return scorer


def word_length_scorer(low_zero, low_ideal, high_ideal, high_zero, weight):
    def scorer(content: str) -> CriterionResult:
        n = count_words(content)
        score = trapezoid_score(n, low_zero, low_ideal, high_ideal, high_zero)
        return CriterionResult(
            criterion="length",
            score=score,
            weight=weight,
            message=f"Word count: {n}",
            actual=str(n),
            expected=f"{low_ideal}-{high_ideal} words",
            suggestion=(
                f"Add ~{low_ideal - n} more words." if n < low_ideal
                else f"Trim ~{n - high_ideal} words." if n > high_ideal
                else "Length is in the sweet spot."
            ),
        )
    return scorer


def sentence_max_scorer(ideal_max: int, zero_at: int, weight: float):
    def scorer(content: str) -> CriterionResult:
        n = count_sentences(content)
        score = ramp_down_score(n, ideal_max, zero_at)
        return CriterionResult(
            criterion="sentence_count",
            score=score,
            weight=weight,
            message=f"Sentence count: {n}",
            actual=str(n),
            expected=f"≤{ideal_max} sentences",
            suggestion=(
                "Within sentence limit." if n <= ideal_max
                else f"Cut {n - ideal_max} sentence(s) — combine ideas."
            ),
        )
    return scorer


def hard_char_cap_scorer(cap: int, weight: float, ideal=None, ko=None):
    """Hard platform limit (X = 280). Above cap = hard 0.

    `ideal` / `ko` are (low, high) sweet-spot bands. The old version derived the band
    as "last 80% of cap" (224–280 for X), which inverted the prompt: docs/x.md asks
    for 100–150 chars and calls 220–275 the concession for logistics-heavy posts. A
    54-char Korean post scored 24.1 for being exactly what it was told to be.
    """
    def scorer(content: str) -> CriterionResult:
        n = count_chars(content)
        band = ko if (ko and is_korean(content)) else (ideal or (int(cap * 0.80), cap))
        lang = "KR" if (ko and is_korean(content)) else "EN"
        lo, hi = band
        if n > cap:
            score = 0.0
            msg = f"OVER LIMIT: {n}/{cap} chars"
            sug = f"Cut {n - cap} chars — X enforces this limit."
        else:
            score = trapezoid_score(n, 0, lo, hi, cap + 1)
            msg = f"Char count: {n}/{cap} ({lang} target)"
            sug = "Tight and punchy." if score >= 70 else f"Aim for {lo}-{hi} chars."
        return CriterionResult(
            criterion="char_cap",
            score=score,
            weight=weight,
            message=msg,
            actual=str(n),
            expected=f"≤{cap} chars (ideal {lo}-{hi}, {lang})",
            suggestion=sug,
        )
    return scorer


def hashtag_count_scorer(ideal_min: int, ideal_max: int, weight: float,
                         zero_above: Optional[int] = None):
    def scorer(content: str) -> CriterionResult:
        n = count_hashtags(content)
        if ideal_min <= n <= ideal_max:
            score = 100.0
        elif n < ideal_min:
            score = (n / max(ideal_min, 1)) * 100.0 if ideal_min > 0 else 100.0
        else:
            zero = zero_above if zero_above else ideal_max * 3
            score = max(0.0, ((zero - n) / (zero - ideal_max)) * 100.0)
        # Special case: ideal_min == 0 and ideal_max == 0 → "no hashtags allowed"
        if ideal_min == 0 and ideal_max == 0:
            score = 100.0 if n == 0 else max(0.0, 100.0 - n * 25.0)
        return CriterionResult(
            criterion="hashtags",
            score=score,
            weight=weight,
            message=f"Hashtag count: {n}",
            actual=str(n),
            expected=f"{ideal_min}-{ideal_max} hashtags" if ideal_max > 0 else "0 hashtags",
            suggestion=(
                "Hashtag use is on target." if score >= 70
                else "Remove hashtags — they don't fit this platform." if ideal_max == 0
                else f"Use {ideal_min}-{ideal_max} hashtags."
            ),
        )
    return scorer


def emoji_count_scorer(ideal_min: int, ideal_max: int, weight: float):
    def scorer(content: str) -> CriterionResult:
        n = count_emojis(content)
        if ideal_min <= n <= ideal_max:
            score = 100.0
        elif n < ideal_min:
            score = (n / max(ideal_min, 1)) * 100.0 if ideal_min > 0 else 100.0
        else:
            score = max(0.0, 100.0 - (n - ideal_max) * 20.0)
        return CriterionResult(
            criterion="emojis",
            score=score,
            weight=weight,
            message=f"Emoji count: {n}",
            actual=str(n),
            expected=f"{ideal_min}-{ideal_max} emojis",
            suggestion=(
                "Emoji use is balanced." if score >= 70
                else f"Use {ideal_min}-{ideal_max} emojis for this platform."
            ),
        )
    return scorer


def paragraph_count_scorer(ideal_min: int, weight: float):
    def scorer(content: str) -> CriterionResult:
        paragraphs = [p for p in content.split("\n\n") if p.strip()]
        n = len(paragraphs)
        if n >= ideal_min + 1:
            score = 100.0
        elif n >= ideal_min:
            score = 85.0
        else:
            score = (n / ideal_min) * 70.0 if ideal_min > 0 else 100.0
        return CriterionResult(
            criterion="format",
            score=score,
            weight=weight,
            message=f"Paragraph count: {n}",
            actual=str(n),
            expected=f"≥{ideal_min} paragraphs",
            suggestion=(
                "Good paragraph structure." if score >= 70
                else "Break content into more paragraphs with line breaks."
            ),
        )
    return scorer


def tone_keywords_scorer(name: str, keywords: List[str], ideal_min: int,
                         ideal_max: int, weight: float):
    def scorer(content: str) -> CriterionResult:
        score, found = keyword_density_score(content, keywords, ideal_min, ideal_max)
        return CriterionResult(
            criterion=name,
            score=score,
            weight=weight,
            message=f"Found {len(found)} indicator(s): {', '.join(found[:5]) or 'none'}",
            actual=f"{len(found)} matches",
            expected=f"{ideal_min}-{ideal_max} indicators",
            suggestion=(
                f"Strong {name}." if score >= 70
                else f"Lean into more {name} language."
            ),
        )
    return scorer


def has_cta_scorer(weight: float):
    cta_keywords = [
        "register", "sign up", "join", "rsvp", "learn more", "click",
        "dm", "comment", "follow", "subscribe", "tap", "visit",
        "신청", "참여", "등록", "확인",
    ]
    def scorer(content: str) -> CriterionResult:
        has = any(k in content.lower() for k in cta_keywords)
        has_link = has_url(content)
        score = 100.0 if (has or has_link) else 40.0
        return CriterionResult(
            criterion="cta",
            score=score,
            weight=weight,
            message=(
                "Has clear CTA or link." if score == 100
                else "No CTA verb or link detected."
            ),
            actual="present" if score == 100 else "missing",
            expected="CTA verb or link",
            suggestion=(
                "CTA is clear." if score == 100
                else "Add a CTA (register / join / link)."
            ),
        )
    return scorer


def no_thread_marker_scorer(weight: float):
    def scorer(content: str) -> CriterionResult:
        has_marker = bool(THREAD_MARKER_RE.search(content))
        score = 0.0 if has_marker else 100.0
        return CriterionResult(
            criterion="single_post",
            score=score,
            weight=weight,
            message="Thread marker detected" if has_marker else "Single post format",
            actual="thread marker found" if has_marker else "clean",
            expected="No '1/', '2/', or 🧵 markers",
            suggestion=(
                "Remove thread markers — write one strong post." if has_marker
                else "Single-post format is correct."
            ),
        )
    return scorer


def punchy_opening_scorer(max_chars: int, weight: float):
    def scorer(content: str) -> CriterionResult:
        first_line = content.strip().split("\n", 1)[0]
        n = len(first_line)
        score = 100.0 if n <= max_chars else max(0.0, 100.0 - (n - max_chars) * 2)
        return CriterionResult(
            criterion="punchy_opening",
            score=score,
            weight=weight,
            message=f"First line: {n} chars",
            actual=f"{n} chars",
            expected=f"≤{max_chars} chars in first line",
            suggestion=(
                "Hook lands fast." if score == 100
                else "Tighten the first line — it has to stop the scroll."
            ),
        )
    return scorer


# ---------------------------------------------------------------------------
# Platform evaluators
# ---------------------------------------------------------------------------

def format_quality_scorer(weight: float, min_paragraphs: int = 0):
    """Formatting checks a model cannot self-verify: orphaned words, and event
    logistics buried in prose instead of bullets.

    These are deterministic, so they belong in code rather than only in the prompt —
    an LLM cannot reliably count characters or see its own line breaks.
    """
    def scorer(content: str) -> CriterionResult:
        problems, score = [], 100.0

        orphans = find_orphan_lines(content)
        if orphans:
            score -= min(40.0, 15.0 * len(orphans))
            shown = ", ".join(f'"{w}"' for w in orphans[:3])
            problems.append(f"{len(orphans)} orphaned word(s): {shown}")

        if has_event_info(content) and not has_structured_lines(content):
            score -= 35.0
            problems.append("event info (date/time/location) is in prose, not bullets")

        leaks = MARKDOWN_LEAK_RE.findall(content)
        if leaks:
            score -= min(40.0, 20.0 * len(leaks))
            problems.append(f"{len(leaks)} markdown artifact(s) — renders literally on this platform")

        if min_paragraphs:
            paras = [p for p in content.split("\n\n") if p.strip()]
            if len(paras) < min_paragraphs:
                score -= 25.0
                problems.append(f"only {len(paras)} paragraphs (want {min_paragraphs}+)")

        score = max(0.0, score)
        return CriterionResult(
            criterion="format",
            score=score,
            weight=weight,
            message="Formatting clean" if not problems else "; ".join(problems),
            actual="clean" if not problems else f"{len(problems)} issue(s)",
            expected="No orphaned words; event info in bullets"
                     + (f"; {min_paragraphs}+ paragraphs" if min_paragraphs else ""),
            suggestion="Good formatting." if not problems else
                       "Move stranded words up a line; put date/time/location in bullets.",
        )
    return scorer


# Tone lists carry BOTH languages. They used to be English-only and were scored
# against Korean output, so `professional`, `casual` and `engagement` returned 0.0 on
# every Korean post — 20%, 15% and 25% of those channels' weight, permanently lost.
# One combined list beats language-switching here: the scorer just counts matches, so
# an English post hits the English terms and a Korean post hits the Korean ones.
LINKEDIN_PRO_KEYWORDS = [
    "insight", "strategy", "professional", "expertise", "industry",
    "leadership", "innovation", "growth", "development", "success",
    "team", "build", "launch", "share",
    # Korean equivalents
    "인사이트", "전략", "전문", "역량", "업계", "리더십", "혁신", "성장",
    "커리어", "경험", "노하우", "성과", "팀", "함께", "공유",
]

INSTAGRAM_CASUAL_KEYWORDS = [
    "you", "your", "we", "our", "love", "excited", "amazing", "join", "check",
    # Korean equivalents — informal/polite second person and enthusiasm markers
    "여러분", "우리", "함께", "지금", "만나", "참여", "신청", "확인",
    "설레", "기대", "좋아", "궁금",
]

CIRCLE_ENGAGEMENT_KEYWORDS = [
    "question", "community", "join", "participate", "share", "discuss",
    # Korean equivalents
    "질문", "커뮤니티", "참여", "함께", "공유", "이야기", "댓글", "의견", "나누",
]

KAKAO_DIRECT_KEYWORDS = [
    "you", "your", "register", "join", "check", "today", "now", "don't miss",
    "신청", "참여", "확인",
]

WHATSAPP_WARM_KEYWORDS = [
    "hey", "quick", "want", "want to", "just", "thought you",
]


class LinkedInEvaluator(ChannelEvaluator):
    platform = "linkedin"
    criteria = [
        # 800–1,000 chars ideal, matching docs/linkedin.md. The prompt previously
        # asked for 1,300–1,800 while this scorer zeroed out above 1,400 — the agent
        # was graded against a target it was never told to hit.
        # EN 800–1,000 / KR 500–650, straight from docs/linkedin.md §2.
        Criterion("length", 0.30, char_length_scorer(500, 800, 1000, 1300, 0.30,
                                                     ko=(300, 500, 650, 900))),
        Criterion("hashtags", 0.15, hashtag_count_scorer(3, 5, 0.15, zero_above=10)),
        Criterion("format", 0.20, format_quality_scorer(0.20, min_paragraphs=3)),
        Criterion("tone", 0.20, tone_keywords_scorer("professional", LINKEDIN_PRO_KEYWORDS, 2, 5, 0.20)),
        Criterion("cta", 0.15, has_cta_scorer(0.15)),
    ]


class InstagramEvaluator(ChannelEvaluator):
    platform = "instagram"
    criteria = [
        # Weights re-balanced to make room for "format" (orphans + event bullets).
        # Chars, not words — docs/instagram.md §2 states its targets in characters.
        # EN 400–600 / KR 200–300.
        Criterion("length", 0.25, char_length_scorer(200, 400, 600, 900, 0.25,
                                                     ko=(120, 200, 300, 500))),
        # §7 is a hard "MAXIMUM 5" (Instagram's own cap), so 6+ must fall off fast.
        Criterion("hashtags", 0.15, hashtag_count_scorer(3, 5, 0.15, zero_above=7)),
        Criterion("emojis", 0.10, emoji_count_scorer(1, 3, 0.10)),
        Criterion("tone", 0.15, tone_keywords_scorer("casual", INSTAGRAM_CASUAL_KEYWORDS, 3, 7, 0.15)),
        Criterion("cta", 0.20, has_cta_scorer(0.20)),
        Criterion("format", 0.15, format_quality_scorer(0.15)),
    ]


class CircleEvaluator(ChannelEvaluator):
    platform = "circle"
    criteria = [
        # Chars, not words — Korean word counts don't convert across languages.
        # docs/circle.md §2: EN 300–700 words (~1,800–4,200 chars) / KR 200–500 words
        # equivalent (~800–2,000 chars at the ~4 chars/word measured on real output).
        Criterion("length", 0.30, char_length_scorer(900, 1800, 4200, 6000, 0.30,
                                                     ko=(400, 800, 2000, 3200))),
        Criterion("structure", 0.25, _struct := (lambda c: _circle_structure_scorer(c, 0.25))),
        Criterion("format", 0.20, _fmt := (lambda c: _circle_format_scorer(c, 0.20))),
        Criterion("engagement", 0.25, tone_keywords_scorer(
            "engagement", CIRCLE_ENGAGEMENT_KEYWORDS, 2, 5, 0.25)),
    ]


def _circle_structure_scorer(content: str, weight: float) -> CriterionResult:
    headers = has_headers(content)
    score = 100.0 if headers else 40.0
    return CriterionResult(
        criterion="structure",
        score=score,
        weight=weight,
        message="Has section headers" if headers else "No headers found",
        actual="headers ✓" if headers else "headers ✗",
        expected="At least one '##' or 'Title:' header",
        suggestion="Good structure." if headers else "Add '## Heading' sections.",
    )


def _circle_format_scorer(content: str, weight: float) -> CriterionResult:
    bullets = has_bullets(content)
    score = 100.0 if bullets else 50.0
    return CriterionResult(
        criterion="format",
        score=score,
        weight=weight,
        message="Has bullet points" if bullets else "No bullet points",
        actual="bullets ✓" if bullets else "bullets ✗",
        expected="Bullet points (•, -, or *)",
        suggestion="Good formatting." if bullets else "Add bullet points for scanability.",
    )


class KakaotalkEvaluator(ChannelEvaluator):
    platform = "kakaotalk"
    criteria = [
        Criterion("sentence_count", 0.35, sentence_max_scorer(3, 6, 0.35)),
        Criterion("hashtags", 0.20, hashtag_count_scorer(0, 0, 0.20)),
        Criterion("emojis", 0.15, emoji_count_scorer(0, 2, 0.15)),
        Criterion("cta", 0.30, has_cta_scorer(0.30)),
    ]


class WhatsappEvaluator(ChannelEvaluator):
    platform = "whatsapp"
    criteria = [
        Criterion("sentence_count", 0.25, sentence_max_scorer(4, 8, 0.25)),
        # EN 50–150 / KR 30–80, from docs/whatsapp.md §2. The old 200–400 band
        # contradicted its own prompt in both languages.
        Criterion("length", 0.25, char_length_scorer(30, 50, 150, 300, 0.25,
                                                     ko=(20, 30, 80, 200))),
        Criterion("hashtags", 0.20, hashtag_count_scorer(0, 0, 0.20)),
        Criterion("emojis", 0.15, emoji_count_scorer(0, 2, 0.15)),
        Criterion("cta", 0.15, has_cta_scorer(0.15)),
    ]


class XEvaluator(ChannelEvaluator):
    platform = "x"
    criteria = [
        # EN 100–150 sweet spot / KR 60–90, from docs/x.md §2. 280 stays a hard cap.
        Criterion("char_cap", 0.35, hard_char_cap_scorer(280, 0.35,
                                                         ideal=(100, 150), ko=(60, 90))),
        Criterion("hashtags", 0.20, hashtag_count_scorer(0, 2, 0.20, zero_above=5)),
        Criterion("emojis", 0.15, emoji_count_scorer(0, 2, 0.15)),
        Criterion("single_post", 0.15, no_thread_marker_scorer(0.15)),
        Criterion("punchy_opening", 0.15, punchy_opening_scorer(80, 0.15)),
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_EVALUATORS = {
    "linkedin": LinkedInEvaluator,
    "instagram": InstagramEvaluator,
    "circle": CircleEvaluator,
    "kakaotalk": KakaotalkEvaluator,
    "whatsapp": WhatsappEvaluator,
    "x": XEvaluator,
}


def get_evaluator(platform: str) -> ChannelEvaluator:
    cls = _EVALUATORS.get(platform.lower())
    if not cls:
        raise ValueError(f"Unknown platform: {platform}")
    return cls()


def evaluate(platform: str, content: str) -> Dict:
    """One-shot helper: returns {'total': float, 'criteria': [...]}."""
    ev = get_evaluator(platform)
    criteria = ev.evaluate(content)
    total = round(sum(r["weighted_score"] for r in criteria), 1)
    return {"platform": platform, "total": total, "criteria": criteria}
