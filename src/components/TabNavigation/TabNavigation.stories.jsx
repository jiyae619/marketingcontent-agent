import { useState } from 'react';
import { TabNavigation } from './TabNavigation';

export default {
    title: 'Components/TabNavigation',
    component: TabNavigation,
};

const tabs = [
    { id: 'linkedin', label: 'LinkedIn' },
    { id: 'instagram', label: 'Instagram' },
    { id: 'circle', label: 'CIRCLE' },
    { id: 'kakaotalk', label: 'Kakaotalk' },
];

export const Default = {
    render: () => {
        const [activeTab, setActiveTab] = useState('linkedin');
        return (
            <div>
                <TabNavigation
                    tabs={tabs}
                    activeTab={activeTab}
                    onTabChange={setActiveTab}
                />
                <div style={{ marginTop: '2rem', padding: '1rem', background: 'var(--color-bg-secondary)', borderRadius: 'var(--border-radius-md)' }}>
                    <p>Active tab: <strong>{activeTab}</strong></p>
                </div>
            </div>
        );
    },
};
