import { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import './JudgeModelSelect.css';

/**
 * Judge-model picker. Reads the single registry (GET /api/judge/models), so cloud
 * models AND the local option appear automatically. The chosen key is passed up to
 * App and threaded into generate/judge requests.
 */
export function JudgeModelSelect({ value, onChange }) {
  const [models, setModels] = useState([]);
  const [defaultKey, setDefaultKey] = useState('');

  useEffect(() => {
    let alive = true;
    fetch('/api/judge/models')
      .then((r) => r.json())
      .then((data) => {
        if (!alive) return;
        setModels(data.models || []);
        setDefaultKey(data.default || '');
        if (!value && data.default) onChange?.(data.default);
      })
      .catch(() => {});
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="judge-select" title="Which model grades the content (judge ≠ generator)">
      <span className="judge-select__label">⚖️ Judge</span>
      <select
        className="judge-select__control"
        value={value || defaultKey}
        onChange={(e) => onChange?.(e.target.value)}
      >
        {models.map((m) => (
          <option key={m.key} value={m.key}>{m.label}</option>
        ))}
      </select>
    </div>
  );
}

JudgeModelSelect.propTypes = {
  value: PropTypes.string,
  onChange: PropTypes.func,
};
