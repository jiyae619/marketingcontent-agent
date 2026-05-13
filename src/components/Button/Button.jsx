import PropTypes from 'prop-types';

export function Button({
    variant = 'primary',
    size = 'default',
    disabled = false,
    onClick,
    children,
    type = 'button',
    className = ''
}) {
    const variantClass = variant === 'secondary' ? 'btn-secondary' : 'btn-primary';
    const sizeClass = size === 'small' ? 'btn-small' : size === 'icon' ? 'btn-icon' : '';

    const buttonClassName = ['btn', variantClass, sizeClass, className].filter(Boolean).join(' ');

    return (
        <button
            type={type}
            className={buttonClassName}
            disabled={disabled}
            onClick={onClick}
        >
            {children}
        </button>
    );
}

Button.propTypes = {
    variant: PropTypes.oneOf(['primary', 'secondary']),
    size: PropTypes.oneOf(['default', 'small', 'icon']),
    disabled: PropTypes.bool,
    onClick: PropTypes.func,
    children: PropTypes.node.isRequired,
    type: PropTypes.oneOf(['button', 'submit', 'reset']),
    className: PropTypes.string
};
