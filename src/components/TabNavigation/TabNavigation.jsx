import PropTypes from 'prop-types';

const STATUS_TEXT = { pending: 'generating', done: 'ready', error: 'failed', idle: 'not started' };

export function TabNavigation({ tabs, activeTab, onTabChange, statuses = {} }) {
    return (
        <div className="tabs-nav" role="tablist" aria-label="Channels">
            {tabs.map((tab) => {
                const status = statuses[tab.id];
                return (
                    <button
                        key={tab.id}
                        type="button"
                        role="tab"
                        aria-selected={activeTab === tab.id}
                        className={`tab-btn${activeTab === tab.id ? ' active' : ''}`}
                        onClick={() => onTabChange(tab.id)}
                        data-tab={tab.id}
                    >
                        {status && (
                            <span
                                className={`tab-status tab-status--${status}`}
                                aria-label={STATUS_TEXT[status]}
                            />
                        )}
                        {tab.label}
                    </button>
                );
            })}
        </div>
    );
}

TabNavigation.propTypes = {
    tabs: PropTypes.arrayOf(
        PropTypes.shape({
            id: PropTypes.string.isRequired,
            label: PropTypes.string.isRequired,
        })
    ).isRequired,
    activeTab: PropTypes.string.isRequired,
    onTabChange: PropTypes.func.isRequired,
    statuses: PropTypes.objectOf(PropTypes.oneOf(['idle', 'pending', 'done', 'error'])),
};
