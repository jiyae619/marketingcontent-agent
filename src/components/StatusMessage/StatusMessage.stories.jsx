import { StatusMessage, LoadingSpinner } from './StatusMessage';

export default {
    title: 'Components/StatusMessage',
    component: StatusMessage,
};

export const Success = {
    args: {
        type: 'success',
        message: '✓ All platforms generated successfully!',
    },
};

export const Error = {
    args: {
        type: 'error',
        message: 'Generation failed: API request failed',
    },
};

export const Info = {
    args: {
        type: 'info',
        message: 'Processing your request...',
    },
};

export const Loading = {
    render: () => (
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <LoadingSpinner />
            <span>Generating content...</span>
        </div>
    ),
};
