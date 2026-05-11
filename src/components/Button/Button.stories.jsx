import { Button } from './Button';

export default {
    title: 'Components/Button',
    component: Button,
    argTypes: {
        variant: {
            control: 'select',
            options: ['primary', 'secondary'],
        },
        size: {
            control: 'select',
            options: ['default', 'small', 'icon'],
        },
        disabled: {
            control: 'boolean',
        },
    },
};

export const Primary = {
    args: {
        variant: 'primary',
        children: '🚀 Generate Content!',
    },
};

export const Secondary = {
    args: {
        variant: 'secondary',
        children: 'Clear All',
    },
};

export const Small = {
    args: {
        variant: 'secondary',
        size: 'small',
        children: '📋 Copy',
    },
};

export const Disabled = {
    args: {
        variant: 'primary',
        disabled: true,
        children: 'Disabled Button',
    },
};

export const Icon = {
    args: {
        variant: 'primary',
        size: 'icon',
        children: '✨',
    },
};
