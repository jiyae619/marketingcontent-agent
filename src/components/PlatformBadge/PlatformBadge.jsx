import PropTypes from 'prop-types';

const platformConfig = {
    linkedin: {
        icon: '💼',
        label: 'LinkedIn',
        className: 'platform-linkedin',
    },
    instagram: {
        icon: '📷',
        label: 'Instagram',
        className: 'platform-instagram',
    },
    circle: {
        icon: '⭕',
        label: 'CIRCLE',
        className: 'platform-circle',
    },
    kakaotalk: {
        icon: '💬',
        label: 'Kakaotalk',
        className: 'platform-kakaotalk',
    },
    whatsapp: {
        icon: '💚',
        label: 'WhatsApp',
        className: 'platform-whatsapp',
    },
    x: {
        icon: '𝕏',
        label: 'X',
        className: 'platform-x',
    },
};

export function PlatformBadge({ platform, showIcon = true }) {
    const config = platformConfig[platform];

    if (!config) {
        return null;
    }

    return (
        <span className={`platform-badge ${config.className}`}>
            {showIcon && <span className="platform-icon">{config.icon}</span>}
            {config.label}
        </span>
    );
}

PlatformBadge.propTypes = {
    platform: PropTypes.oneOf(['linkedin', 'instagram', 'circle', 'kakaotalk', 'whatsapp', 'x']).isRequired,
    showIcon: PropTypes.bool,
};
