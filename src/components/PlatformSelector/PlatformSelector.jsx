import PropTypes from 'prop-types';
import { useState } from 'react';

const platforms = [
    { id: 'linkedin', label: 'LinkedIn' },
    { id: 'instagram', label: 'Instagram' },
    { id: 'circle', label: 'CIRCLE' },
    { id: 'kakaotalk', label: 'KakaoTalk' },
    { id: 'whatsapp', label: 'WhatsApp' },
    { id: 'x', label: 'X' },
];

export function PlatformSelector({ selectedPlatforms = [], onChange, disabled = false }) {
    const handleChange = (platformId) => {
        const newSelected = selectedPlatforms.includes(platformId)
            ? selectedPlatforms.filter(id => id !== platformId)
            : [...selectedPlatforms, platformId];
        onChange?.(newSelected);
    };

    const allOn = selectedPlatforms.length === platforms.length;

    return (
        <fieldset className="platform-selector" disabled={disabled}>
            <div className="selector-head">
                <legend className="selector-label">Channels</legend>
                <button
                    type="button"
                    className="link-btn"
                    onClick={() => onChange?.(allOn ? [] : platforms.map((p) => p.id))}
                >
                    {allOn ? 'Clear' : 'Select all'}
                </button>
            </div>
            <div className="platform-checkboxes">
                {platforms.map(platform => (
                    <label
                        key={platform.id}
                        className={`platform-checkbox platform-checkbox-${platform.id}`}
                    >
                        <input
                            type="checkbox"
                            checked={selectedPlatforms.includes(platform.id)}
                            onChange={() => handleChange(platform.id)}
                        />
                        <span className={`dot dot--${platform.id}`} aria-hidden="true" />
                        <span className="platform-name">{platform.label}</span>
                    </label>
                ))}
            </div>
        </fieldset>
    );
}

PlatformSelector.propTypes = {
    selectedPlatforms: PropTypes.arrayOf(PropTypes.string),
    onChange: PropTypes.func,
    disabled: PropTypes.bool,
};

// Wrapper component for stories
export function PlatformSelectorDemo() {
    const [selected, setSelected] = useState(['linkedin', 'instagram', 'circle', 'kakaotalk', 'whatsapp', 'x']);

    return (
        <div>
            <PlatformSelector selectedPlatforms={selected} onChange={setSelected} />
            <p style={{ marginTop: '1rem', color: 'var(--color-text-tertiary)' }}>
                Selected: {selected.length > 0 ? selected.join(', ') : 'none'}
            </p>
        </div>
    );
}
