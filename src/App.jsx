import { useState, useEffect } from 'react';
import { Button } from './components/Button/Button';
import { Input } from './components/Input/Input';
import { PlatformSelector } from './components/PlatformSelector/PlatformSelector';
import { TabNavigation } from './components/TabNavigation/TabNavigation';
import { PlatformPreview } from './components/PlatformPreview/PlatformPreview';
import { StatusMessage, LoadingSpinner } from './components/StatusMessage/StatusMessage';
import { ReviewPanel } from './components/ReviewPanel/ReviewPanel';
import { BriefForm } from './components/BriefForm/BriefForm';
import './styles/index.css';

const PLATFORM_TABS = [
  { id: 'linkedin', label: 'LinkedIn' },
  { id: 'instagram', label: 'Instagram' },
  { id: 'circle', label: 'CIRCLE' },
  { id: 'kakaotalk', label: 'KakaoTalk' },
  { id: 'whatsapp', label: 'WhatsApp' },
  { id: 'x', label: 'X' },
];
const LABEL = Object.fromEntries(PLATFORM_TABS.map((t) => [t.id, t.label]));
// Generation order, shortest output first (measured: x ~6s, chat ~9-12s,
// circle ~30-40s). Total time is the same either way; the first finished post
// appears in seconds instead of after the longest one.
const FASTEST_FIRST = ['x', 'whatsapp', 'kakaotalk', 'linkedin', 'instagram', 'circle'];
const PENDING = 'Generating...';

function statusOf(content) {
  if (content === PENDING) return 'pending';
  if (typeof content === 'string' && content.startsWith('Error:')) return 'error';
  if (content) return 'done';
  return 'idle';
}

function App() {
  const [originalContent, setOriginalContent] = useState('');
  // Two input modes. 'fields' is the structured path: code writes the facts and
  // the model writes only prose. 'text' is the original free-text brief, kept
  // because a pasted brief is still the fastest way in — but a parsed brief is a
  // guess and a submitted form is not.
  const [inputMode, setInputMode] = useState('fields');
  const [briefFields, setBriefFields] = useState({ ko: false, topics: [] });
  const [fieldErrors, setFieldErrors] = useState({});
  const [linkUrl, setLinkUrl] = useState('');
  const [imageDataUrl, setImageDataUrl] = useState('');
  const [selectedPlatforms, setSelectedPlatforms] = useState(['linkedin', 'instagram', 'circle', 'kakaotalk', 'whatsapp', 'x']);
  const [generatedContent, setGeneratedContent] = useState({});
  const [generationIds, setGenerationIds] = useState({});
  const [isGenerating, setIsGenerating] = useState(false);
  const [activeTab, setActiveTab] = useState('linkedin');
  const [statusMessage, setStatusMessage] = useState(null);
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

  const setContentFor = (platform, content) =>
    setGeneratedContent((prev) => ({ ...prev, [platform]: content }));

  const buildUserMessage = () => {
    const extras = [];
    if (linkUrl.trim()) extras.push(`Include this link in the post: ${linkUrl.trim()}`);
    if (imageDataUrl) extras.push('Note: an image is attached to this post — reference it naturally if appropriate.');
    return extras.length ? `${originalContent}\n\n---\n${extras.join('\n')}` : originalContent;
  };

  // Lives at component scope, not inside generateContent, so a single channel
  // that timed out can be retried on its own instead of re-running all six.
  const generateOne = async (platform) => {
    try {
      const structured = inputMode === 'fields';
      const response = await fetch(
        structured ? '/api/generate/fields' : '/api/gemini',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(structured ? {
            platform,
            fields: briefFields,
          } : {
            platform,
            link_url: linkUrl.trim(),
            has_image: Boolean(imageDataUrl),
            messages: [{ role: 'user', content: buildUserMessage() }],
          }),
        });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        if (response.status === 422 && errorData.errors) {
          setFieldErrors(errorData.errors);
          throw new Error('Fix the highlighted fields');
        }
        throw new Error(errorData.error || 'API request failed');
      }
      setFieldErrors({});

      const data = await response.json();
      setContentFor(platform, data.content[0].text);
      if (data.generation_id) {
        setGenerationIds((prev) => ({ ...prev, [platform]: data.generation_id }));
      }
      return true;
    } catch (error) {
      setContentFor(platform, `Error: ${error.message}`);
      return false;
    }
  };

  const generateContent = async () => {
    if (inputMode === 'text' && !originalContent.trim()) {
      showStatus('error', 'Please enter some content to transform');
      return;
    }
    if (selectedPlatforms.length === 0) {
      showStatus('error', 'Please select at least one platform');
      return;
    }

    const order = FASTEST_FIRST.filter((p) => selectedPlatforms.includes(p));
    setIsGenerating(true);
    setActiveTab(order[0]);
    setGeneratedContent(Object.fromEntries(selectedPlatforms.map((p) => [p, PENDING])));

    // ONE AT A TIME, not Promise.all. The backend serializes every local-model
    // call behind one global semaphore (providers.py: _LOCAL_CALL_GATE), so
    // firing six in parallel bought nothing but six blocked server threads,
    // and the call queued last could time out waiting its turn (measured:
    // kakaotalk and x both failed in one batch). Sequential requests take the
    // same total time but nothing sits queued behind work it didn't need.
    let failed = 0;
    try {
      for (const platform of order) {
        if (!(await generateOne(platform))) failed += 1;
      }
      if (failed) {
        showStatus('error', `${failed} of ${selectedPlatforms.length} channels failed — retry them from their tabs.`);
      } else {
        showStatus('success', `${selectedPlatforms.length} channels generated.`);
      }
    } finally {
      setIsGenerating(false);
    }
  };

  const retry = async (platform) => {
    setIsGenerating(true);
    setContentFor(platform, PENDING);
    try {
      await generateOne(platform);
    } finally {
      setIsGenerating(false);
    }
  };

  const statuses = Object.fromEntries(
    selectedPlatforms.map((p) => [p, statusOf(generatedContent[p])]),
  );
  const hasOutput = selectedPlatforms.some((p) => statuses[p] !== 'idle');
  const finished = selectedPlatforms.filter((p) => statuses[p] === 'done' || statuses[p] === 'error').length;
  const tabs = PLATFORM_TABS.filter((tab) => selectedPlatforms.includes(tab.id));
  const current = selectedPlatforms.includes(activeTab) ? activeTab : selectedPlatforms[0];

  const channelCount = selectedPlatforms.length;
  const buttonLabel = isGenerating
    ? `Generating ${Math.min(finished + 1, channelCount)} of ${channelCount}`
    : `Generate ${channelCount} channel${channelCount === 1 ? '' : 's'}`;

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <span className="wordmark">Marketing Channel Agent</span>
          <span className="topbar-meta">One brief, written for every channel</span>
        </div>
      </header>

      {backendUnreachable && (
        <div className="notice" role="note">
          Static preview — no backend attached. Generation runs on local models only when
          {' '}<code>python3 server.py</code> is running on your machine.
        </div>
      )}

      <main className="workspace">
        <section className="panel brief-panel" aria-labelledby="brief-title">
          <div className="panel-head">
            <h2 id="brief-title" className="panel-title">Brief</h2>
            <div className="segmented" role="radiogroup" aria-label="Input mode">
              {[['fields', 'Event fields'], ['text', 'Free text']].map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  role="radio"
                  aria-checked={inputMode === mode}
                  className={`segmented-option${inputMode === mode ? ' is-active' : ''}`}
                  onClick={() => setInputMode(mode)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {inputMode === 'fields' && (
            <BriefForm
              values={briefFields}
              onChange={setBriefFields}
              errors={fieldErrors}
              disabled={isGenerating}
            />
          )}

          {inputMode === 'text' && (
            <div className="content-input-stack">
              <Input
                label="Message"
                type="textarea"
                value={originalContent}
                onChange={(e) => setOriginalContent(e.target.value)}
                placeholder="Describe the event or announcement. Each channel gets its own length, tone and format."
                rows={8}
              />

              <div className="attachments">
                <div className="attachment-field">
                  <label htmlFor="link-url" className="attachment-label">Link</label>
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
                  <label className="attachment-label" htmlFor="image-upload">Image</label>
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
                      <span>Choose an image</span>
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
          )}

          <PlatformSelector
            selectedPlatforms={selectedPlatforms}
            onChange={setSelectedPlatforms}
            disabled={isGenerating}
          />

          <div className="brief-footer">
            <Button
              variant="primary"
              onClick={generateContent}
              disabled={isGenerating || channelCount === 0}
              className="btn-block"
            >
              {isGenerating && <LoadingSpinner />}
              {buttonLabel}
            </Button>
            {statusMessage && (
              <StatusMessage type={statusMessage.type} message={statusMessage.message} />
            )}
          </div>
        </section>

        <section className="panel output-panel" aria-label="Generated content">
          {!hasOutput ? (
            <div className="empty-state">
              <h2 className="panel-title">Output</h2>
              <p>
                Each channel appears here as it finishes. They run one at a time on the
                local model — roughly 10–30 seconds each.
              </p>
              <ul className="empty-channels">
                {tabs.map((t) => (
                  <li key={t.id}><span className={`dot dot--${t.id}`} aria-hidden="true" />{t.label}</li>
                ))}
              </ul>
            </div>
          ) : (
            <>
              <TabNavigation
                tabs={tabs}
                activeTab={current}
                onTabChange={setActiveTab}
                statuses={statuses}
              />

              {/* Every panel stays mounted and is only hidden, so an unsent review
                  note or chip selection survives switching tabs mid-review. */}
              {tabs.map(({ id }) => {
                const content = generatedContent[id] || '';
                return (
                  <div className="tab-panel" role="tabpanel" key={id} hidden={id !== current}>
                    {statuses[id] === 'pending' && (
                      <div className="pending-state" aria-live="polite">
                        <p className="pending-label">Writing the {LABEL[id]} post…</p>
                        <div className="skeleton" aria-hidden="true">
                          <span /><span /><span /><span />
                        </div>
                      </div>
                    )}

                    {statuses[id] === 'error' && (
                      <div className="error-state" role="alert">
                        <p className="error-title">{LABEL[id]} didn&apos;t generate</p>
                        <p className="error-detail">{content.replace(/^Error:\s*/, '')}</p>
                        <Button variant="secondary" size="small" onClick={() => retry(id)} disabled={isGenerating}>
                          Try again
                        </Button>
                      </div>
                    )}

                    {statuses[id] === 'done' && (
                      <>
                        <PlatformPreview
                          platform={id}
                          content={content}
                          imageUrl={imageDataUrl}
                          linkUrl={linkUrl}
                          onContentChange={(next) => setContentFor(id, next)}
                        />
                        {generationIds[id] && (
                          <ReviewPanel
                            key={generationIds[id]}
                            platform={id}
                            content={content}
                            generationId={generationIds[id]}
                            onStatus={showStatus}
                          />
                        )}
                      </>
                    )}
                  </div>
                );
              })}
            </>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
