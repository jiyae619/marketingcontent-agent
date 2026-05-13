import PropTypes from 'prop-types';
import { Button } from '../Button/Button';

function LinkedInPreview({ content, imageUrl }) {
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
                {imageUrl && (
                    <div className="linkedin-image">
                        <img src={imageUrl} alt="" />
                    </div>
                )}
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

function InstagramPreview({ content, imageUrl }) {
    return (
        <div className="preview-mockup instagram-preview">
            <div className="instagram-post">
                <div className="instagram-header">
                    <div className="instagram-avatar"></div>
                    <div className="instagram-username">pknic_official</div>
                </div>
                <div className={`instagram-image ${imageUrl ? 'instagram-image-filled' : ''}`}>
                    {imageUrl && <img src={imageUrl} alt="" />}
                </div>
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

function WhatsappPreview({ content }) {
    return (
        <div className="preview-mockup whatsapp-preview">
            <div className="whatsapp-chat">
                <div className="whatsapp-date-wrap">
                    <span className="whatsapp-date">TODAY</span>
                </div>
                <div className="whatsapp-row whatsapp-row-out">
                    <div className="whatsapp-bubble whatsapp-bubble-out">
                        <div className="whatsapp-text">{content}</div>
                        <div className="whatsapp-meta">
                            <span className="whatsapp-time">3:45 PM</span>
                            <span className="whatsapp-check" aria-label="read">✓✓</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function XPreview({ content }) {
    return (
        <div className="preview-mockup x-preview">
            <div className="x-post">
                <div className="x-avatar" aria-hidden="true">
                    <span className="x-avatar-glyph">𝕏</span>
                </div>
                <div className="x-body">
                    <div className="x-header">
                        <span className="x-name">PKNIC</span>
                        <span className="x-verified" aria-label="Verified">✓</span>
                        <span className="x-handle">@pknic</span>
                        <span className="x-dot" aria-hidden="true">·</span>
                        <span className="x-meta">1h</span>
                    </div>
                    <div className="x-content">{content}</div>
                    <div className="x-actions">
                        <span className="x-action x-action-reply"><span className="x-icon">💬</span><span className="x-count">24</span></span>
                        <span className="x-action x-action-repost"><span className="x-icon">🔁</span><span className="x-count">12</span></span>
                        <span className="x-action x-action-like"><span className="x-icon">♡</span><span className="x-count">138</span></span>
                        <span className="x-action x-action-views"><span className="x-icon">📊</span><span className="x-count">5.4K</span></span>
                        <span className="x-action x-action-share"><span className="x-icon">↗</span></span>
                    </div>
                </div>
            </div>
        </div>
    );
}

export function PlatformPreview({ platform, content, imageUrl, linkUrl, onContentChange, onCopy }) {
    const previews = {
        linkedin: LinkedInPreview,
        instagram: InstagramPreview,
        circle: CirclePreview,
        kakaotalk: KakaotalkPreview,
        whatsapp: WhatsappPreview,
        x: XPreview,
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
                <PreviewComponent
                    content={content || `Your generated ${platform} post will appear here...`}
                    imageUrl={imageUrl}
                    linkUrl={linkUrl}
                />
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
    platform: PropTypes.oneOf(['linkedin', 'instagram', 'circle', 'kakaotalk', 'whatsapp', 'x']).isRequired,
    content: PropTypes.string,
    imageUrl: PropTypes.string,
    linkUrl: PropTypes.string,
    onContentChange: PropTypes.func,
    onCopy: PropTypes.func,
};

LinkedInPreview.propTypes = { content: PropTypes.string.isRequired, imageUrl: PropTypes.string };
InstagramPreview.propTypes = { content: PropTypes.string.isRequired, imageUrl: PropTypes.string };
CirclePreview.propTypes = { content: PropTypes.string.isRequired };
KakaotalkPreview.propTypes = { content: PropTypes.string.isRequired };
WhatsappPreview.propTypes = { content: PropTypes.string.isRequired };
XPreview.propTypes = { content: PropTypes.string.isRequired };
