# Marketing Channel Agent

![bughunt](https://github.com/jiyae619/marketingcontent-agent/actions/workflows/bughunt.yml/badge.svg)

Paste raw content once, generate platform-tailored versions for LinkedIn, Instagram,
CIRCLE, KakaoTalk, WhatsApp, and X in parallel — each graded by an LLM judge against a
shared flag taxonomy, with a human-in-the-loop panel to approve, edit, or reject before
anything ships.

Runs entirely on local models by default. No paid API call happens unless you
explicitly turn that off.

## Quick start

Prerequisites: Node 20+, Python 3.12+, and (for local generation/judging)
[Ollama](https://ollama.com) running on the same machine.

**1. Install dependencies**

```bash
npm install
pip install -r requirements.txt   # Homebrew Python: add --break-system-packages, or use a venv
```

**2. Configure environment**

```bash
cp .env.example .env
```

Then set, at minimum:

```
LOCAL_ONLY=true
API_PORT=8081
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=<generator model, e.g. gemma3:4b>
LOCAL_JUDGE_MODEL=<a DIFFERENT model — the judge must not be the same model as the generator>
```

Two things worth knowing before you run anything:

- `LOCAL_ONLY` **defaults to `false` if left unset.** Set it explicitly — otherwise a
  cloud API key sitting in your environment can let a paid provider get called.
- `LOCAL_JUDGE_MODEL` **falls back to `LOCAL_LLM_MODEL` if left unset**, which lets a
  model grade its own output. Set both, to two different models.

Run `python3 scripts/preflight.py` after editing — it prints the *resolved* config
(not just what `.env` says) and fails loudly if either of the above is wrong.

**3. Run it** (two terminals)

```bash
python3 server.py   # backend — http://localhost:8081, /api/* only, no browsable homepage
npm run dev          # frontend — http://localhost:5173, proxies /api to the backend
```

Open http://localhost:5173.

## Architecture

- **Frontend** — React 19 + Vite (`src/`). Talks to the backend only via same-origin
  `fetch('/api/...')`; there's no configurable API base URL.
- **Backend** — `server.py`, a single-file Python stdlib `http.server`. Binds to
  `localhost` only — there is no hosted deployment of it, by design.
- **Generation & judging** — `generators.py` / `judge.py`, two parallel model
  registries behind one call interface in `providers.py`. Under `LOCAL_ONLY=true`,
  paid providers are stripped from both registries *and* separately refused at the
  call site, so no dropdown, fallback, or stray argument can reach one.
- **Data** — `feedback_db.py`, SQLite via the stdlib (no ORM). Every generation, judge
  verdict, and human decision is recorded there.

## Testing

- `python3 scripts/test_feedback_db.py` — write-path fixture for the data layer, no
  server needed.
- `python3 tools/bughunt/bughunt.py` — deterministic checks (clean-clone build, lint,
  data layer, judge invariants). Runs in CI on every push and PR into `main`; see
  [`tools/bughunt/README.md`](tools/bughunt/README.md).
- [`TESTING_GUIDE.md`](TESTING_GUIDE.md) — the eval-runner / golden-set flow for
  testing generated content quality.

## More

- [`PYTHON_FILES_GUIDE.md`](PYTHON_FILES_GUIDE.md) — plain-language walkthrough of the
  backend files.
- [`CLAUDE.md`](CLAUDE.md) — the project's hard constraints (local-only generation, the
  4B local-model tier, judge ≠ generator) and the incident behind each one.
