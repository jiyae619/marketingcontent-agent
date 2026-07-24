import { useState } from 'react';
import PropTypes from 'prop-types';
import { Button } from '../Button/Button';
import { LoadingSpinner } from '../StatusMessage/StatusMessage';

const MODEL_LABELS = {
  'gemini':            { name: 'Gemini 2.5 Flash',  vendor: 'Google',   tag: 'Cheapest' },
  'openai':            { name: 'GPT-4o mini',       vendor: 'OpenAI',   tag: 'Balanced' },
  'anthropic-haiku':   { name: 'Claude Haiku 4.5',  vendor: 'Anthropic', tag: 'Fast' },
  'anthropic-sonnet':  { name: 'Claude Sonnet 4.6', vendor: 'Anthropic', tag: 'Best quality' },
};

const ORDER = ['gemini', 'openai', 'anthropic-haiku', 'anthropic-sonnet'];

function formatCost(usd) {
  if (usd >= 0.01) return `$${usd.toFixed(3)}`;
  return `$${(usd * 100).toFixed(3)}¢`;
}

export function ModelCompare({
  platform,
  originalContent,
  linkUrl,
  hasImage,
  password,
  onPickWinner,
}) {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const run = async () => {
    if (!originalContent.trim()) {
      setError('Enter content first, then run compare.');
      return;
    }
    if (!password) {
      setError('Password required to compare.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-app-password': password },
        body: JSON.stringify({
          platform,
          link_url: linkUrl,
          has_image: hasImage,
          messages: [{ role: 'user', content: originalContent }],
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.message || body.error || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setResults(data.results || {});
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const winner = results
    ? ORDER.map(k => results[k]).filter(r => r && r.ok)
        .sort((a, b) => (b.eval_score ?? 0) - (a.eval_score ?? 0))[0]
    : null;

  return (
    <div className="compare-panel">
      <div className="compare-header">
        <div>
          <h3 className="compare-title">🆚 Compare across models</h3>
          <p className="compare-sub">
            Same prompt, four models, side-by-side. Cost shown is per run.
          </p>
        </div>
        <Button variant="primary" onClick={run} disabled={loading}>
          {loading ? <><LoadingSpinner /> Running…</> : 'Run compare'}
        </Button>
      </div>

      {error && <p className="compare-error">{error}</p>}

      {results && (
        <div className="compare-grid">
          {ORDER.map((key) => {
            const r = results[key];
            const meta = MODEL_LABELS[key];
            if (!r) return null;
            const isWinner = winner && winner.model === r.model;
            return (
              <div key={key} className={`compare-card ${isWinner ? 'compare-card--winner' : ''} ${!r.ok ? 'compare-card--error' : ''}`}>
                <div className="compare-card-head">
                  <div>
                    <div className="compare-card-name">{meta.name}</div>
                    <div className="compare-card-vendor">{meta.vendor} · {meta.tag}</div>
                  </div>
                  {isWinner && <span className="compare-winner-pill">🏆 Top eval</span>}
                </div>

                {r.ok ? (
                  <>
                    <div className="compare-metrics">
                      <span title="Estimated cost for this run">{formatCost(r.cost_usd)}</span>
                      <span title="Round-trip latency">{r.latency_ms}ms</span>
                      <span title="Output tokens">{r.output_tokens}tok</span>
                      {typeof r.eval_score === 'number' && (
                        <span title="Heuristic eval score (0–100)">⭐ {r.eval_score.toFixed(0)}</span>
                      )}
                    </div>
                    <textarea
                      className="compare-text"
                      readOnly
                      value={r.text}
                    />
                    <div className="compare-card-actions">
                      <Button
                        variant="secondary"
                        size="small"
                        onClick={() => onPickWinner?.(r.text, r.generation_id, key)}
                      >
                        ✅ Use this version
                      </Button>
                    </div>
                  </>
                ) : (
                  <p className="compare-card-err">⚠ {r.error}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

ModelCompare.propTypes = {
  platform: PropTypes.string.isRequired,
  originalContent: PropTypes.string.isRequired,
  linkUrl: PropTypes.string,
  hasImage: PropTypes.bool,
  password: PropTypes.string,
  onPickWinner: PropTypes.func,
};
