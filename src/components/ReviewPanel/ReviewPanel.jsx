import { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { Button } from '../Button/Button';
import './ReviewPanel.css';

const FAMILY_LABEL = { grounding: 'ground', voice: 'voice' };

// A local judge takes 17-54s (measured); call_local's own timeout is 120s. The old
// poller gave up after 8s, so even a successful verdict landed after the UI had
// stopped listening and only appeared if you clicked "Judge this" by hand.
const POLL_STEPS_MS = [1000, 2000, 3000];  // then steady
const POLL_STEADY_MS = 5000;
const POLL_CEILING_MS = 130000;            // just past the provider timeout
// No row yet usually means the heuristic cleared it and no judge was dispatched. But
// all six platforms generate at once, and their claims serialise behind one SQLite
// writer, so a claim can land later than the grace period. Show "skipped" after the
// grace, keep polling to the shorter ceiling in case a claim is merely queued.
const NO_ROW_GRACE_MS = 4000;
const NO_ROW_CEILING_MS = 25000;
const TERMINAL = new Set(['graded', 'abstained', 'failed']);

// The judge writes its row on dispatch, so these are real distinguishable outcomes
// rather than four different ways of showing nothing.
const STATE_TEXT = {
  unknown: 'Checking for a judge grade…',
  pending: 'Judging… local models take 20–60s.',
  skipped: 'Not judged — the heuristic scored this above the escalation threshold.',
  abstained: 'Judge abstained — it could not verify this one, so it declined to guess. Your call.',
  failed: 'Judge failed — no usable verdict came back. Re-run it, or decide unaided.',
  timeout: 'Judge has not finished yet. It may still be running — re-check in a moment.',
};

function scoreColor(score) {
  if (score == null) return 'var(--color-text-tertiary)';
  if (score >= 70) return 'var(--color-success)';
  if (score >= 45) return 'var(--color-warning)';
  return 'var(--color-error)';
}

/**
 * Per-platform review surface: the LLM judge grade (with per-category reasoning
 * and an overall summary) plus explicit approve / reject-with-flag controls.
 * Grade is fetched from GET /api/judge/result (async, background-graded) with a
 * manual "Judge this" fallback; verdicts POST to /api/copies.
 */
export function ReviewPanel({ platform, content, generationId, password, judgeModel, onStatus }) {
  const [grade, setGrade] = useState(null);
  const [judging, setJudging] = useState(false);
  const [flags, setFlags] = useState([]);
  const [rejecting, setRejecting] = useState(false);
  const [verdict, setVerdict] = useState(null);
  const [judgeState, setJudgeState] = useState('unknown');

  useEffect(() => {
    fetch('/api/flags').then((r) => r.json()).then((d) => setFlags(d.taxonomy || [])).catch(() => {});
  }, []);

  // Poll until the verdict reaches a terminal status, not until a fixed clock runs
  // out. Backs off so a slow local judge doesn't mean dozens of requests.
  useEffect(() => {
    setGrade(null); setVerdict(null); setRejecting(false); setJudgeState('unknown');
    if (!generationId) return undefined;

    let cancelled = false;
    let timer;
    let attempt = 0;
    const startedAt = Date.now();

    const tick = async () => {
      if (cancelled) return;
      let d = null;
      try {
        const res = await fetch(`/api/judge/result?generation_id=${generationId}`);
        d = await res.json();
      } catch { /* a dropped request is not a verdict — keep polling */ }
      if (cancelled) return;

      // `status` is absent on rows written before the column existed; infer it.
      const status = d && Object.keys(d).length
        ? (d.status || (d.overall != null ? 'graded' : 'pending'))
        : null;

      const elapsed = Date.now() - startedAt;
      if (status === null) {
        if (elapsed > NO_ROW_GRACE_MS) setJudgeState('skipped');
        if (elapsed > NO_ROW_CEILING_MS) return;   // no claim is coming
      } else {
        setJudgeState(status);
        if (status === 'graded') setGrade(d);
        if (TERMINAL.has(status)) return;
        if (elapsed > POLL_CEILING_MS) { setJudgeState('timeout'); return; }
      }
      timer = setTimeout(tick, POLL_STEPS_MS[attempt] ?? POLL_STEADY_MS);
      attempt += 1;
    };

    tick();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [generationId]);

  const runJudge = async () => {
    if (!password || !generationId || !content) return;
    setJudging(true);
    try {
      const res = await fetch('/api/judge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-app-password': password },
        body: JSON.stringify({ platform, content, generation_id: generationId, model: judgeModel || undefined }),
      });
      const d = await res.json();
      // `ok` only means the call succeeded. An abstained verdict still carries an
      // `overall`, so rendering on `ok` alone would show a grade the judge explicitly
      // refused to stand behind — the same collapse the status column removed from
      // the background path.
      const st = d.status
        || (d.abstained ? 'abstained' : (d.ok && d.overall != null) ? 'graded' : 'failed');
      setJudgeState(st);
      setGrade(st === 'graded' ? d : null);
      if (st === 'failed') {
        onStatus?.('error', `Judge unavailable: ${d.error || 'no judge model reachable'}`);
      }
    } catch {
      onStatus?.('error', 'Judge request failed');
    } finally {
      setJudging(false);
    }
  };

  const postVerdict = async (body, okMsg) => {
    if (!password) { onStatus?.('error', 'Enter the password to record a verdict'); return; }
    try {
      const res = await fetch('/api/copies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-app-password': password },
        body: JSON.stringify(body),
      });
      const d = await res.json();
      if (res.ok) { setVerdict(d.verdict); onStatus?.('success', okMsg(d.verdict)); }
      else onStatus?.('error', d.error || 'Could not record verdict');
    } catch {
      onStatus?.('error', 'Verdict request failed');
    }
  };

  const approve = async () => {
    await postVerdict(
      { platform, final_content: content, generation_id: generationId },
      (v) => (v === 'edit' ? `✓ Saved your edit for ${platform}` : `✓ Approved ${platform}`),
    );
    try { await navigator.clipboard.writeText(content); } catch { /* clipboard optional */ }
  };

  const reject = (category) => {
    setRejecting(false);
    return postVerdict(
      { platform, verdict: 'reject', flag_category: category, generation_id: generationId },
      () => `Rejected ${platform}${category ? ` — ${category.replace('_', ' ')}` : ''}`,
    );
  };

  const canReview = Boolean(content) && !content.startsWith('Error:') && content !== 'Generating...';
  if (!canReview) return null;

  return (
    <div className="review-panel">
      <div className="rp-grade">
        {grade ? (
          <>
            <div className="rp-grade-top">
              <div className="rp-ring" style={{ '--rp-pct': `${grade.overall}%`, '--rp-col': scoreColor(grade.overall) }}>
                <span>{grade.overall}</span>
              </div>
              <div className="rp-grade-meta">
                <div className="rp-grade-title">Judge grade — {grade.overall}/100</div>
                <div className="rp-grade-sub">by {grade.judge_model}</div>
              </div>
              <span className={`rp-safety ${grade.safety_pass ? 'pass' : 'fail'}`}>
                {grade.safety_pass ? '✓ Safety: PASS' : '⚠ Safety: FAIL'}
              </span>
            </div>

            {grade.summary && <div className="rp-summary">{grade.summary}</div>}

            <div className="rp-cats">
              {Object.entries(grade.scores || {}).map(([cat, d]) => {
                const fam = (flags.find((f) => f.category === cat) || {}).family;
                return (
                  <div className="rp-cat" key={cat}>
                    <div className="rp-cat-head">
                      <span className="rp-cat-name">
                        {cat.replace(/_/g, ' ')}
                        {fam && <span className={`rp-fam rp-fam-${fam}`}>{FAMILY_LABEL[fam] || fam}</span>}
                      </span>
                      <span className="rp-track"><span className="rp-fill" style={{ width: `${d.score}%`, background: scoreColor(d.score) }} /></span>
                      <span className="rp-sc">{d.score}</span>
                    </div>
                    {d.reason && <div className="rp-reason">{d.reason}</div>}
                  </div>
                );
              })}
            </div>
            <button className="rp-rejudge" onClick={runJudge} disabled={judging}>
              {judging ? 'Re-judging…' : '↻ Re-judge'}
            </button>
          </>
        ) : (
          <div className={`rp-nograde rp-nograde-${judgeState}`}>
            <span className="rp-nograde-text">
              {judgeState === 'pending' && <span className="rp-spin" aria-hidden="true" />}
              {STATE_TEXT[judgeState] || STATE_TEXT.unknown}
            </span>
            <Button variant="secondary" size="small" onClick={runJudge}
                    disabled={judging || !generationId || judgeState === 'pending'}>
              {judging ? 'Judging…' : judgeState === 'abstained' ? '↻ Try again' : '⚖️ Judge this'}
            </Button>
          </div>
        )}
      </div>

      <div className="rp-actions">
        <Button variant="primary" size="small" onClick={approve}>✓ Approve &amp; copy</Button>
        <Button variant="secondary" size="small" onClick={() => setRejecting((v) => !v)}>✕ Reject &amp; flag</Button>
        <span className="rp-actions-spacer" />
        {verdict && <span className={`rp-verdict rp-verdict-${verdict}`}>Recorded: {verdict}</span>}
        <span className="rp-later">on approve → schedule / publish (later)</span>
      </div>

      {rejecting && (
        <div className="rp-flags">
          <div className="rp-flags-lead">Why? Each flag is a labeled example that trains the judge on that exact criterion.</div>
          <div className="rp-chips">
            {flags.map((f) => (
              <button key={f.category} className={`rp-chip rp-chip-${f.family}`} onClick={() => reject(f.category)}>
                <span className="rp-chip-dot" /> {f.category.replace(/_/g, ' ')}
              </button>
            ))}
            <button className="rp-chip rp-chip-plain" onClick={() => reject(null)}>Reject (no flag)</button>
          </div>
        </div>
      )}
    </div>
  );
}

ReviewPanel.propTypes = {
  platform: PropTypes.string.isRequired,
  content: PropTypes.string,
  generationId: PropTypes.number,
  password: PropTypes.string,
  judgeModel: PropTypes.string,
  onStatus: PropTypes.func,
};
