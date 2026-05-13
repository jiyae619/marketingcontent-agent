import PropTypes from 'prop-types';
import { Button } from '../Button/Button';

function LinkedInPreview({ content }) {
    return (
        <div className="preview-mockup linkedin-preview">
            <div className="linkedin-post">
                <div className="linkedin-header">
                    <div className="linkedin-avatar"></div>
                    <div className="linkedin-user-info">
                        <div className="linkedin-name">PKNIC Team</div>
                        <div className="linkedin-meta">Marketing · 1h</div>
                    </div>
                </div>
                <div className="linkedin-content" dangerouslySetInnerHTML={{
                    __html: content.replace(/#(\w+)/g, '<span style="color: #0077b5;">#$1</span>')
                }} />
                <div className="linkedin-actions">
                    <div className="linkedin-action">👍 Like</div>
                    <div className="linkedin-action">💬 Comment</div>
                    <div className="linkedin-action">🔄 Repost</div>
                    <div className="linkedin-action">📤 Send</div>
                </div>
            </div>
        </div>
    );
}

function InstagramPreview({ content }) {
    return (
        <div className="preview-mockup instagram-preview">
            <div className="instagram-post">
                <div className="instagram-header">
                    <div className="instagram-avatar"></div>
                    <div className="instagram-username">pknic_official</div>
                </div>
                <div className="instagram-image"></div>
                <div className="instagram-actions">
                    <div className="instagram-action">❤️</div>
                    <div className="instagram-action">💬</div>
                    <div className="instagram-action">📤</div>
                </div>
                <div className="instagram-likes">1,234 likes</div>
                <div className="instagram-caption">
                    <span className="instagram-username">pknic_official</span> {content}
                </div>
            </div>
        </div>
    );
}

function CirclePreview({ content }) {
    return (
        <div className="preview-mockup circle-preview">
            <div className="circle-post">
                <div className="circle-header">
                    <div className="circle-avatar"></div>
                    <div className="circle-user-info">
                        <div className="circle-name">PKNIC Community</div>
                        <div className="circle-meta">Posted 2h ago</div>
                    </div>
                </div>
                <div className="circle-content" dangerouslySetInnerHTML={{ __html: content }} />
                <div className="circle-actions">
                    <div className="circle-action">👍 Like</div>
                    <div className="circle-action">💬 Comment</div>
                    <div className="circle-action">🔗 Share</div>
                </div>
            </div>
        </div>
    );
}

function KakaotalkPreview({ content }) {
    return (
        <div className="preview-mockup kakaotalk-preview">
            <div className="kakaotalk-chat">
                <div className="kakaotalk-date">Today</div>
                <div className="kakaotalk-message">
                    <div className="kakaotalk-sender">PKNIC</div>
                    <div className="kakaotalk-bubble">{content}</div>
                    <div className="kakaotalk-time">3:45 PM</div>
                </div>
            </div>
        </div>
    );
}

export function PlatformPreview({ platform, content, onContentChange, onCopy }) {
    const previews = {
        linkedin: LinkedInPreview,
        instagram: InstagramPreview,
        circle: CirclePreview,
        kakaotalk: KakaotalkPreview,
    };

    const PreviewComponent = previews[platform];

    if (!PreviewComponent) {
        return null;
    }

    return (
        <div className="content-columns">
            <div className="content-editor">
                <div className="form-group mb-0">
                    <label>Generated Content</label>
                    <textarea
                        className="platform-output"
                        value={content}
                        onChange={(event) => onContentChange?.(event.target.value)}
                        placeholder={`${platform} version will appear here...`}
                    />
                    <div className="char-counter">{content.length} characters</div>
                </div>
            </div>
            <div className="content-preview">
                <label className="preview-label">Live Preview</label>
                <PreviewComponent content={content || `Your generated ${platform} post will appear here...`} />
                {onCopy && (
                    <Button variant="secondary" size="small" onClick={onCopy} className="preview-copy-button">
                        📋 Copy
                    </Button>
                )}
            </div>
        </div>
    );
}

PlatformPreview.propTypes = {
    platform: PropTypes.oneOf(['linkedin', 'instagram', 'circle', 'kakaotalk']).isRequired,
    content: PropTypes.string,
    onContentChange: PropTypes.func,
    onCopy: PropTypes.func,
};

LinkedInPreview.propTypes = { content: PropTypes.string.isRequired };
InstagramPreview.propTypes = { content: PropTypes.string.isRequired };
CirclePreview.propTypes = { content: PropTypes.string.isRequired };
KakaotalkPreview.propTypes = { content: PropTypes.string.isRequired };
