import { PlatformBadge } from './PlatformBadge';

export default {
    title: 'Components/PlatformBadge',
    component: PlatformBadge,
    argTypes: {
        platform: {
            control: 'select',
            options: ['linkedin', 'instagram', 'circle', 'kakaotalk'],
        },
        showIcon: {
            control: 'boolean',
        },
    },
};

export const LinkedIn = {
    args: {
        platform: 'linkedin',
    },
};

export const Instagram = {
    args: {
        platform: 'instagram',
    },
};

export const Circle = {
    args: {
        platform: 'circle',
    },
};

export const Kakaotalk = {
    args: {
        platform: 'kakaotalk',
    },
};

export const AllPlatforms = {
    render: () => (
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
            <PlatformBadge platform="linkedin" />
            <PlatformBadge platform="instagram" />
            <PlatformBadge platform="circle" />
            <PlatformBadge platform="kakaotalk" />
        </div>
    ),
};

export const WithoutIcons = {
    render: () => (
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
            <PlatformBadge platform="linkedin" showIcon={false} />
            <PlatformBadge platform="instagram" showIcon={false} />
            <PlatformBadge platform="circle" showIcon={false} />
            <PlatformBadge platform="kakaotalk" showIcon={false} />
        </div>
    ),
};
