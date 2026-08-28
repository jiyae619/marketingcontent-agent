import { useState, useEffect } from 'react';
import { Card } from './components/Card/Card';
import { Button } from './components/Button/Button';
import { Input } from './components/Input/Input';
import { PlatformSelector } from './components/PlatformSelector/PlatformSelector';
import { TabNavigation } from './components/TabNavigation/TabNavigation';
import { PlatformPreview } from './components/PlatformPreview/PlatformPreview';
import { StatusMessage, LoadingSpinner } from './components/StatusMessage/StatusMessage';
import { ModelCompare } from './components/ModelCompare/ModelCompare';
import { JudgeModelSelect } from './components/JudgeModelSelect/JudgeModelSelect';
import { ReviewPanel } from './components/ReviewPanel/ReviewPanel';
import { GeneratingOverlay } from './components/GeneratingOverlay/GeneratingOverlay';
import './styles/index.css';

const PLATFORM_TABS = [
  { id: 'linkedin', label: 'LinkedIn' },
  { id: 'instagram', label: 'Instagram' },
  { id: 'circle', label: 'CIRCLE' },
  { id: 'kakaotalk', label: 'Kakaotalk' },
  { id: 'whatsapp', label: 'WhatsApp' },
  { id: 'x', label: 'X' },
];

function App() {
  const [originalContent, setOriginalContent] = useState('');
  const [linkUrl, setLinkUrl] = useState('');
  const [imageDataUrl, setImageDataUrl] = useState('');
  const [selectedPlatforms, setSelectedPlatforms] = useState(['linkedin', 'instagram', 'circle', 'kakaotalk', 'whatsapp', 'x']);
  const [generatedContent, setGeneratedContent] = useState({});
  const [generationIds, setGenerationIds] = useState({});
  const [judgeModel, setJudgeModel] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [activeTab, setActiveTab] = useState('linkedin');
  const [statusMessage, setStatusMessage] = useState(null);
  const [showTabs, setShowTabs] = useState(false);
  const [backendUnreachable, setBackendUnreachable] = useState(false);

  // This app has no hosted backend — server.py binds to localhost only and
  // drives local Ollama models, by design (see CLAUDE.md: LOCAL_ONLY). A
  // deployed copy of this page (e.g. the Netlify preview) has nothing at
  // /api to talk to, so every generate click would otherwise fail silently.
  useEffect(() => {
    fetch('/api/generator/models')
      .then((res) => setBackendUnreachable(!res.ok))
      .catch(() => setBackendUnreachable(true));
  }, []);

  const handleImageUpload = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      showStatus('error', 'Please select an image file');
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => setImageDataUrl(e.target?.result || '');
    reader.readAsDataURL(file);
  };

  const removeImage = () => setImageDataUrl('');

  const showStatus = (type, message) => {
    setStatusMessage({ type, message });
    setTimeout(() => setStatusMessage(null), 5000);
  };

  const generateContent = async () => {
    if (!originalContent.trim()) {
      showStatus('error', 'Please enter some content to transform');
      return;
    }

    if (selectedPlatforms.length === 0) {
      showStatus('error', 'Please select at least one platform');
      return;
    }

    setIsGenerating(true);
    setShowTabs(true);

    // Initialize generating state for selected platforms
    const generatingState = {};
    selectedPlatforms.forEach(platform => {
      generatingState[platform] = 'Generating...';
    });
    setGeneratedContent(generatingState);

    try {
      // Compose user message with optional link + image hint
      const extras = [];
      if (linkUrl.trim()) extras.push(`Include this link in the post: ${linkUrl.trim()}`);
      if (imageDataUrl) extras.push('Note: an image is attached to this post — reference it naturally if appropriate.');
      const userMessage = extras.length
        ? `${originalContent}\n\n---\n${extras.join('\n')}`
        : originalContent;

      // Generate for all selected platforms in parallel.
      // System prompt is assembled server-side — we only send the raw user content.
      const promises = selectedPlatforms.map(async (platform) => {
        try {
          const response = await fetch('/api/gemini', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              platform,
              link_url: linkUrl.trim(),
              has_image: Boolean(imageDataUrl),
              judge_model: judgeModel || undefined,
              messages: [{ role: 'user', content: userMessage }],
            }),
          });

          if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || 'API request failed');
          }

          const data = await response.json();
          const content = data.content[0].text;
          setGeneratedContent(prevContent => ({
            ...prevContent,
            [platform]: content,
          }));
          if (data.generation_id) {
            setGenerationIds(prev => ({ ...prev, [platform]: data.generation_id }));
          }
          return { platform, content };
        } catch (error) {
          const content = `Error: ${error.message}`;
          setGeneratedContent(prevContent => ({
            ...prevContent,
            [platform]: content,
          }));
          return { platform, content };
        }
      });

      await Promise.all(promises);
      showStatus('success', '✓ All platforms generated successfully!');
    } catch (error) {
      showStatus('error', `Generation failed: ${error.message}`);
    } finally {
      setIsGenerating(false);
    }
  };


  return (
    <div>
      {backendUnreachable && (
        <StatusMessage
          type="info"
          message="This is a static demo of the UI with no backend attached — it drives local AI models and only generates content when you run `python3 server.py` on your own machine."
        />
      )}

      <GeneratingOverlay
        visible={isGenerating}
        platforms={selectedPlatforms}
        contentByPlatform={generatedContent}
      />

      {/* Header */}
      <header>
        <div className="header-background">
          <div className="bg-blur-1"></div>
          <div className="bg-blur-2"></div>
          <div className="bg-blur-3"></div>
        </div>
        <h1 className="app-title">✨ Marketing Channel Agent</h1>
        <p className="app-subtitle">Transform your content for every platform</p>
      </header>

      <div className="container">
        {/* Input Section */}
        <Card title="📝 Original Content">
          <div className="input-grid">
            <div className="content-input-stack">
              <Input
                label="Write your content"
                type="textarea"
                value={originalContent}
                onChange={(e) => setOriginalContent(e.target.value)}
                placeholder="Enter your marketing message here. This will be adapted for each platform with the appropriate tone, length, and formatting..."
                rows={8}
              />

              <div className="attachments">
                <div className="attachment-field">
                  <label htmlFor="link-url" className="attachment-label">🔗 Link</label>
                  <input
                    id="link-url"
                    type="url"
                    className="attachment-input"
                    value={linkUrl}
                    onChange={(e) => setLinkUrl(e.target.value)}
                    placeholder="https://example.com/your-event"
                  />
                </div>

                <div className="attachment-field">
                  <label className="attachment-label" htmlFor="image-upload">🖼️ Image</label>
                  {imageDataUrl ? (
                    <div className="attachment-image-preview">
                      <img src={imageDataUrl} alt="Upload preview" />
                      <button
                        type="button"
                        className="attachment-image-remove"
                        onClick={removeImage}
                        aria-label="Remove image"
                      >
                        ×
                      </button>
                    </div>
                  ) : (
                    <label htmlFor="image-upload" className="attachment-image-dropzone">
                      <span>Click to upload</span>
                      <input
                        id="image-upload"
                        type="file"
                        accept="image/*"
                        onChange={handleImageUpload}
                        hidden
                      />
                    </label>
                  )}
                </div>
              </div>
            </div>

            <PlatformSelector
              selectedPlatforms={selectedPlatforms}
              onChange={setSelectedPlatforms}
            />
          </div>

          <div className="action-bar input-actions">
            <Button
              variant="primary"
              onClick={generateContent}
              disabled={isGenerating || selectedPlatforms.length === 0}
            >
              {isGenerating ? (
                <>
                  <LoadingSpinner /> Generating...
                </>
              ) : (
                '🚀 Generate Content!'
              )}
            </Button>
            <JudgeModelSelect value={judgeModel} onChange={setJudgeModel} />
          </div>
        </Card>

        {/* Status Messages */}
        {statusMessage && (
          <StatusMessage type={statusMessage.type} message={statusMessage.message} />
        )}

        {/* Platform Tabs */}
        {showTabs && (
          <div className="tabs-container">
            <TabNavigation
              tabs={PLATFORM_TABS.filter(tab => selectedPlatforms.includes(tab.id))}
              activeTab={activeTab}
              onTabChange={setActiveTab}
            />

            {selectedPlatforms.map(platform => (
              <div
                key={platform}
                className={`tab-content ${activeTab === platform ? 'active' : ''}`}
              >
                <Card className="fade-in platform-card">
                  <PlatformPreview
                    platform={platform}
                    content={generatedContent[platform] || ''}
                    imageUrl={imageDataUrl}
                    linkUrl={linkUrl}
                    onContentChange={(content) => {
                      setGeneratedContent(prevContent => ({
                        ...prevContent,
                        [platform]: content,
                      }));
                    }}
                  />
                  {generationIds[platform] && (
                    <ReviewPanel
                      platform={platform}
                      content={generatedContent[platform] || ''}
                      generationId={generationIds[platform]}
                      judgeModel={judgeModel}
                      onStatus={showStatus}
                    />
                  )}
                  <ModelCompare
                    platform={platform}
                    originalContent={originalContent}
                    linkUrl={linkUrl}
                    hasImage={Boolean(imageDataUrl)}
                    onPickWinner={(text, gen_id, providerKey) => {
                      setGeneratedContent(prev => ({ ...prev, [platform]: text }));
                      if (gen_id) setGenerationIds(prev => ({ ...prev, [platform]: gen_id }));
                      showStatus('success', `Using ${providerKey} version for ${platform}`);
                    }}
                  />
                </Card>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
