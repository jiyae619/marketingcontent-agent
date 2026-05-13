import PropTypes from 'prop-types';
import { useState } from 'react';

const platforms = [
    { id: 'linkedin', label: 'LinkedIn' },
    { id: 'instagram', label: 'Instagram' },
    { id: 'circle', label: 'CIRCLE' },
    { id: 'kakaotalk', label: 'Kakaotalk' },
    { id: 'whatsapp', label: 'WhatsApp' },
    { id: 'x', label: 'X' },
];

export function PlatformSelector({ selectedPlatforms = [], onChange }) {
    const handleChange = (platformId) => {
        const newSelected = selectedPlatforms.includes(platformId)
            ? selectedPlatforms.filter(id => id !== platformId)
            : [...selectedPlatforms, platformId];
        onChange?.(newSelected);
    };

    return (
        <div className="platform-selector">
            <label className="selector-label">Select Platforms:</label>
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
                        <span className="checkbox-label">
                            <span className="platform-name">{platform.label}</span>
                        </span>
                    </label>
                ))}
            </div>
        </div>
    );
}

PlatformSelector.propTypes = {
    selectedPlatforms: PropTypes.arrayOf(PropTypes.string),
    onChange: PropTypes.func,
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
