import PropTypes from 'prop-types';

function CardHeader({ children }) {
    return <div className="card-header">{children}</div>;
}

function CardBody({ children }) {
    return <div className="card-body">{children}</div>;
}

export function Card({ title, actions, children, className = '' }) {
    return (
        <div className={`card ${className}`.trim()}>
            {(title || actions) && (
                <div className="card-header">
                    {title && <h3 className="card-title mb-0">{title}</h3>}
                    {actions && <div className="platform-actions">{actions}</div>}
                </div>
            )}
            <div className="card-body">{children}</div>
        </div>
    );
}

Card.Header = CardHeader;
Card.Body = CardBody;

Card.propTypes = {
    title: PropTypes.node,
    actions: PropTypes.node,
    children: PropTypes.node.isRequired,
    className: PropTypes.string,
};

CardHeader.propTypes = {
    children: PropTypes.node.isRequired,
};

CardBody.propTypes = {
    children: PropTypes.node.isRequired,
};
