from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import hashlib
import json
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
from evaluators import evaluate as run_eval, strip_markdown
import providers
import judge
import generators
from concurrent.futures import ThreadPoolExecutor

feedback_db.init_db()

VALID_PLATFORMS = ['linkedin', 'instagram', 'circle', 'kakaotalk', 'whatsapp', 'x']
VOICE_EXAMPLES_LIMIT = 3

PASSWORD_REQUIRED_MESSAGE = (
    "This is a private preview. Enter the password to generate content — "
    "it keeps the shared Gemini quota from being burned by visitors."
)

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

class CORSRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS for all origins
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, x-api-key, x-app-password')
        super().end_headers()

    def _password_ok(self):
        expected = os.getenv('APP_PASSWORD')
        if not expected:
            return False
        provided = self.headers.get('x-app-password', '')
        return provided == expected
    
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

        # Flag taxonomy for the review UI's flag chips — one source of truth.
        if self.path == '/api/flags':
            self._json(200, {'taxonomy': [
                {'category': c, 'family': f}
                for c, f in feedback_db.FLAG_TAXONOMY.items()
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
        """Triggered after a copy is logged. If enough new copies exist, synthesize."""
        try:
            count = feedback_db.copy_count(platform)
            existing = feedback_db.get_voice_profile(platform)
            # Synthesize on first copy and every 3 thereafter
            if count == 0 or (existing is not None):
                return
            examples = feedback_db.recent_copies(platform, limit=6)
            if not examples:
                return

            samples_text = "\n\n---\n".join(
                f"Sample {i+1}:\n{ex['final_content']}"
                for i, ex in enumerate(examples)
            )
            synthesis_prompt = (
                f"You are analyzing writing samples from a marketer to extract their voice profile.\n\n"
                f"Platform: {platform}\n\n"
                f"Samples:\n{samples_text}\n\n"
                f"Write a concise voice profile (3-5 sentences, under 120 words) describing:\n"
                f"- Sentence length and rhythm\n"
                f"- Tone (formal/casual, direct/warm, etc.)\n"
                f"- Characteristic words, phrases, or patterns\n"
                f"- What they emphasize and what they avoid\n\n"
                f"Return ONLY the voice profile description, nothing else."
            )

            # Route through providers.call_gemini, which sets thinkingBudget=0.
            # A raw call with maxOutputTokens=200 and no thinking budget lets
            # gemini-2.5-flash spend the cap on internal reasoning, returning a
            # profile truncated mid-sentence ("The marketer employs a direct,").
            res = providers.call_gemini(synthesis_prompt)
            if res.get("ok") and res.get("text"):
                style = res["text"].strip()
                feedback_db.save_voice_profile(platform, style)
                print(f"[voice] synthesized {platform} ({count} copies → {len(style)} chars)")
            else:
                print(f"[voice] synthesis returned nothing for {platform}: {res.get('error')}")
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
        # Generation endpoints all require the shared password.
        if self.path in ('/api/copies', '/api/gemini', '/api/compare', '/api/judge'):
            if not self._password_ok():
                self._json(401, {
                    'error': 'password_required',
                    'message': PASSWORD_REQUIRED_MESSAGE,
                })
                return

        # /api/copies — human verdict on generated content (approve / edit / reject),
        # optionally carrying one flag from the shared taxonomy.
        if self.path == '/api/copies':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                platform = payload.get('platform', '').lower()
                final = payload.get('final_content', '')
                gen_id = payload.get('generation_id')
                verdict_override = payload.get('verdict')       # explicit, e.g. 'reject'
                flag_category = payload.get('flag_category')    # optional taxonomy flag
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

                try:
                    row_id = feedback_db.log_feedback(
                        generation_id=gen_id,
                        platform=platform,
                        verdict=verdict,
                        original_content=original,
                        final_content=final_content,
                        flag_category=flag_category,
                    )
                except ValueError as ve:
                    self._json(400, {'error': str(ve)})
                    return
                print(f"[feedback] {platform} {verdict} id={row_id} gen={gen_id} "
                      f"flag={flag_category or '-'} voice_v={feedback_db.voice_version(platform)}")
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
            # If we know the generation, pull both from the data spine: its recorded
            # model (to enforce judge != generator) and its original_input, which the
            # grounding criteria are defined against.
            if gen_id is not None and (generator_model is None or source_brief is None):
                g = feedback_db.get_generation(gen_id)
                if g:
                    if generator_model is None:
                        generator_model = g.get('model')
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
            cache_key = feedback_db.make_cache_key(platform, user_message, link_url, has_image, v_ver)
            cached = feedback_db.generation_by_cache_key(cache_key)
            if cached:
                print(f"[cache] HIT  {platform} key={cache_key[:12]}… id={cached['id']}")
                self._json(200, {
                    'content': [{'text': cached['generated_content']}],
                    'generation_id': cached['id'],
                    'from_cache': True,
                })
                return
            print(f"[cache] MISS {platform} key={cache_key[:12]}…  voice_v={v_ver}")

            # Build prompt entirely server-side — frontend no longer sends system.
            channel_template = self.load_prompt_from_md(platform)
            prompt_version = _prompt_hash(channel_template)
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
                        result = {'content': [{'text': text}], 'generator_model': gen_model}

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

if __name__ == '__main__':
    api_port = os.getenv('API_PORT')
    if not api_port:
        sys.exit('API_PORT not set. Add it to .env (see .env.example).')
    PORT = int(api_port)
    server = ThreadingHTTPServer(('localhost', PORT), CORSRequestHandler)
    print(f'Server running on http://localhost:{PORT}')
    print('Press Ctrl+C to stop')
    server.serve_forever()
