import PropTypes from 'prop-types';
import { PlatformBadge } from '../PlatformBadge/PlatformBadge';

export function TabNavigation({ tabs, activeTab, onTabChange }) {
    return (
        <div className="tabs-nav">
            {tabs.map(tab => (
                <button
                    key={tab.id}
                    className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
                    onClick={() => onTabChange(tab.id)}
                    data-tab={tab.id}
                >
                    <PlatformBadge platform={tab.id} showIcon={false} />
                </button>
            ))}
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
};
