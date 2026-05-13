import { Card } from './Card';
import { Button } from '../Button/Button';

export default {
    title: 'Components/Card',
    component: Card,
};

export const Basic = {
    render: () => (
        <Card>
            <p>This is a basic card with some content inside.</p>
        </Card>
    ),
};

export const WithTitle = {
    render: () => (
        <Card title="📝 Original Content">
            <p>This card has a title in the header.</p>
        </Card>
    ),
};

export const WithActions = {
    render: () => (
        <Card
            title="Platform Output"
            actions={
                <Button variant="secondary" size="small">
                    📋 Copy
                </Button>
            }
        >
            <p>This card has both a title and action buttons.</p>
        </Card>
    ),
};

export const WithCustomContent = {
    render: () => (
        <Card title="🎨 Custom Card">
            <div className="form-group">
                <label htmlFor="example">Example Input</label>
                <input
                    type="text"
                    id="example"
                    placeholder="Type something..."
                />
            </div>
            <p className="text-muted">Cards can contain any content you need.</p>
        </Card>
    ),
};
