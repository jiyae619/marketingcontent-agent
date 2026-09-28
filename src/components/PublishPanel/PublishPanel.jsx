import { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { Button } from '../Button/Button';
import './PublishPanel.css';

const PLATFORM_LABEL = { linkedin: 'LinkedIn', instagram: 'Instagram' };

function fmtWhen(ts) {
  if (!ts) return 'now';
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

const STATUS_TEXT = {
  pending: 'queued',
  publishing: 'publishing…',
  success: 'published',
  failed: 'failed',
  canceled: 'canceled',
};

/**
 * Connect / publish / schedule for the two channels with a real publish API
 * (LinkedIn, Instagram — see PUBLISHABLE_PLATFORMS in server.py). Shown only
 * once ReviewPanel has recorded an approve/edit verdict: the backend refuses
 * to enqueue anything without one (enqueue_publish reads the approved text
 * from feedback_events itself), so a Publish button before that point could
 * only ever 400.
 *
 * Publishing itself is scheduling: this POSTs generation_id + account id only,
 * never the text. What actually gets sent is read server-side from the last
 * approve/edit row at the moment a background poller (every 15s, only while
 * server.py is running) claims the job — see feedback_db.enqueue_publish.
 */
export function PublishPanel({ platform, generationId, hasImage, onStatus }) {
  const [accounts, setAccounts] = useState(null);
  const [log, setLog] = useState([]);
  const [scheduleAt, setScheduleAt] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = () => {
    fetch('/api/oauth/accounts').then((r) => r.json())
      .then((d) => setAccounts((d.accounts || []).filter((a) => a.platform === platform)))
      .catch(() => setAccounts([]));
    fetch(`/api/publish/log?generation_id=${generationId}`).then((r) => r.json())
      .then((d) => setLog(d.log || [])).catch(() => {});
  };

  useEffect(() => {
    refresh();
    // Publishing happens on the server's own clock (the poller), not this
    // click, so the status can change with nobody touching the page —
    // pending -> publishing -> success is exactly that. Poll while there is
    // an unfinished job; stop once everything is terminal so an old review
    // doesn't poll forever in a background tab.
    const t = setInterval(() => {
      setLog((prev) => {
        if (prev.some((j) => j.status === 'pending' || j.status === 'publishing')) refresh();
        return prev;
      });
    }, 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generationId]);

  if (platform !== 'linkedin' && platform !== 'instagram') return null;

  const account = accounts?.[0];
  const label = PLATFORM_LABEL[platform];
  const blockedNoImage = platform === 'instagram' && !hasImage;

  const connect = () => {
    // A real browser navigation, not fetch: the platform's own login page has
    // to render, which only works as a top-level page load.
    window.location.href = `/api/oauth/${platform}/authorize`;
  };

  const disconnect = async () => {
    if (!account) return;
    setBusy(true);
    try {
      const res = await fetch(`/api/oauth/${platform}/disconnect`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: account.id }),
      });
      if (res.ok) { onStatus?.('success', `Disconnected ${label}.`); refresh(); }
      else onStatus?.('error', 'Could not disconnect.');
    } finally { setBusy(false); }
  };

  const publish = async (whenTs) => {
    setBusy(true);
    try {
      const res = await fetch('/api/publish', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform, generation_id: generationId, oauth_account_id: account.id,
          scheduled_for: whenTs || undefined,
        }),
      });
      const d = await res.json();
      if (res.ok) {
        onStatus?.('success', whenTs
          ? `Scheduled for ${label} — ${fmtWhen(whenTs)}.`
          : `Queued for ${label}. Publishes within the next 15s.`);
        setScheduleAt('');
        refresh();
      } else {
        onStatus?.('error', d.error || 'Could not queue this post.');
      }
    } finally { setBusy(false); }
  };

  const cancelJob = async (jobId) => {
    setBusy(true);
    try {
      const res = await fetch('/api/publish/cancel', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId }),
      });
      if (res.ok) refresh();
    } finally { setBusy(false); }
  };

  return (
    <div className="publish-panel">
      <div className="pp-head">
        <span className="pp-label">{label}</span>
        {accounts === null ? (
          <span className="pp-hint">Checking connection…</span>
        ) : account ? (
          <>
            <span className="pp-account">{account.label || account.external_id}</span>
            <button type="button" className="pp-linklike" onClick={disconnect} disabled={busy}>
              Disconnect
            </button>
          </>
        ) : (
          <Button variant="secondary" size="small" onClick={connect}>
            Connect {label}
          </Button>
        )}
      </div>

      {blockedNoImage && (
        <p className="pp-blocked">
          Instagram requires an image — none is attached to this post. Add one above before publishing.
        </p>
      )}

      {account && !blockedNoImage && (
        <div className="pp-actions">
          <Button variant="primary" size="small" onClick={() => publish(null)} disabled={busy}>
            Publish now
          </Button>
          <input
            type="datetime-local"
            className="pp-schedule-input"
            value={scheduleAt}
            onChange={(e) => setScheduleAt(e.target.value)}
            min={new Date(Date.now() + 60000).toISOString().slice(0, 16)}
          />
          <Button
            variant="secondary" size="small" disabled={busy || !scheduleAt}
            onClick={() => publish(Math.floor(new Date(scheduleAt).getTime() / 1000))}
          >
            Schedule
          </Button>
        </div>
      )}

      {account && (
        <p className="pp-caveat">
          Scheduled posts only go out while this app's server is running on this machine.
        </p>
      )}

      {log.length > 0 && (
        <ul className="pp-log">
          {log.map((j) => (
            <li key={j.id} className={`pp-log-row pp-log-${j.status}`}>
              <span className={`pp-dot pp-dot-${j.status}`} aria-hidden="true" />
              <span className="pp-log-text">
                {STATUS_TEXT[j.status] || j.status}
                {j.scheduled_for ? ` · for ${fmtWhen(j.scheduled_for)}` : ''}
                {j.status === 'failed' && j.error ? ` — ${j.error}` : ''}
              </span>
              {j.status === 'pending' && (
                <button type="button" className="pp-linklike" onClick={() => cancelJob(j.id)} disabled={busy}>
                  Cancel
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

PublishPanel.propTypes = {
  platform: PropTypes.string.isRequired,
  generationId: PropTypes.number.isRequired,
  hasImage: PropTypes.bool,
  onStatus: PropTypes.func,
};
