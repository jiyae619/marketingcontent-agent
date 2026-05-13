import { useState } from 'react';
import { Input } from './Input';

export default {
    title: 'Components/Input',
    component: Input,
};

export const TextInput = {
    render: () => {
        const [value, setValue] = useState('');
        return (
            <Input
                label="Your Name"
                type="text"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="Enter your name..."
            />
        );
    },
};

export const Textarea = {
    render: () => {
        const [value, setValue] = useState('');
        return (
            <Input
                label="Paste or write your marketing content"
                type="textarea"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="Enter your marketing message here..."
                rows={6}
            />
        );
    },
};

export const WithCharacterCount = {
    render: () => {
        const [value, setValue] = useState('');
        return (
            <div>
                <Input
                    label="Generated Content"
                    type="textarea"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    placeholder="Content will appear here..."
                    className="platform-output"
                />
                <div className="char-counter">{value.length} characters</div>
            </div>
        );
    },
};
