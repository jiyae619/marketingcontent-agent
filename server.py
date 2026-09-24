from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import hashlib
import json
import re
import sys
import urllib.request
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Make our local modules importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'testing/core'))

import feedback_db
import brief_fields
from evaluators import evaluate as run_eval, strip_markdown, strip_ungrounded
import providers
import judge
import generators
import oauth_providers
from concurrent.futures import ThreadPoolExecutor
import threading
import time as _time
import secrets

feedback_db.init_db()

VALID_PLATFORMS = ['linkedin', 'instagram', 'circle', 'kakaotalk', 'whatsapp', 'x']
PUBLISHABLE_PLATFORMS = ('linkedin', 'instagram')  # the only two with a real publish API — see docs/oauth.md

_CALLBACK_PAGE = '<!doctype html><meta charset="utf-8">\n<body style="font:15px system-ui;max-width:32rem;margin:15vh auto;text-align:center">\n<h2>{title}</h2><p>{message}</p>\n<p><a href="{front}">Return to the app</a></p>\n<script>setTimeout(()=>{{try{{window.close()}}catch(e){{}}}},1200)</script>\n</body>'

# In-memory CSRF state for the OAuth handshake: {state: (platform, created_at)}.
# Five-minute secrets that die with the process, not account data, so a plain
# dict (not the DB) is the right amount of durability — surviving a server
# restart mid-handshake just means the user clicks "Connect" again.
_OAUTH_STATE_TTL = 300
_oauth_states = {}
_oauth_states_lock = threading.Lock()


def _new_oauth_state(platform):
    with _oauth_states_lock:
        now = _time.time()
        for k, (_, ts) in list(_oauth_states.items()):
            if now - ts > _OAUTH_STATE_TTL:
                del _oauth_states[k]
        state = secrets.token_urlsafe(24)
        _oauth_states[state] = (platform, now)
        return state


def _consume_oauth_state(state):
    """Returns the platform for a valid, unexpired, UNUSED state, or None.
    Deletes it either way — a state is single-use, so a replayed callback
    (browser back button, a retried request) fails closed instead of
    re-running the token exchange a second time."""
    with _oauth_states_lock:
        entry = _oauth_states.pop(state, None)
    if not entry:
        return None
    platform, ts = entry
    if _time.time() - ts > _OAUTH_STATE_TTL:
        return None
    return platform

VOICE_EXAMPLES_LIMIT = 3

GEMINI_MODEL = 'gemini-2.5-flash'

# Tiered eval cascade: heuristic (always, free) -> LLM judge -> human.
#
# JUDGE_TRIGGER_THRESHOLD is a COST control, not a quality gate. Measured against the
# golden set (scripts/tune_threshold.py), the heuristic cannot separate clean from
# defective content at ANY threshold: 16 of 17 defective samples score above the
# lowest clean sample, and at the shipped default of 70 it catches 1 of 4 injected
# hallucinations. Reaching 90% recall is impossible anywhere in 50-100; even 82%
# requires escalating 76% of everything.
#
# That is structural, not a tuning problem — the heuristic never receives the brief,
# so grounding defects are invisible to it by construction. So the gate is applied
# only when a judge call actually costs money. On a free local judge, judge
# everything: the gate can only cause false negatives, and false negatives are the
# error type that reaches a human unflagged.
JUDGE_ON_GENERATE = os.getenv('JUDGE_ON_GENERATE', 'true').strip().lower() not in ('0', 'false', 'no', 'off')
JUDGE_TRIGGER_THRESHOLD = float(os.getenv('JUDGE_TRIGGER_THRESHOLD', '70'))


def _prompt_hash(channel_template: str) -> str:
    """Version fingerprint of a channel prompt template.

    Computed from the raw `## AI Prompt` slice BEFORE voice injection, so it
    identifies the channel template independent of per-user voice (which is
    tracked separately by voice_version).
    """
    return hashlib.sha256(channel_template.encode('utf-8')).hexdigest()[:12]

# Voice synthesis runs on a LOCAL model. It used to call providers.call_gemini, which
# is refused outright under LOCAL_ONLY=true — so on this project's own default config
# the learning loop's synthesis half never ran, and the only trace was one print line.
#
# It defaults to the GENERATOR's model rather than the judge's, and that is a memory
# decision, not a quality one: CLAUDE.md rule 1 says two models cannot co-reside on an
# 8GB box, and providers._evict_others enforces it by unloading whatever else is
# resident. Pointing synthesis at a second model would therefore evict the generator
# on every approve — ~3.3GB reloaded, seconds of latency, on the hot path. Same model
# = no eviction. judge != generator does not apply here: summarizing your own posts
# produces no verdict, so there is nothing to grade itself.
VOICE_MODEL = os.getenv('VOICE_MODEL') or os.getenv('LOCAL_LLM_MODEL')

# A synthesized profile is injected into EVERY later generation for that platform, so
# a bad one degrades everything downstream silently — and the voice_version bump
# invalidates the cache, removing the rows you would have compared against. The old
# code accepted any non-empty string. That was survivable behind gemini-2.5-flash and
# is not behind a 4B: small models pad, preface, and sometimes just hand a sample back.
VOICE_MIN_WORDS = 20
VOICE_MAX_WORDS = 200
_VOICE_ECHO_NGRAM = 8


def _clean_voice_profile(text, samples_text):
    """Return (profile, None) if usable, else (None, reason).

    Rejecting is the safe outcome: no profile means the loop falls back to raw
    few-shot, which is a weaker prompt but a correct one.
    """
    if not text:
        return None, "empty response"
    t = text.strip()
    # Small models like to wrap prose in fences and announce themselves first.
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", t).strip()
    first, _, rest = t.partition("\n")
    if rest and len(first) < 60 and first.rstrip().endswith(":"):
        t = rest.strip()
    t = re.sub(r"^[#*\s]+", "", t).strip()

    words = t.split()
    if len(words) < VOICE_MIN_WORDS:
        return None, f"too short ({len(words)} words)"
    if len(words) > VOICE_MAX_WORDS:
        return None, f"too long ({len(words)} words)"

    # Echo guard: a small model asked to summarize sometimes returns one of the inputs.
    # That would install a single past post as the style rule for every future one.
    hay = " ".join(samples_text.split()).lower()
    for i in range(len(words) - _VOICE_ECHO_NGRAM + 1):
        if " ".join(words[i:i + _VOICE_ECHO_NGRAM]).lower() in hay:
            return None, "echoes the input samples verbatim"
    return t, None


class CORSRequestHandler(SimpleHTTPRequestHandler):
    # Localhost only, any port — not a single hardcoded origin, so this survives
    # Vite picking a different port when 5173 is taken. The property that matters
    # for security is "localhost", not "5173": a remote page's browser-set Origin
    # header can never read as localhost/127.0.0.1, so this can't be spoofed by an
    # actual attacker the way a wildcard could.
    _LOCAL_ORIGIN_RE = re.compile(r'^https?://(localhost|127\.0\.0\.1)(:\d+)?$')

    def end_headers(self):
        # CORS used to be wildcard-open with no auth behind it — meaning any
        # website you had open in another tab could fetch() this API directly
        # and it would just work. Restricting to localhost origins closes that:
        # a non-matching Origin gets no Allow-Origin header at all, so the
        # browser blocks the response from being read by that page's JS.
        # Costs nothing for real usage — the dev flow (`npm run dev`) never
        # makes a genuinely cross-origin browser request to this port at all:
        # the browser only ever talks to Vite's own origin, and Vite's dev
        # proxy forwards server-side (Node-to-Node), which browser CORS does
        # not apply to.
        origin = self.headers.get('Origin', '')
        if self._LOCAL_ORIGIN_RE.match(origin):
            self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, x-api-key')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()
    
    def do_GET(self):
        # Handle /api/prompts/<platform> endpoint
        if self.path.startswith('/api/prompts/'):
            platform = self.path.split('/')[-1]

            if platform not in VALID_PLATFORMS:
                self._json(404, {'error': f'Invalid platform. Must be one of: {", ".join(VALID_PLATFORMS)}'})
                return

            try:
                prompt = self.load_prompt_from_md(platform)
                prompt = self._with_voice_examples(platform, prompt)
                self._json(200, {'platform': platform, 'prompt': prompt})
            except Exception as e:
                self._json(500, {'error': f'Failed to load prompt: {str(e)}'})
            return

        # Available generator models — the single source its UI dropdown reads.
        if self.path == '/api/generator/models':
            self._json(200, {'models': generators.available_models(),
                             'default': generators.DEFAULT_GENERATOR_KEY})
            return

        # Available judge models — the single source the UI dropdown reads.
        if self.path == '/api/judge/models':
            self._json(200, {'models': judge.available_models(),
                             'default': judge.DEFAULT_JUDGE_KEY})
            return

        # Chip vocabulary for the review UI — one source of truth. Serves
        # EDIT_REASONS, not FLAG_TAXONOMY: the chips answer "why did the human change
        # this", which is a richer question than "what did the judge detect", and
        # EDIT_REASONS is a superset with identical families. Same response shape.
        # The form is rendered FROM this spec rather than hand-built in JSX, so a
        # field added to brief_fields.FIELDS cannot silently fail to appear in the
        # UI, and the enum the server validates against is the enum the UI offers.
        if self.path == '/api/brief/fields':
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))
            from schema_gen import EVENT_TYPES
            self._json(200, {
                'fields': [{'name': n, 'kind': k, 'required': r,
                            'label_en': le, 'label_ko': lk}
                           for n, k, r, le, lk in brief_fields.FIELDS],
                'event_types': [{'key': k, 'en': en, 'ko': ko}
                                for k, (en, ko, _) in EVENT_TYPES.items()],
                'timezones': list(brief_fields.TIMEZONES),
                'currencies': list(brief_fields.CURRENCIES),
                'price_kinds': list(brief_fields.PRICE_KINDS),
            })
            return

        if self.path == '/api/flags':
            self._json(200, {'taxonomy': [
                {'category': c, 'family': f}
                for c, f in feedback_db.EDIT_REASONS.items()
            ]})
            return

        # Latest machine judge verdict for a generation (async grade retrieval).
        if self.path.startswith('/api/judge/result'):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            gid = (q.get('generation_id') or [None])[0]
            if not gid:
                self._json(400, {'error': 'generation_id required'})
                return
            try:
                result = feedback_db.get_judge_result(int(gid))
            except ValueError:
                self._json(400, {'error': 'generation_id must be an integer'})
                return
            self._json(200, result or {})
            return

        # /api/oauth/<platform>/authorize — redirects the BROWSER (not fetch) to
        # the platform's consent screen. GET, not POST: this has to be a normal
        # navigation so the platform's own login page can render.
        if self.path.startswith('/api/oauth/') and self.path.endswith('/authorize'):
            platform = self.path.split('/')[3]
            if platform not in PUBLISHABLE_PLATFORMS:
                self._json(404, {'error': f'unknown platform: {platform}'})
                return
            state = _new_oauth_state(platform)
            try:
                url = (oauth_providers.linkedin_authorize_url(state) if platform == 'linkedin'
                      else oauth_providers.instagram_authorize_url(state))
            except oauth_providers.OAuthError as e:
                # This is a browser navigation (the Connect button sets
                # window.location.href), not a fetch the frontend can catch —
                # a JSON body would render as a bare blob with no way back.
                # Same friendly page the callback route uses.
                front = os.getenv('FRONTEND_ORIGIN', 'http://localhost:5173')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                safe = str(e).replace('<', '&lt;').replace('>', '&gt;')
                self.wfile.write(_CALLBACK_PAGE.format(
                    title='Not configured yet', message=safe, front=front).encode())
                return
            self.send_response(302)
            self.send_header('Location', url)
            self.end_headers()
            return

        # /api/oauth/<platform>/callback — the platform redirects the browser
        # HERE after the user approves or denies. Must validate `state` before
        # touching `code` at all (see _consume_oauth_state's docstring).
        if self.path.startswith('/api/oauth/') and '/callback' in self.path:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            platform = parsed.path.split('/')[3]
            q = parse_qs(parsed.query)
            state = (q.get('state') or [None])[0]
            code = (q.get('code') or [None])[0]
            err = (q.get('error_description') or q.get('error') or [None])[0]

            def _finish(ok, message):
                # A real page, not JSON: the browser lands here directly.
                front = os.getenv('FRONTEND_ORIGIN', 'http://localhost:5173')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                safe = message.replace('<', '&lt;').replace('>', '&gt;')
                title = "Connected" if ok else "Could not connect"
                self.wfile.write(_CALLBACK_PAGE.format(title=title, message=safe, front=front).encode())

            if not state or not _consume_oauth_state(state):
                _finish(False, 'This link has expired or was already used. Go back and click Connect again.')
                return
            expected_platform = platform
            if err:
                _finish(False, f'{expected_platform} declined: {err}')
                return
            if not code:
                _finish(False, 'No authorization code returned.')
                return
            try:
                if platform == 'linkedin':
                    tok = oauth_providers.linkedin_exchange_code(code)
                    access = tok.get('access_token')
                    if not access:
                        raise oauth_providers.OAuthError(f'no access_token in response: {tok}')
                    info = oauth_providers.linkedin_userinfo(access)
                    member_urn = f"urn:li:person:{info['sub']}"
                    expires_at = _time.time() + float(tok.get('expires_in', 0)) if tok.get('expires_in') else None
                    feedback_db.save_oauth_account(
                        platform='linkedin', external_id=member_urn,
                        label=info.get('name') or info.get('email'),
                        access_token=access, refresh_token=tok.get('refresh_token'),
                        scope=os.environ.get('LINKEDIN_SCOPES', ''), expires_at=expires_at)
                    _finish(True, f"LinkedIn connected as {info.get('name') or member_urn}.")
                else:
                    tok = oauth_providers.instagram_exchange_code(code)
                    short_lived = tok.get('access_token')
                    if not short_lived:
                        raise oauth_providers.OAuthError(f'no access_token in response: {tok}')
                    long_lived = oauth_providers.instagram_long_lived_token(short_lived)
                    user_token = long_lived.get('access_token', short_lived)
                    account = oauth_providers.instagram_discover_account(user_token)
                    expires_in = long_lived.get('expires_in')
                    expires_at = _time.time() + float(expires_in) if expires_in else None
                    feedback_db.save_oauth_account(
                        platform='instagram', external_id=account['ig_user_id'],
                        label=f"@{account['username']}" if account.get('username') else account['ig_user_id'],
                        access_token=user_token, page_token=account['page_token'],
                        scope=os.environ.get('META_SCOPES', ''), expires_at=expires_at)
                    _finish(True, f"Instagram connected as @{account.get('username', account['ig_user_id'])}.")
            except oauth_providers.OAuthError as e:
                _finish(False, str(e))
            except Exception as e:
                _finish(False, f'Unexpected error: {e}')
            return

        # Connected accounts for the UI — tokens are never in this response;
        # list_oauth_accounts() does not select the token columns at all.
        if self.path == '/api/oauth/accounts':
            self._json(200, {'accounts': feedback_db.list_oauth_accounts()})
            return

        # Publish history for one generation, so the review UI can show
        # "published 2m ago" / "scheduled for 6pm" / "failed: <reason>".
        if self.path.startswith('/api/publish/log'):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            gid = (q.get('generation_id') or [None])[0]
            if not gid:
                self._json(400, {'error': 'generation_id required'})
                return
            try:
                self._json(200, {'log': feedback_db.publish_log_for(int(gid))})
            except ValueError:
                self._json(400, {'error': 'generation_id must be an integer'})
            return

        # Light dashboard for the dev — backend-only signal
        if self.path == '/api/admin/stats':
            self._json(200, {
                'platforms': feedback_db.stats_by_platform(),
                'hands_on_time': feedback_db.hands_on_time_stats(),
            })
            return

        # Default: serve static files
        return super().do_GET()

    def _json(self, status, body):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def _with_voice_examples(self, platform: str, base_prompt: str) -> str:
        """Inject voice context — synthesized style profile if available, else raw few-shot.

        Synthesized profile: one LLM call compresses N samples into ~120 tokens.
        Raw few-shot: last 3 copied examples appended verbatim (~600 tokens).
        Falls back to base prompt if no copies exist yet.
        """
        try:
            # Try synthesized first (cheapest at inference time)
            style = feedback_db.get_voice_profile(platform)
            if style:
                block = (
                    "\n\n## Your Voice Style\n"
                    "Write in this user's established voice and style:\n\n"
                    f"{style}"
                )
                return base_prompt + block

            # Fall back to raw few-shot
            examples = feedback_db.recent_copies(platform, limit=VOICE_EXAMPLES_LIMIT)
            if not examples:
                return base_prompt

            block = ["", "", "## User's Recent Approved Voice"]
            block.append("Match the tone, rhythm, and voice of these approved samples. Do not copy verbatim.")
            for i, ex in enumerate(examples, 1):
                block.append(f"\n### Example {i}\n```\n{ex['final_content']}\n```")
            return base_prompt + "\n".join(block)

        except Exception:
            return base_prompt

    def _maybe_synthesize_voice(self, platform: str) -> None:
        """Triggered after a copy is logged. If enough new copies exist, synthesize.

        Runs on a LOCAL model (see VOICE_MODEL) and learns from two signals rather
        than one: posts the human accepted, and — new — the voice-family changes the
        human MADE. The second is the stronger signal and was captured but unread:
        feedback_events has stored original_content and final_content all along while
        this loop looked only at final_content. Accepted posts show what good output
        looks like; edits show what this person reliably fixes, which is the thing a
        style profile is actually for.

        Grounding edits are filtered out upstream by feedback_db.voice_edits(), not
        here: "changed Friday to Thursday" is a fact fix, and feeding it in as style
        teaches the model to write Thursday.
        """
        try:
            count = feedback_db.copy_count(platform)
            existing = feedback_db.get_voice_profile(platform)
            # Synthesize on the first copy, then again once get_voice_profile reports
            # the active version stale (3+ new approvals/edits since it was built).
            if count == 0 or (existing is not None):
                return
            examples = feedback_db.recent_copies(platform, limit=6)
            if not examples:
                return

            samples_text = "\n\n---\n".join(
                f"Sample {i+1}:\n{ex['final_content']}"
                for i, ex in enumerate(examples)
            )

            edits_block = ""
            edits = feedback_db.voice_edits(platform, limit=6)
            lines = []
            for e in edits:
                try:
                    ops = json.loads(e.get("edit_ops") or "[]")
                except (ValueError, TypeError):
                    continue
                for op in ops[:3]:
                    frm = (op.get("from") or "").strip()
                    to = (op.get("to") or "").strip()
                    if not (frm or to):
                        continue
                    lines.append(f'- [{e.get("flag_category")}] "{frm[:120]}" -> "{to[:120]}"')
            if lines:
                edits_block = ("\n\nEdits this person MADE to drafts — each shows text "
                               "they rejected and what they replaced it with. These are "
                               "the strongest signal of their taste:\n"
                               + "\n".join(lines[:12]))

            system = (
                "You extract a writing-voice profile from a marketer's own posts. "
                "You describe HOW they write, never WHAT any individual post said. "
                "Never quote a sample back. Output the profile only, with no preamble, "
                "no heading and no markdown."
            )
            user = (
                f"Platform: {platform}\n\n"
                f"Posts they accepted:\n{samples_text}{edits_block}\n\n"
                "Write a voice profile of 3-5 sentences, under 120 words, covering:\n"
                "- Sentence length and rhythm\n"
                "- Tone (formal/casual, direct/warm)\n"
                "- Language and formality register, if the samples show one\n"
                "- Characteristic words or patterns, and what they avoid\n"
            )

            res = providers.call_local(user, model=VOICE_MODEL, system=system)
            if not res.get("ok"):
                print(f"[voice] SYNTHESIS FAILED {platform} model={VOICE_MODEL!r}: "
                      f"{res.get('error')} — falling back to raw few-shot")
                return
            style, reason = _clean_voice_profile(res.get("text"), samples_text + edits_block)
            if style is None:
                # Refusing is the safe outcome. No profile means raw few-shot, which is
                # a weaker prompt; a bad profile is a wrong one, applied to everything.
                print(f"[voice] SYNTHESIS REJECTED {platform} model={VOICE_MODEL!r}: "
                      f"{reason} — keeping raw few-shot rather than installing it")
                return
            feedback_db.save_voice_profile(platform, style)
            print(f"[voice] synthesized {platform} on {VOICE_MODEL} "
                  f"({count} copies, {len(lines)} voice edits -> {len(style.split())} words)")
        except Exception as e:
            print(f"[voice] synthesis failed for {platform}: {e}")
    
    def _maybe_judge(self, platform, content, generation_id, heuristic_score,
                     judge_model=None, source_brief=None, generator_model=None):
        """Tiered cascade step (runs in a background thread, never blocks generation).

        Skips when the heuristic already scored the content at/above the trigger
        threshold — the LLM judge tier is spent only on flagged content. No-ops
        gracefully when no non-generator judge model is reachable (judge != generator
        needs a second provider). Persists the verdict to judge_results.
        """
        try:
            # Resolve the judge first: the claim needs its name, and whether the gate
            # applies at all depends on which provider answers. Pure config lookup, no
            # network — judge.judge() re-resolves to the same model deterministically.
            try:
                _k, _l, judge_model_id, judge_fn = judge.resolve_judge(judge_model, generator_model)
            except ValueError as ve:
                print(f"[judge] gen {generation_id} not judged: {ve}")
                return

            # Gate on cost, not on quality — see JUDGE_TRIGGER_THRESHOLD above. A free
            # local judge is never skipped: the gate's only possible effect there is a
            # false negative, and it produced 11 of them on 17 known-bad samples.
            judge_is_free = judge_fn is providers.call_local
            if (not judge_is_free and heuristic_score is not None
                    and heuristic_score >= JUDGE_TRIGGER_THRESHOLD):
                print(f"[judge] gen {generation_id} skipped: score {heuristic_score:.1f} "
                      f">= {JUDGE_TRIGGER_THRESHOLD} and {judge_model_id} is a paid judge")
                return

            # CLAIM BEFORE JUDGING. This thread is a daemon: if the process exits mid
            # call it is killed with no unwinding, so anything written only on the
            # success path is lost silently. That is how 45 of 49 eligible generations
            # went unjudged and left no trace. A pending row survives the crash and is
            # re-drivable via feedback_db.stuck_judge_results().
            row_id, prior = feedback_db.claim_judge_result(
                generation_id=generation_id, platform=platform, judge_model=judge_model_id)
            if prior in feedback_db.JUDGE_TERMINAL:
                print(f"[judge] gen {generation_id} already {prior} by {judge_model_id} — skipped")
                return

            verdict = judge.judge(content, platform, model=judge_model,
                                  generator_model=generator_model, source_brief=source_brief)
            if not verdict.get('ok'):
                feedback_db.finish_judge_result(row_id, 'failed',
                                                summary=verdict.get('error'))
                print(f"[judge] gen {generation_id} FAILED: {verdict.get('error')}")
                return
            # Abstention: the judge said it could not verify. Recorded as its own
            # status rather than as absence — "I looked and won't guess" is signal,
            # "the thread died" is an outage, and both used to render identically.
            # Checked before the unparseable-verdict branch below: an abstained
            # verdict also has overall=None, and must not be mistaken for that.
            if verdict.get('abstained'):
                feedback_db.finish_judge_result(
                    row_id, 'abstained',
                    summary=verdict.get('abstain_reason') or 'judge confidence low')
                print(f"[judge] gen {generation_id} ABSTAINED — routed to human")
                return
            # `ok` only means the API call succeeded — the model can still return
            # output the parser can't read (small local models do this often).
            if verdict.get('overall') is None:
                feedback_db.finish_judge_result(
                    row_id, 'failed',
                    summary=verdict.get('error') or 'no scores returned')
                print(f"[judge] gen {generation_id} FAILED: unparseable verdict")
                return
            feedback_db.finish_judge_result(
                row_id, 'graded',
                overall=verdict.get('overall'),
                safety_pass=verdict.get('safety_pass'),
                scores=verdict.get('scores'),
                summary=verdict.get('summary'),
            )
            print(f"[judge] gen {generation_id} judged by {verdict.get('judge_model')} "
                  f"overall={verdict.get('overall')} safety_pass={verdict.get('safety_pass')}")
        except Exception as e:
            print(f"[judge] background judge failed for gen {generation_id}: {e}")

    def load_prompt_from_md(self, platform):
        """Extract AI Prompt section from markdown file"""
        md_path = f'docs/{platform}.md'
        
        if not os.path.exists(md_path):
            raise FileNotFoundError(f'Documentation file not found: {md_path}')
        
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract content between "## AI Prompt" and next "##"
        start_marker = '## AI Prompt'
        start_idx = content.find(start_marker)
        
        if start_idx == -1:
            raise ValueError(f'AI Prompt section not found in {md_path}')
        
        # Find the start of the prompt content (after the header)
        prompt_start = start_idx + len(start_marker)
        
        # Find the next "##" header
        next_header_idx = content.find('\n##', prompt_start)
        
        if next_header_idx == -1:
            # No next header, take until end of file
            prompt_content = content[prompt_start:]
        else:
            prompt_content = content[prompt_start:next_header_idx]
        
        # Clean up the prompt (remove leading/trailing whitespace)
        prompt = prompt_content.strip()
        
        return prompt
    
    def do_POST(self):
        # /api/copies — human verdict on generated content (approve / edit / reject),
        # optionally carrying one flag from the shared taxonomy.
        # /api/oauth/<platform>/disconnect — soft-delete the account (see
        # disconnect_oauth_account's docstring on why tokens are wiped, not
        # merely flagged).
        if self.path.startswith('/api/oauth/') and self.path.endswith('/disconnect'):
            length = int(self.headers.get('Content-Length', '0'))
            payload = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
            account_id = payload.get('account_id')
            if not isinstance(account_id, int):
                self._json(400, {'error': 'account_id (int) required'})
                return
            ok = feedback_db.disconnect_oauth_account(account_id)
            if not ok:
                self._json(404, {'error': 'no connected account with that id'})
                return
            self._json(200, {'disconnected': account_id})
            return

        # /api/publish — enqueue a generation for publishing. Takes IDs ONLY,
        # never `content`: the text that goes out is read server-side from the
        # latest approve/edit verdict on `generation_id` (feedback_db.enqueue_
        # publish), so nothing this endpoint accepts can change WHAT gets
        # published, only WHETHER and WHEN. scheduled_for is an optional unix
        # timestamp; omitted means "publish on the next scheduler tick."
        if self.path == '/api/publish':
            length = int(self.headers.get('Content-Length', '0'))
            payload = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
            platform = (payload.get('platform') or '').lower()
            gen_id = payload.get('generation_id')
            account_id = payload.get('oauth_account_id')
            scheduled_for = payload.get('scheduled_for')
            if platform not in PUBLISHABLE_PLATFORMS:
                self._json(400, {'error': f'platform must be one of {PUBLISHABLE_PLATFORMS}'})
                return
            if not isinstance(gen_id, int) or not isinstance(account_id, int):
                self._json(400, {'error': 'generation_id and oauth_account_id (int) required'})
                return
            if scheduled_for is not None and not isinstance(scheduled_for, (int, float)):
                self._json(400, {'error': 'scheduled_for must be a unix timestamp'})
                return
            try:
                job = feedback_db.enqueue_publish(
                    generation_id=gen_id, platform=platform,
                    oauth_account_id=account_id, scheduled_for=scheduled_for)
            except ValueError as e:
                self._json(400, {'error': str(e)})
                return
            print(f"[publish] queued {platform} gen={gen_id} job={job['id']} "
                  f"scheduled_for={scheduled_for or 'now'}")
            self._json(200, {'job_id': job['id'], 'content_fingerprint': job['content_fingerprint']})
            return

        # /api/publish/cancel — only a still-pending (not yet claimed) job.
        if self.path == '/api/publish/cancel':
            length = int(self.headers.get('Content-Length', '0'))
            payload = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
            job_id = payload.get('job_id')
            if not isinstance(job_id, int):
                self._json(400, {'error': 'job_id (int) required'})
                return
            ok = feedback_db.cancel_publish_job(job_id)
            if not ok:
                self._json(409, {'error': 'job is not pending (already running, done, or unknown)'})
                return
            self._json(200, {'canceled': job_id})
            return

        if self.path == '/api/copies':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                platform = payload.get('platform', '').lower()
                final = payload.get('final_content', '')
                gen_id = payload.get('generation_id')
                verdict_override = payload.get('verdict')       # explicit, e.g. 'reject'
                flag_category = payload.get('flag_category')    # chip from EDIT_REASONS
                # A review can name several defects at once. The list is the real
                # input now; flag_category stays accepted so an older client, and
                # every row already written, keep working.
                flag_categories = payload.get('flag_categories') or []
                if not isinstance(flag_categories, list):
                    self._json(400, {'error': 'flag_categories must be a list'})
                    return
                edit_note = payload.get('edit_note')            # free text, never parsed
                if platform not in VALID_PLATFORMS:
                    self._json(400, {'error': 'platform required'})
                    return

                # Resolve the linked generation once: verify platform + get the
                # original text (used to classify approve vs edit).
                original = None
                if gen_id is not None:
                    gen = feedback_db.get_generation(gen_id)
                    if gen is None:
                        gen_id = None  # dangling id — record unlinked rather than drop
                    elif gen['platform'] != platform:
                        self._json(400, {'error': 'generation_id does not match platform'})
                        return
                    else:
                        original = gen['generated_content']

                if verdict_override == 'reject':
                    # Reject: no approved content — record the rejection (+ flag).
                    verdict = 'reject'
                    final_content = None
                else:
                    # Approve / edit: require genuine content; classify from the text.
                    if not final.strip():
                        self._json(400, {'error': 'final_content required'})
                        return
                    if not feedback_db.is_genuine_content(final):
                        self._json(400, {'error': 'final_content is not genuine content'})
                        return
                    verdict = feedback_db.classify_verdict(original, final)
                    final_content = final
                    # The chip is REQUIRED on an edit. Before this it shipped only on
                    # reject (ReviewPanel.jsx) — the rarest action — which is why 10
                    # feedback events produced 0 flags and the taxonomy was never
                    # exercised. An edit without a family cannot be routed: the loop
                    # has no way to tell "cut the cliche" from "fixed the date", and
                    # guessing is what teaches a fact as a style rule.
                    if verdict == 'edit' and not (flag_category or flag_categories):
                        # pct_changed rides along so the UI can show the reviewer how
                        # much they actually rewrote before asking them why.
                        d = feedback_db.diff_ops(original, final_content)
                        self._json(400, {'error': 'flag_category required on an edit',
                                         'choices': feedback_db.EDIT_REASONS,
                                         'pct_changed': d.get('pct_changed')})
                        return

                try:
                    row_id = feedback_db.log_feedback(
                        generation_id=gen_id,
                        platform=platform,
                        verdict=verdict,
                        original_content=original,
                        final_content=final_content,
                        flag_category=flag_category,
                        flag_categories=flag_categories,
                        edit_note=edit_note,
                    )
                except ValueError as ve:
                    self._json(400, {'error': str(ve)})
                    return
                _chips = [c for c in ([flag_category] if flag_category else []) + flag_categories]
                print(f"[feedback] {platform} {verdict} id={row_id} gen={gen_id} "
                      f"flags={','.join(_chips) or '-'} "
                      f"fam={','.join(sorted({feedback_db.EDIT_REASONS[c] for c in _chips})) or '-'} "
                      f"note={'y' if edit_note else 'n'} "
                      f"voice_v={feedback_db.voice_version(platform)}")
                self._json(200, {'id': row_id, 'platform': platform, 'verdict': verdict})

                # Voice synthesis only learns from accepted content (approve/edit).
                if verdict in ('approve', 'edit'):
                    api_key = os.getenv('GEMINI_API_KEY')
                    if api_key:
                        import threading
                        threading.Thread(
                            target=self._maybe_synthesize_voice,
                            args=(platform,),
                            daemon=True,
                        ).start()
            except Exception as e:
                self._json(500, {'error': str(e)})
            return

        # /api/judge — grade content against the flag taxonomy with a swappable
        # judge model (judge != generator). Returns the verdict in memory.
        # The structured path. Deliberately a SEPARATE route from /api/gemini
        # rather than a branch inside it: that route builds a free-text prompt and
        # lets the model write the whole post, which is the design this replaces.
        # Both log to the same spine, so their output stays comparable.
        if self.path == '/api/generate/fields':
            length = int(self.headers.get('Content-Length') or 0)
            data = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
            platform = (data.get('platform') or '').lower()
            if platform not in VALID_PLATFORMS:
                self._json(400, {'error': f'Unknown platform: {platform}'})
                return
            fields = data.get('fields') or {}

            # Validate BEFORE resolving a model or touching the cache: a bad form
            # should cost nothing and come back with every error at once.
            ko = bool(fields.get('ko'))
            _facts, errors = brief_fields.validate(fields, ko=ko)
            if errors:
                self._json(422, {'error': 'field validation failed', 'errors': errors})
                return

            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))
            import schema_gen
            try:
                _k, _l, resolved_model, _f = generators.resolve(data.get('generator_model'))
            except ValueError as ve:
                self._json(400, {'error': str(ve)}); return

            v_ver = feedback_db.voice_version(platform)
            channel_template = self.load_prompt_from_md(platform)
            prompt_version = _prompt_hash(channel_template)
            # The cache key describes what PRODUCED the text. The submitted fields
            # ARE the input here, so they are serialised with sorted keys — two
            # forms differing only in field order are the same brief.
            canonical = json.dumps(fields, ensure_ascii=False, sort_keys=True)
            cache_key = feedback_db.make_cache_key(
                platform, canonical, fields.get('link') or '', False,
                v_ver, resolved_model, prompt_version)
            cached = feedback_db.generation_by_cache_key(cache_key)
            if cached:
                self._json(200, {'content': [{'text': cached['generated_content']}],
                                 'generation_id': cached['id'], 'from_cache': True})
                return

            text, facts, flags, err = schema_gen.generate(
                platform, None, resolved_model, fields=fields)
            if err:
                self._json(502, {'error': err}); return

            ev = run_eval(platform, text)
            result = {'content': [{'text': text}], 'generator_model': resolved_model,
                      'grounding_flags': flags, 'facts': facts,
                      'eval': {'total': ev['total'], 'criteria': ev['criteria']}}
            try:
                gen_id = feedback_db.log_generation(
                    platform=platform, original_input=canonical,
                    generated_content=text, link_url=fields.get('link') or '',
                    has_image=False, eval_score=ev['total'],
                    eval_detail=json.dumps(ev['criteria']), model=resolved_model,
                    prompt_version=prompt_version, voice_version=v_ver,
                    cache_key=cache_key)
                result['generation_id'] = gen_id
                print(f"[gen:fields] {platform} id={gen_id} score={ev['total']:.1f} "
                      f"flags={flags or 'none'}")
            except Exception as log_err:
                existing = feedback_db.generation_by_cache_key(cache_key)
                if existing:
                    result['generation_id'] = existing['id']
                else:
                    # A generation with no row cannot be edited, flagged or fed
                    # back into the loop, so it is not a success.
                    self._json(500, {'error': f'logging failed: {log_err}'}); return
            self._json(200, result)
            return

        if self.path == '/api/judge':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
            except Exception as e:
                self._json(400, {'error': f'bad json: {e}'})
                return

            platform = (payload.get('platform') or '').lower()
            content = payload.get('content') or ''
            if platform not in VALID_PLATFORMS or not content.strip():
                self._json(400, {'error': 'platform and content required'})
                return

            model = payload.get('model')  # judge model key (from the dropdown), optional
            generator_model = payload.get('generator_model')
            gen_id = payload.get('generation_id')
            source_brief = payload.get('source_brief')
            # If we know the generation, the data spine is AUTHORITATIVE for the
            # generator model — the client's value is never trusted over it.
            #
            # The old condition only consulted the DB when the client had OMITTED
            # `generator_model`, so supplying one bypassed judge != generator
            # entirely: post content written by gemma3:4b with
            # generator_model="gpt-4o-mini" and gemma3:4b grades its own output.
            # That is the exact incident CLAUDE.md rule 3 exists for, reachable
            # over HTTP. A bogus `generation_id` is refused for the same reason —
            # otherwise it is a one-line way back around the guard.
            #
            # `source_brief` keeps its previous precedence (client value wins, DB
            # fills the gap). A client-supplied brief can still weaken the
            # grounding criteria; that is a separate hole, noted not fixed.
            if gen_id is not None:
                g = feedback_db.get_generation(gen_id)
                if not g:
                    self._json(400, {'error': f'unknown generation_id: {gen_id}'})
                    return
                recorded = g.get('model')
                if recorded:
                    if generator_model and generator_model != recorded:
                        print(f"[judge] ignoring client generator_model="
                              f"{generator_model!r} for generation {gen_id}; "
                              f"recorded model is {recorded!r}")
                    generator_model = recorded
                if source_brief is None:
                    source_brief = g.get('original_input')

            try:
                verdict = judge.judge(content, platform, model=model,
                                      generator_model=generator_model,
                                      source_brief=source_brief)
            except ValueError as ve:
                self._json(400, {'error': str(ve)})
                return
            # Record the outcome, whatever it was. This endpoint is synchronous so a
            # claim buys no crash-safety, but writing 'abstained' and 'failed' as
            # statuses keeps the two distinguishable from "never judged" — the
            # distinction the background path also depends on.
            if gen_id is not None and verdict.get('judge_model'):
                status = ('graded' if verdict.get('ok') and verdict.get('overall') is not None
                          and not verdict.get('abstained')
                          else 'abstained' if verdict.get('abstained') else 'failed')
                try:
                    row_id, _prior = feedback_db.claim_judge_result(
                        generation_id=gen_id, platform=platform,
                        judge_model=verdict.get('judge_model'))
                    feedback_db.finish_judge_result(
                        row_id, status,
                        overall=verdict.get('overall') if status == 'graded' else None,
                        safety_pass=verdict.get('safety_pass') if status == 'graded' else None,
                        scores=verdict.get('scores') if status == 'graded' else None,
                        summary=(verdict.get('summary') if status == 'graded'
                                 else verdict.get('abstain_reason') or verdict.get('error')),
                    )
                    verdict['judge_result_id'] = row_id
                    verdict['status'] = status
                except Exception as e:
                    print(f"[judge] persist failed: {e}")
            print(f"[judge] {platform} model={verdict.get('judge_model')} "
                  f"ok={verdict.get('ok')} overall={verdict.get('overall')}")
            self._json(200, verdict)
            return

        # /api/compare — fan out the same prompt to every configured provider
        # and return all results so the UI can render them side-by-side.
        if self.path == '/api/compare':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
            except Exception as e:
                self._json(400, {'error': f'bad json: {e}'})
                return

            platform = (payload.get('platform') or '').lower()
            if platform not in VALID_PLATFORMS:
                self._json(400, {'error': f'Unknown platform: {platform}'})
                return

            user_message = (payload.get('messages') or [{}])[0].get('content', '')
            link_url = payload.get('link_url') or ''
            has_image = bool(payload.get('has_image'))

            # Same prompt assembly as /api/gemini so the comparison is apples-to-apples.
            try:
                channel_template = self.load_prompt_from_md(platform)
            except Exception as e:
                self._json(500, {'error': f'prompt load failed: {e}'})
                return
            prompt_version = _prompt_hash(channel_template)
            v_ver = feedback_db.voice_version(platform)
            system_prompt = self._with_voice_examples(platform, channel_template)
            # Two parts, not one string — providers.py puts `system` in each API's
            # native slot. This is the endpoint the model comparison runs through, so
            # flattening here is what made Claude score 36 on a plumbing bug.
            user_turn = f"User content to transform:\n{user_message}"

            # Fan out in parallel. Each provider returns a result dict
            # (see providers.py); failures are surfaced as ok=False rows.
            def run(entry):
                key, model, fn = entry
                result = fn(user_turn, model=model, system=system_prompt)
                # Same strip as the main path, or the comparison would rank models on
                # markdown this pipeline now removes anyway.
                if result.get('ok') and result.get('text'):
                    result['text'] = strip_markdown(result['text'])
                    result['text'], result['grounding_flags'] = strip_ungrounded(
                        result['text'], user_message)
                return key, result

            results = {}
            with ThreadPoolExecutor(max_workers=len(providers.COMPARE_MODELS)) as pool:
                for key, result in pool.map(run, providers.COMPARE_MODELS):
                    results[key] = result

            # Log successful generations from each provider so they can be copied
            # and tracked in feedback_db just like a normal Gemini run.
            for key, r in results.items():
                if not r.get('ok'):
                    continue
                try:
                    eval_result = run_eval(platform, r['text'])
                    gen_id = feedback_db.log_generation(
                        platform=platform,
                        original_input=user_message,
                        generated_content=r['text'],
                        link_url=link_url,
                        has_image=has_image,
                        eval_score=eval_result['total'],
                        eval_detail=json.dumps(eval_result['criteria']),
                        model=r['model'],
                        prompt_version=prompt_version,
                        voice_version=v_ver,
                    )
                    r['generation_id'] = gen_id
                    r['eval_score'] = eval_result['total']
                    print(f"[compare] {platform} {key} model={r['model']} "
                          f"score={eval_result['total']:.1f} cost=${r['cost_usd']:.4f} "
                          f"latency={r['latency_ms']}ms id={gen_id}")
                except Exception as log_err:
                    print(f"[compare] log failed for {platform}/{key}: {log_err}")

            self._json(200, {'platform': platform, 'results': results})
            return

        # Handle /api/gemini endpoint
        if self.path == '/api/gemini':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            api_key = os.getenv('GEMINI_API_KEY') or data.get('api_key')
            if not api_key:
                self._json(400, {'error': 'GEMINI_API_KEY not set'})
                return

            platform = (data.get('platform') or '').lower()
            if platform not in VALID_PLATFORMS:
                self._json(400, {'error': f'Unknown platform: {platform}'})
                return

            user_message = data.get('messages', [{}])[0].get('content', '')
            link_url    = data.get('link_url', '') or ''
            has_image   = bool(data.get('has_image'))
            judge_model = data.get('judge_model')  # optional: chosen in the UI dropdown
            generator_key = data.get('generator_model')  # optional: which model writes

            # Cache check — a prior generation with this exact key IS the cache entry.
            # A hit returns a real generation (content + id), so a copy of cached
            # content links correctly and can never be orphaned.
            v_ver = feedback_db.voice_version(platform)
            # The key must describe what PRODUCED the text, not only the input, so the
            # channel prompt and the RESOLVED generator are computed before the lookup
            # rather than after it. With an input-only key, asking a second model for a
            # brief the first model had already written returned the first model's post
            # under the second one's name — and the cached row still carried the
            # original model, so the swap was invisible in the data spine too. That is
            # a silent failure of the one experiment /api/compare exists to run.
            channel_template = self.load_prompt_from_md(platform)
            prompt_version = _prompt_hash(channel_template)
            try:
                _gk, _gl, resolved_model, _gf = generators.resolve(generator_key)
            except ValueError as ve:
                self._json(400, {'error': str(ve)})
                return
            cache_key = feedback_db.make_cache_key(platform, user_message, link_url,
                                                   has_image, v_ver,
                                                   resolved_model, prompt_version)
            cached = feedback_db.generation_by_cache_key(cache_key)
            if cached:
                print(f"[cache] HIT  {platform} key={cache_key[:12]}… id={cached['id']}")
                self._json(200, {
                    'content': [{'text': cached['generated_content']}],
                    'generation_id': cached['id'],
                    'from_cache': True,
                })
                return
            print(f"[cache] MISS {platform} key={cache_key[:12]}…  voice_v={v_ver} "
                  f"model={resolved_model}")

            # Build prompt entirely server-side — frontend no longer sends system.
            # channel_template and prompt_version are loaded above the cache check,
            # because the key is derived from them.
            system_prompt = self._with_voice_examples(platform, channel_template)
            # Two parts, not one string — providers.py puts `system` in each API's
            # native slot. Gemini re-concatenates in exactly this order, so its prompt
            # stays byte-identical and its scored history remains comparable.
            user_turn = f"User content to transform:\n{user_message}"

            # Generate via the swappable registry (generators.py). call_gemini keeps
            # thinkingBudget=0 — gemini-2.5-flash counts reasoning tokens against the
            # output budget, which silently truncated mid-length posts mid-sentence.
            try:
                gen = generators.generate(user_turn, model_key=generator_key,
                                          system=system_prompt)
                gen_model = gen.get('generator_model') or GEMINI_MODEL
                if gen.get('ok') and gen.get('text'):
                        # Strip ONCE, here — before eval, persist, cache, judge and the
                        # UI response, which all read `text` below. One canonical string
                        # means the heuristic, the judge and the human grade the same
                        # bytes the user will actually publish.
                        text = strip_markdown(gen['text'])
                        # Then the grounding guard. Seven local models, six channels,
                        # one brief: every one invented a weekday or restyled the
                        # event, and both rules are stated explicitly — in Korean and
                        # English — in every channel prompt. Korean-native models broke
                        # them as readily as the English-first ones, so this is neither
                        # a model-choice nor a prompt-wording problem, and code answers
                        # it (CLAUDE.md rule 5). Weekdays and placeholders absent from
                        # the brief are deleted; restyle nouns are only flagged, since
                        # cutting 세미나 out of a sentence leaves broken Korean.
                        text, ground_flags = strip_ungrounded(text, user_message)
                        if ground_flags:
                            print(f"[ground] {platform} " +
                                  ", ".join(f"{k}:{v}" for k, v in ground_flags))
                        result = {'content': [{'text': text}], 'generator_model': gen_model,
                                  'grounding_flags': ground_flags}

                        # Eval + persist + cache
                        if platform in VALID_PLATFORMS:
                            try:
                                eval_result = run_eval(platform, text)
                                score = eval_result['total']
                                try:
                                    gen_id = feedback_db.log_generation(
                                        platform=platform,
                                        original_input=user_message,
                                        generated_content=text,
                                        link_url=link_url,
                                        has_image=has_image,
                                        eval_score=score,
                                        eval_detail=json.dumps(eval_result['criteria']),
                                        model=gen_model,
                                        prompt_version=prompt_version,
                                        voice_version=v_ver,
                                        cache_key=cache_key,
                                    )
                                except Exception:
                                    # Concurrent identical request already inserted this
                                    # cache_key (unique) — reuse that generation.
                                    existing = feedback_db.generation_by_cache_key(cache_key)
                                    if not existing:
                                        raise
                                    gen_id = existing['id']
                                result['generation_id'] = gen_id
                                print(f"[gen] {platform} id={gen_id} score={score:.1f}/100 chars={len(text)}")
                                # Tiered cascade: heuristic already ran; if it flagged
                                # this generation, judge it in the background (async).
                                if JUDGE_ON_GENERATE:
                                    import threading
                                    threading.Thread(
                                        target=self._maybe_judge,
                                        args=(platform, text, gen_id, score, judge_model,
                                              user_message, gen_model),
                                        daemon=True,
                                    ).start()
                            except Exception as log_err:
                                print(f"[gen] log failed for {platform}: {log_err}")
                else:
                    result = {'error': gen.get('error') or f'No response from {gen_model}'}

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            
            except urllib.error.HTTPError as e:
                error_data = e.read().decode('utf-8')
                self.send_response(e.code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(error_data.encode())
            
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            # For other requests, use default handler
            super().do_POST()

PUBLISH_POLL_SECONDS = 15


def _run_publish_job(job):
    """One job: claim it, publish through the right provider, record the
    outcome. Every branch — success, a platform rejection, an unexpected
    exception — ends in complete_publish_job, so a job never sits in
    'publishing' forever because of a bug in this function."""
    if not feedback_db.claim_publish_job(job['id']):
        return  # already claimed by another tick or process
    try:
        account = feedback_db.get_oauth_tokens(job['oauth_account_id'])
        if not account:
            raise oauth_providers.OAuthError(
                'the connected account was disconnected before this job ran')
        gen = feedback_db.get_generation(job['generation_id'])
        if not gen:
            raise oauth_providers.OAuthError('the source generation no longer exists')
        text = gen['generated_content']
        # Re-fingerprint what we are ABOUT to send against what was approved at
        # enqueue time. A voice-profile resynthesis or a later edit to the same
        # generation row between enqueue and publish would otherwise let a job
        # publish text nobody approved in this exact form.
        import hashlib as _hashlib
        latest = _hashlib.sha256(text.encode('utf-8')).hexdigest()
        if latest != job['content_fingerprint']:
            raise oauth_providers.OAuthError(
                'content changed since this was approved for publishing — '
                're-approve and re-queue it')
        if job['platform'] == 'linkedin':
            post_id = oauth_providers.linkedin_publish(
                account['access_token'], account['external_id'], text)
        else:
            post_id = oauth_providers.instagram_publish(
                account['page_token'], account['external_id'], text, image_url=None)
        feedback_db.complete_publish_job(job['id'], remote_post_id=post_id)
        print(f"[publish] {job['platform']} job={job['id']} -> {post_id}")
    except Exception as e:
        feedback_db.complete_publish_job(job['id'], error=str(e))
        print(f"[publish] {job['platform']} job={job['id']} FAILED: {e}")


def _publish_scheduler_loop():
    """Runs for the lifetime of the process. Scheduling therefore only works
    while server.py is running — a laptop that sleeps, or a killed process,
    means a scheduled post does not go out at its time. That limit is
    structural to a local-only server and is surfaced in the UI, not hidden
    here."""
    while True:
        try:
            for job in feedback_db.due_publish_jobs():
                _run_publish_job(job)
        except Exception as e:
            print(f"[publish] scheduler tick failed: {e}")
        _time.sleep(PUBLISH_POLL_SECONDS)


if __name__ == '__main__':
    api_port = os.getenv('API_PORT')
    if not api_port:
        sys.exit('API_PORT not set. Add it to .env (see .env.example).')
    PORT = int(api_port)
    server = ThreadingHTTPServer(('localhost', PORT), CORSRequestHandler)
    threading.Thread(target=_publish_scheduler_loop, daemon=True).start()
    print(f'Server running on http://localhost:{PORT}')
    print(f'Publish scheduler polling every {PUBLISH_POLL_SECONDS}s')
    print('Press Ctrl+C to stop')
    server.serve_forever()
