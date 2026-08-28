import { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import './GeneratingOverlay.css';

const LABEL = {
  linkedin: 'LinkedIn', instagram: 'Instagram', circle: 'CIRCLE',
  kakaotalk: 'Kakaotalk', whatsapp: 'WhatsApp', x: 'X',
};

// After this fix (providers.py: threading.Semaphore(1) around call_local), a
// generation batch is fully serialized — measured 250-370s for a call that
// takes 25-75s uncontended when several platforms queue behind each other.
// A user watching a spinner with no per-platform breakdown for minutes has no
// way to tell "still working" from "stuck"; this is the same information
// ReviewPanel already surfaces per verdict, one level up at the batch level.
function statusFor(content) {
  if (content == null || content === 'Generating...') return 'pending';
  if (typeof content === 'string' && content.startsWith('Error:')) return 'error';
  return 'done';
}

export function GeneratingOverlay({ visible, platforms, contentByPlatform }) {
  // Non-blocking by design: fixed corner card, not a modal — the rest of the
  // UI (scrolling, other tabs, prior results) stays interactable the whole
  // time. Holds a brief "all done" state after generation finishes so the
  // final tally is visible for a moment instead of vanishing the instant the
  // last platform lands.
  const [prevVisible, setPrevVisible] = useState(visible);
  const [holding, setHolding] = useState(false);

  // Adjusting state in response to a prop change, done during render per
  // https://react.dev/learn/you-might-not-need-an-effect — not in an effect,
  // so there is no synchronous setState-in-effect to cause a cascading render.
  if (visible !== prevVisible) {
    setPrevVisible(visible);
    if (!visible) setHolding(true);
  }

  // The delayed dismiss is genuinely async, so it belongs in an effect.
  useEffect(() => {
    if (!holding) return undefined;
    const t = setTimeout(() => setHolding(false), 1800);
    return () => clearTimeout(t);
  }, [holding]);

  if (!visible && !holding) return null;

  const statuses = platforms.map((p) => ({ id: p, status: statusFor(contentByPlatform[p]) }));
  const doneCount = statuses.filter((s) => s.status !== 'pending').length;
  const errorCount = statuses.filter((s) => s.status === 'error').length;
  const allDone = doneCount === statuses.length;

  return (
    <div className={`gen-overlay ${allDone ? 'gen-overlay--done' : ''}`} role="status" aria-live="polite">
      <div className="gen-overlay-head">
        <span className="gen-orb" aria-hidden="true">
          <span className="gen-orb-ring" />
          <span className="gen-orb-ring gen-orb-ring--delay" />
        </span>
        <div className="gen-overlay-headline">
          <strong>{allDone ? 'Done generating' : 'Generating content…'}</strong>
          <span className="gen-overlay-count">
            {doneCount}/{statuses.length} platform{statuses.length === 1 ? '' : 's'}
            {errorCount > 0 ? ` · ${errorCount} failed` : ''}
          </span>
        </div>
      </div>

      <ul className="gen-overlay-list">
        {statuses.map(({ id, status }) => (
          <li key={id} className={`gen-overlay-row gen-overlay-row--${status}`}>
            <span className={`gen-dot gen-dot--${id}`} aria-hidden="true" />
            <span className="gen-overlay-label">{LABEL[id] || id}</span>
            <span className="gen-overlay-icon" aria-hidden="true">
              {status === 'pending' && <span className="gen-spinner-sm" />}
              {status === 'done' && '✓'}
              {status === 'error' && '!'}
            </span>
          </li>
        ))}
      </ul>

      <div className="gen-overlay-bar">
        <div className="gen-overlay-bar-fill" style={{ width: `${(doneCount / statuses.length) * 100}%` }} />
      </div>
    </div>
  );
}

GeneratingOverlay.propTypes = {
  visible: PropTypes.bool.isRequired,
  platforms: PropTypes.arrayOf(PropTypes.string).isRequired,
  contentByPlatform: PropTypes.object.isRequired,
};
