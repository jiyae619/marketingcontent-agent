import PropTypes from 'prop-types';

export function Input({
    label,
    type = 'text',
    value,
    onChange,
    placeholder,
    id,
    className = '',
    rows = 3
}) {
    const inputId = id || `input-${label?.toLowerCase().replace(/\s+/g, '-')}`;

    return (
        <div className="form-group">
            {label && <label htmlFor={inputId}>{label}</label>}
            {type === 'textarea' ? (
                <textarea
                    id={inputId}
                    className={`content-input ${className}`.trim()}
                    value={value}
                    onChange={onChange}
                    placeholder={placeholder}
                    rows={rows}
                />
            ) : (
                <input
                    type={type}
                    id={inputId}
                    className={className}
                    value={value}
                    onChange={onChange}
                    placeholder={placeholder}
                />
            )}
        </div>
    );
}

Input.propTypes = {
    label: PropTypes.string,
    type: PropTypes.oneOf(['text', 'password', 'textarea']),
    value: PropTypes.string,
    onChange: PropTypes.func,
    placeholder: PropTypes.string,
    id: PropTypes.string,
    className: PropTypes.string,
    rows: PropTypes.number,
};
