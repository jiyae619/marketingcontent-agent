import { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { Button } from '../Button/Button';
import './ReviewPanel.css';

const FAMILY_LEAD = {
  voice: 'Reads wrong',
  grounding: 'Facts wrong',
};

/**
 * Per-platform review surface: approve, or reject / edit with reasons.
 *
 * A review can name SEVERAL defects — "the date is wrong AND it reads like a
 * brochure" is one review with two reasons — so the chips are a multi-select and
 * the picked set stays visible while you type the note. The family of each chip
 * is what routes the row (voice -> the voice profile, grounding -> the defect
 * list), and a review that is both must reach both, which is why the set is sent
 * rather than a single winner.
 *
 * The note is free text and is never parsed. It exists because the chips are a
 * fixed taxonomy and the reason a draft is wrong often is not.
 */
export function ReviewPanel({ platform, content, generationId, onStatus }) {
  const [flags, setFlags] = useState([]);
  // null = closed. Otherwise { mode: 'reject' | 'edit', pct }.
  const [review, setReview] = useState(null);
  const [picked, setPicked] = useState([]);
  const [note, setNote] = useState('');
  const [verdict, setVerdict] = useState(null);

  useEffect(() => {
    fetch('/api/flags').then((r) => r.json()).then((d) => setFlags(d.taxonomy || [])).catch(() => {});
  }, []);

  useEffect(() => {
    setVerdict(null); setReview(null); setPicked([]); setNote('');
  }, [generationId]);

  const toggle = (category) =>
    setPicked((prev) => (prev.includes(category)
      ? prev.filter((c) => c !== category)
      : [...prev, category]));

  const close = () => { setReview(null); setPicked([]); setNote(''); };

  const postVerdict = async (body, okMsg) => {
    try {
      const res = await fetch('/api/copies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const d = await res.json();
      if (res.ok) { setVerdict(d.verdict); onStatus?.('success', okMsg(d.verdict)); return { ok: true, d }; }
      // A missing chip is not an error the reviewer should see as one — it is the
      // next step of the flow, so it is handled by the caller rather than shouted.
      if (!d?.choices) onStatus?.('error', d.error || 'Could not record verdict');
      return { ok: false, d };
    } catch {
      onStatus?.('error', 'Verdict request failed');
      return { ok: false, d: null };
    }
  };

  const okMsg = (v) => (v === 'edit' ? `✓ Saved your edit for ${platform}` : `✓ Approved ${platform}`);

  const approve = async () => {
    // An edit is classified SERVER-side (it compares against the stored original,
    // which this component does not hold), so the flow is: submit, and if the
    // server says reasons are required, open the panel and resubmit.
    const { ok, d } = await postVerdict(
      { platform, final_content: content, generation_id: generationId }, okMsg,
    );
    if (!ok) {
      if (d?.choices) setReview({ mode: 'edit', pct: d.pct_changed });
      return;
    }
    try { await navigator.clipboard.writeText(content); } catch { /* clipboard optional */ }
  };

  const submitReview = async () => {
    const isEdit = review?.mode === 'edit';
    if (isEdit && picked.length === 0) return;
    const { ok } = await postVerdict(
      isEdit
        ? { platform, final_content: content, generation_id: generationId,
            flag_categories: picked, edit_note: note || undefined }
        : { platform, verdict: 'reject', generation_id: generationId,
            flag_categories: picked, edit_note: note || undefined },
      isEdit ? okMsg : () => `Rejected ${platform}${picked.length ? ` — ${picked.length} reason(s)` : ''}`,
    );
    if (!ok) return;
    close();
    if (isEdit) {
      try { await navigator.clipboard.writeText(content); } catch { /* clipboard optional */ }
    }
  };

  const canReview = Boolean(content) && !content.startsWith('Error:') && content !== 'Generating...';
  if (!canReview) return null;

  const isEdit = review?.mode === 'edit';
  const byFamily = (fam) => flags.filter((f) => f.family === fam);

  return (
    <div className="review-panel">
      <div className="rp-actions">
        <Button variant="primary" size="small" onClick={approve}>✓ Approve &amp; copy</Button>
        <Button variant="secondary" size="small"
                onClick={() => setReview((r) => (r ? null : { mode: 'reject' }))}>
          ✕ Reject &amp; flag
        </Button>
        <span className="rp-actions-spacer" />
        {verdict && <span className={`rp-verdict rp-verdict-${verdict}`}>Recorded: {verdict}</span>}
        <span className="rp-later">on approve → schedule / publish (later)</span>
      </div>

      {review && (
        <div className="rp-flags">
          <div className="rp-flags-lead">
            {isEdit ? (
              <>
                You changed <b>{review.pct ?? '—'}%</b> of this draft. What kind of change was it?
                {' '}A style fix teaches the voice loop; a fact fix never does.
              </>
            ) : (
              <>What was wrong? Pick every reason that applies — each one is a labeled
                example, and a review can be more than one thing.</>
            )}
          </div>

          {['voice', 'grounding'].map((fam) => (
            byFamily(fam).length > 0 && (
              <div className="rp-chip-row" key={fam}>
                <span className="rp-chip-rowlabel">{FAMILY_LEAD[fam]}</span>
                <div className="rp-chips">
                  {byFamily(fam).map((f) => {
                    const on = picked.includes(f.category);
                    return (
                      <button key={f.category} type="button"
                              aria-pressed={on}
                              className={`rp-chip rp-chip-${f.family}${on ? ' rp-chip-on' : ''}`}
                              onClick={() => toggle(f.category)}>
                        <span className="rp-chip-check" aria-hidden="true">{on ? '✓' : ''}</span>
                        {f.category.replace(/_/g, ' ')}
                      </button>
                    );
                  })}
                </div>
              </div>
            )
          ))}

          {/* The picked set stays visible while the note is written, so it is
              possible to check what was selected without scrolling back up. */}
          <div className="rp-picked">
            {picked.length === 0
              ? <span className="rp-picked-none">No reasons selected yet</span>
              : picked.map((c) => (
                  <span key={c} className="rp-picked-tag">
                    {c.replace(/_/g, ' ')}
                    <button type="button" className="rp-picked-x"
                            aria-label={`Remove ${c}`} onClick={() => toggle(c)}>×</button>
                  </span>
                ))}
          </div>

          <label className="rp-note-label" htmlFor={`rp-note-${platform}`}>
            Your notes {isEdit ? '(optional)' : '— what specifically went wrong?'}
          </label>
          <textarea id={`rp-note-${platform}`} className="rp-note" maxLength={500} rows={3}
                    value={note}
                    placeholder="e.g. invented a venue that isn't in the brief; the closing line reads like a press release"
                    onChange={(e) => setNote(e.target.value)} />
          <div className="rp-note-count">{note.length}/500 · free text, never parsed — a human reads it</div>

          <div className="rp-chip-row">
            <Button variant="primary" size="small" onClick={submitReview}
                    disabled={isEdit && picked.length === 0}>
              {isEdit ? 'Save edit' : 'Record rejection'}
            </Button>
            <button type="button" className="rp-chip rp-chip-plain" onClick={close}>Cancel</button>
            {isEdit && picked.length === 0 && (
              <span className="rp-hint">Pick at least one reason — an unlabelled edit cannot be routed.</span>
            )}
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
  onStatus: PropTypes.func,
};
