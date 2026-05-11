import PropTypes from 'prop-types';

export function LoadingSpinner() {
    return <span className="loading-spinner" />;
}

export function StatusMessage({ type = 'info', message }) {
    return (
        <div className={`status-message status-${type} fade-in`}>
            {message}
        </div>
    );
}

StatusMessage.propTypes = {
    type: PropTypes.oneOf(['success', 'error', 'info']).isRequired,
    message: PropTypes.string.isRequired,
};
