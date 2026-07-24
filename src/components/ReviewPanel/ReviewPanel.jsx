import { useCallback, useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { Button } from '../Button/Button';
import './ReviewPanel.css';

const FAMILY_LABEL = { grounding: 'ground', voice: 'voice' };

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

  useEffect(() => {
    fetch('/api/flags').then((r) => r.json()).then((d) => setFlags(d.taxonomy || [])).catch(() => {});
  }, []);

  const fetchGrade = useCallback(() => {
    if (!generationId) return;
    fetch(`/api/judge/result?generation_id=${generationId}`)
      .then((r) => r.json())
      .then((d) => { if (d && d.overall != null) setGrade(d); })
      .catch(() => {});
  }, [generationId]);

  // Reset + poll for a background grade whenever the generation changes.
  useEffect(() => {
    setGrade(null); setVerdict(null); setRejecting(false);
    if (!generationId) return undefined;
    fetchGrade();
    const timers = [1500, 4000, 8000].map((ms) => setTimeout(fetchGrade, ms));
    return () => timers.forEach(clearTimeout);
  }, [generationId, fetchGrade]);

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
      if (d.ok) setGrade(d);
      else onStatus?.('error', `Judge unavailable: ${d.error || 'no judge model reachable'}`);
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
          <div className="rp-nograde">
            <span className="rp-nograde-text">No judge grade yet — grades appear automatically when the heuristic flags content, or run it now.</span>
            <Button variant="secondary" size="small" onClick={runJudge} disabled={judging || !generationId}>
              {judging ? 'Judging…' : '⚖️ Judge this'}
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
