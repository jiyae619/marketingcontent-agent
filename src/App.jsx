import { useState } from 'react';
import { Card } from './components/Card/Card';
import { Button } from './components/Button/Button';
import { Input } from './components/Input/Input';
import { PlatformSelector } from './components/PlatformSelector/PlatformSelector';
import { TabNavigation } from './components/TabNavigation/TabNavigation';
import { PlatformPreview } from './components/PlatformPreview/PlatformPreview';
import { StatusMessage, LoadingSpinner } from './components/StatusMessage/StatusMessage';
import './styles/index.css';

const PLATFORM_TABS = [
  { id: 'linkedin', label: 'LinkedIn' },
  { id: 'instagram', label: 'Instagram' },
  { id: 'circle', label: 'CIRCLE' },
  { id: 'kakaotalk', label: 'Kakaotalk' },
];

function App() {
  const [originalContent, setOriginalContent] = useState('');
  const [selectedPlatforms, setSelectedPlatforms] = useState(['linkedin', 'instagram', 'circle', 'kakaotalk']);
  const [generatedContent, setGeneratedContent] = useState({});
  const [isGenerating, setIsGenerating] = useState(false);
  const [activeTab, setActiveTab] = useState('linkedin');
  const [statusMessage, setStatusMessage] = useState(null);
  const [showTabs, setShowTabs] = useState(false);

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
      // Generate for all selected platforms in parallel
      const promises = selectedPlatforms.map(async (platform) => {
        try {
          const response = await fetch('/api/gemini', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              model: 'claude-3-5-sonnet-20241022',
              max_tokens: 2048,
              system: await loadPlatformPrompt(platform),
              messages: [
                {
                  role: 'user',
                  content: originalContent,
                },
              ],
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

  const loadPlatformPrompt = async (platform) => {
    try {
      const response = await fetch(`/api/prompts/${platform}`);
      const data = await response.json();
      return data.prompt;
    } catch (error) {
      console.error(`Failed to load ${platform} prompt:`, error);
      return `Transform this content for ${platform}`;
    }
  };

  const clearAll = () => {
    setOriginalContent('');
    setGeneratedContent({});
    setShowTabs(false);
  };

  const copyToClipboard = async (platform) => {
    const content = generatedContent[platform];
    if (!content || content === 'Generating...') {
      showStatus('error', 'No content to copy');
      return;
    }

    try {
      await navigator.clipboard.writeText(content);
      showStatus('success', `✓ ${platform} content copied to clipboard!`);
    } catch {
      showStatus('error', 'Failed to copy to clipboard');
    }
  };

  return (
    <div>
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
            <Input
              label="Paste or write your marketing content"
              type="textarea"
              value={originalContent}
              onChange={(e) => setOriginalContent(e.target.value)}
              placeholder="Enter your marketing message here. This will be adapted for each platform with the appropriate tone, length, and formatting..."
              rows={8}
            />

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
            <Button variant="secondary" size="small" onClick={clearAll}>
              Clear All
            </Button>
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
                    onContentChange={(content) => {
                      setGeneratedContent(prevContent => ({
                        ...prevContent,
                        [platform]: content,
                      }));
                    }}
                    onCopy={() => copyToClipboard(platform)}
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
