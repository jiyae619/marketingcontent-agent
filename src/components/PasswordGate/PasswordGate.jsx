import { useState } from 'react';
import PropTypes from 'prop-types';
import { Button } from '../Button/Button';

export function PasswordGate({ onUnlock, onPreview, error }) {
  const [password, setPassword] = useState('');

  const submit = (e) => {
    e.preventDefault();
    if (password.trim()) onUnlock(password.trim());
  };

  return (
    <div className="gate-backdrop" role="dialog" aria-modal="true" aria-labelledby="gate-title">
      <div className="gate-card">
        <h2 id="gate-title" className="gate-title">🔐 Private preview</h2>
        <p className="gate-body">
          This tool generates content with Gemini, which costs tokens per request.
          Enter the password to generate content, or click <em>I want to preview!</em>
          to explore the interface without generating anything.
        </p>

        <form onSubmit={submit} className="gate-form">
          <input
            type="password"
            className="gate-input"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            aria-label="Password"
          />
          {error && <p className="gate-error">{error}</p>}
          <div className="gate-actions">
            <Button type="submit" variant="primary" disabled={!password.trim()}>
              Unlock generation
            </Button>
            <Button type="button" variant="secondary" onClick={onPreview}>
              I want to preview!
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

PasswordGate.propTypes = {
  onUnlock: PropTypes.func.isRequired,
  onPreview: PropTypes.func.isRequired,
  error: PropTypes.string,
};
