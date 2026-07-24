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
from evaluators import evaluate as run_eval
import providers
import judge
from concurrent.futures import ThreadPoolExecutor

feedback_db.init_db()

VALID_PLATFORMS = ['linkedin', 'instagram', 'circle', 'kakaotalk', 'whatsapp', 'x']
VOICE_EXAMPLES_LIMIT = 3

PASSWORD_REQUIRED_MESSAGE = (
    "This is a private preview. Enter the password to generate content — "
    "it keeps the shared Gemini quota from being burned by visitors."
)

GEMINI_MODEL = 'gemini-2.5-flash'

# Tiered eval cascade: heuristic (always, free) -> LLM judge (only on flagged
# content) -> human. After a new generation, the judge runs in the background
# when the heuristic score is below the trigger threshold AND a non-generator
# judge model is reachable; otherwise it no-ops. Both configurable via env.
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

        # Available judge models — the single source the UI dropdown reads.
        if self.path == '/api/judge/models':
            self._json(200, {'models': judge.available_models(),
                             'default': judge.DEFAULT_JUDGE_KEY})
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

    def _maybe_synthesize_voice(self, platform: str, api_key: str) -> None:
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

            gemini_url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}'
            payload = {
                "contents": [{"parts": [{"text": synthesis_prompt}]}],
                "generationConfig": {"maxOutputTokens": 200},
            }
            req = urllib.request.Request(
                gemini_url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as resp:
                rd = json.loads(resp.read().decode())
                if "candidates" in rd and rd["candidates"]:
                    style = rd["candidates"][0]["content"]["parts"][0]["text"].strip()
                    feedback_db.save_voice_profile(platform, style)
                    print(f"[voice] synthesized {platform} ({count} copies → {len(style)} chars)")
        except Exception as e:
            print(f"[voice] synthesis failed for {platform}: {e}")
    
    def _maybe_judge(self, platform, content, generation_id, heuristic_score):
        """Tiered cascade step (runs in a background thread, never blocks generation).

        Skips when the heuristic already scored the content at/above the trigger
        threshold — the LLM judge tier is spent only on flagged content. No-ops
        gracefully when no non-generator judge model is reachable (judge != generator
        needs a second provider). Persists the verdict to judge_results.
        """
        try:
            if heuristic_score is not None and heuristic_score >= JUDGE_TRIGGER_THRESHOLD:
                return  # heuristic says it's good enough — skip the paid judge tier
            verdict = judge.judge(content, platform, generator_model=GEMINI_MODEL)
            if not verdict.get('ok'):
                print(f"[judge] gen {generation_id} not judged: {verdict.get('error')}")
                return
            feedback_db.log_judge_result(
                generation_id=generation_id, platform=platform,
                judge_model=verdict.get('judge_model'),
                overall=verdict.get('overall'),
                safety_pass=verdict.get('safety_pass'),
                scores=verdict.get('scores'),
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

        # /api/copies — user copied/approved content (writes a verdict event)
        if self.path == '/api/copies':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                platform = payload.get('platform', '').lower()
                final = payload.get('final_content', '')
                gen_id = payload.get('generation_id')
                if platform not in VALID_PLATFORMS or not final.strip():
                    self._json(400, {'error': 'platform and final_content required'})
                    return
                # Reject non-genuine content (error strings / placeholder) so it
                # can never enter voice training.
                if not feedback_db.is_genuine_content(final):
                    self._json(400, {'error': 'final_content is not genuine content'})
                    return
                # Look up the linked generation to verify it belongs to this
                # platform and to classify approve vs edit by comparing texts.
                original = None
                if gen_id is not None:
                    gen = feedback_db.get_generation(gen_id)
                    if gen is None:
                        # Dangling id (e.g. a rotated DB) — record the approval
                        # unlinked rather than dropping the signal.
                        gen_id = None
                    elif gen['platform'] != platform:
                        self._json(400, {'error': 'generation_id does not match platform'})
                        return
                    else:
                        original = gen['generated_content']
                verdict = feedback_db.classify_verdict(original, final)
                try:
                    row_id = feedback_db.log_feedback(
                        generation_id=gen_id,
                        platform=platform,
                        verdict=verdict,
                        original_content=original,
                        final_content=final,
                    )
                except ValueError as ve:
                    self._json(400, {'error': str(ve)})
                    return
                print(f"[feedback] {platform} {verdict} id={row_id} gen={gen_id} "
                      f"chars={len(final)} voice_v={feedback_db.voice_version(platform)}")
                self._json(200, {'id': row_id, 'platform': platform, 'verdict': verdict})

                # Trigger voice synthesis if enough samples accumulated (async-ish)
                api_key = os.getenv('GEMINI_API_KEY')
                if api_key:
                    import threading
                    threading.Thread(
                        target=self._maybe_synthesize_voice,
                        args=(platform, api_key),
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
            # If we know the generation, use its recorded model (provenance from the
            # data spine) to enforce judge != generator automatically.
            if generator_model is None and gen_id is not None:
                g = feedback_db.get_generation(gen_id)
                if g:
                    generator_model = g.get('model')

            try:
                verdict = judge.judge(content, platform,
                                      model=model, generator_model=generator_model)
            except ValueError as ve:
                self._json(400, {'error': str(ve)})
                return
            # Persist a successful verdict when it grades a tracked generation.
            if verdict.get('ok') and gen_id is not None:
                try:
                    row_id = feedback_db.log_judge_result(
                        generation_id=gen_id, platform=platform,
                        judge_model=verdict.get('judge_model'),
                        overall=verdict.get('overall'),
                        safety_pass=verdict.get('safety_pass'),
                        scores=verdict.get('scores'),
                    )
                    verdict['judge_result_id'] = row_id
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
            full_prompt = f"{system_prompt}\n\nUser content to transform:\n{user_message}"

            # Fan out in parallel. Each provider returns a result dict
            # (see providers.py); failures are surfaced as ok=False rows.
            def run(entry):
                key, model, fn = entry
                result = fn(full_prompt, model=model)
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
            full_prompt = f"{system_prompt}\n\nUser content to transform:\n{user_message}"

            # Forward request to Gemini API
            try:
                gemini_url = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}'

                # Gemini 2.5 Flash has "thinking" enabled by default and reasoning
                # tokens count against the output budget — which silently truncates
                # mid-length output (LinkedIn/Instagram saw cuts mid-sentence).
                # Content generation doesn't need chain-of-thought; disable it.
                gemini_payload = {
                    "contents": [{"parts": [{"text": full_prompt}]}],
                    "generationConfig": {
                        "thinkingConfig": {"thinkingBudget": 0},
                    },
                }
                
                req = urllib.request.Request(
                    gemini_url,
                    data=json.dumps(gemini_payload).encode('utf-8'),
                    headers={
                        'Content-Type': 'application/json'
                    }
                )
                
                with urllib.request.urlopen(req) as response:
                    response_data = json.loads(response.read().decode('utf-8'))

                    if 'candidates' in response_data and len(response_data['candidates']) > 0:
                        text = response_data['candidates'][0]['content']['parts'][0]['text']
                        result = {'content': [{'text': text}]}

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
                                        model=GEMINI_MODEL,
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
                                        args=(platform, text, gen_id, score),
                                        daemon=True,
                                    ).start()
                            except Exception as log_err:
                                print(f"[gen] log failed for {platform}: {log_err}")
                    else:
                        result = {'error': 'No response from Gemini'}

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
