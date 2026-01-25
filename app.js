// ===================================
// State Management
// ===================================

const APP_STATE = {
  apiKey: null,
  isGenerating: false,
  originalContent: ''
};

// ===================================
// Platform-Specific Prompts
// ===================================

const PLATFORM_PROMPTS = {
  linkedin: {
    name: 'LinkedIn',
    systemPrompt: `You are a professional LinkedIn content strategist. Transform the user's content into an engaging LinkedIn post.

REQUIREMENTS:
- Professional, authoritative tone
- Length: 1300-1500 characters (aim for engagement sweet spot)
- Structure: Hook (first line) → Key points → Call-to-action
- Use 3-5 relevant professional hashtags at the end
- Strategic line breaks for readability
- Focus on value delivery and thought leadership

Return ONLY the transformed LinkedIn post, nothing else.`
  },

  instagram: {
    name: 'Instagram',
    systemPrompt: `You are an Instagram content creator. Transform the user's content into an engaging Instagram caption.

REQUIREMENTS:
- Casual, engaging, friendly tone
- Length: 125-150 words (optimal for engagement)
- Include 3-5 strategically placed emojis that enhance the message
- Strong hook in the first line to grab attention
- Use 5-8 relevant hashtags at the end
- Natural, conversational style

Return ONLY the transformed Instagram caption, nothing else.`
  },

  circle: {
    name: 'CIRCLE',
    systemPrompt: `You are a community platform content specialist. Transform the user's content for the CIRCLE platform.

REQUIREMENTS:
- Informative, community-focused tone
- Length: Comprehensive (500-800 words) - don't rush, provide depth
- Use bullet points for scannability and easy reading
- Include section headers if content is complex
- Discussion prompts or questions to encourage engagement
- Structured with clear sections

Return ONLY the transformed CIRCLE post, nothing else.`
  },

  kakaotalk: {
    name: 'Kakaotalk',
    systemPrompt: `You are a messaging platform content specialist. Transform the user's content into a Kakaotalk message.

REQUIREMENTS:
- Conversational, friendly, direct tone
- MAXIMUM 3 sentences - this is critical
- Chat-like style, concise and actionable
- Clear, simple message format
- Focus on single key takeaway
- No hashtags, no emojis (unless extremely natural)

Return ONLY the transformed Kakaotalk message, nothing else.`
  }
};

// ===================================
// DOM Elements
// ===================================

const elements = {
  // Main content
  mainContent: document.getElementById('mainContent'),

  // Input
  originalContent: document.getElementById('originalContent'),
  generateBtn: document.getElementById('generateBtn'),
  generateBtnText: document.getElementById('generateBtnText'),
  generateBtnLoading: document.getElementById('generateBtnLoading'),
  clearBtn: document.getElementById('clearBtn'),

  // Platform outputs
  linkedinCard: document.getElementById('linkedinCard'),
  instagramCard: document.getElementById('instagramCard'),
  circleCard: document.getElementById('circleCard'),
  kakaotalkCard: document.getElementById('kakaotalkCard'),

  linkedinOutput: document.getElementById('linkedinOutput'),
  instagramOutput: document.getElementById('instagramOutput'),
  circleOutput: document.getElementById('circleOutput'),
  kakaotalkOutput: document.getElementById('kakaotalkOutput'),

  linkedinCounter: document.getElementById('linkedinCounter'),
  instagramCounter: document.getElementById('instagramCounter'),
  circleCounter: document.getElementById('circleCounter'),
  kakaotalkCounter: document.getElementById('kakaotalkCounter'),

  // Status
  statusContainer: document.getElementById('statusContainer')
};

// ===================================
// Initialization
// ===================================

function init() {
  loadApiKey();
  attachEventListeners();
  updateCharCounters();
}

function loadApiKey() {
  const savedKey = localStorage.getItem('gemini_api_key');
  if (savedKey) {
    APP_STATE.apiKey = savedKey;
    elements.apiKeyInput.value = savedKey;
  }
  // Try to check if backend has API key configured
  checkBackendApiKey();
}

async function checkBackendApiKey() {
  // Backend API key check removed - configuration UI no longer exists
  // API key is now always configured in backend via .env file
}

function markConfigured() {
  // Configuration UI removed - main content always visible
  // API key is now configured in backend via .env file
}

// ===================================
// Event Listeners
// ===================================

function attachEventListeners() {
  // Content Generation
  elements.generateBtn.addEventListener('click', generateAllPlatforms);
  elements.clearBtn.addEventListener('click', clearAll);

  // Copy Buttons
  document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const platform = e.currentTarget.getAttribute('data-platform');
      copyToClipboard(platform);
    });
  });

  // Character Counters
  elements.linkedinOutput.addEventListener('input', () => updateCharCounter('linkedin'));
  elements.instagramOutput.addEventListener('input', () => updateCharCounter('instagram'));
  elements.circleOutput.addEventListener('input', () => updateCharCounter('circle'));
  elements.kakaotalkOutput.addEventListener('input', () => updateCharCounter('kakaotalk'));
}

// ===================================
// API Key Management
// ===================================
// API key management removed - now handled in backend via .env file

// ===================================
// Content Generation
// ===================================

async function generateAllPlatforms() {
  const content = elements.originalContent.value.trim();

  if (!content) {
    showStatus('error', 'Please enter some content to transform');
    return;
  }

  if (!APP_STATE.apiKey) {
    showStatus('error', 'Please configure your API key first');
    return;
  }

  APP_STATE.isGenerating = true;
  setGeneratingState(true);

  // Show all platform cards
  elements.linkedinCard.style.display = 'block';
  elements.instagramCard.style.display = 'block';
  elements.circleCard.style.display = 'block';
  elements.kakaotalkCard.style.display = 'block';

  // Clear previous outputs
  elements.linkedinOutput.value = 'Generating...';
  elements.instagramOutput.value = 'Generating...';
  elements.circleOutput.value = 'Generating...';
  elements.kakaotalkOutput.value = 'Generating...';

  // Convert to markdown (simple conversion)
  const markdownContent = convertToMarkdown(content);

  // Generate for all platforms in parallel
  const platforms = ['linkedin', 'instagram', 'circle', 'kakaotalk'];
  const promises = platforms.map(platform =>
    generateForPlatform(platform, markdownContent)
  );

  try {
    await Promise.all(promises);
    showStatus('success', '✓ All platforms generated successfully!');
  } catch (error) {
    showStatus('error', `Generation failed: ${error.message}`);
  } finally {
    APP_STATE.isGenerating = false;
    setGeneratingState(false);
    updateCharCounters();
  }
}

async function generateForPlatform(platform, content) {
  const prompt = PLATFORM_PROMPTS[platform];
  const outputElement = elements[`${platform}Output`];

  try {
    const result = await callAnthropicAPI(prompt.systemPrompt, content);
    outputElement.value = result;
  } catch (error) {
    outputElement.value = `Error: ${error.message}`;
    throw error;
  }
}

// ===================================
// Anthropic API Integration
// ===================================

async function callAnthropicAPI(systemPrompt, userContent) {
  // Use local proxy server to avoid CORS issues (now using Gemini)
  const requestBody = {
    model: 'claude-3-5-sonnet-20241022',
    max_tokens: 2048,
    system: systemPrompt,
    messages: [
      {
        role: 'user',
        content: userContent
      }
    ]
  };

  // Only include API key if we have one (backend might have it configured)
  if (APP_STATE.apiKey) {
    requestBody.api_key = APP_STATE.apiKey;
  }

  const response = await fetch('http://localhost:8080/api/gemini', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(requestBody)
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error?.message || 'API request failed');
  }

  const data = await response.json();
  return data.content[0].text;
}

// ===================================
// Utility Functions
// ===================================

function convertToMarkdown(text) {
  // Simple conversion - mainly for preserving structure
  // Split into paragraphs and clean up
  const paragraphs = text.split('\n\n').filter(p => p.trim());
  return paragraphs.map(p => p.trim()).join('\n\n');
}

function setGeneratingState(isGenerating) {
  elements.generateBtn.disabled = isGenerating;
  elements.generateBtnText.classList.toggle('hidden', isGenerating);
  elements.generateBtnLoading.classList.toggle('hidden', !isGenerating);
}

function clearAll() {
  elements.originalContent.value = '';
  elements.linkedinOutput.value = '';
  elements.instagramOutput.value = '';
  elements.circleOutput.value = '';
  elements.kakaotalkOutput.value = '';

  elements.linkedinCard.style.display = 'none';
  elements.instagramCard.style.display = 'none';
  elements.circleCard.style.display = 'none';
  elements.kakaotalkCard.style.display = 'none';

  updateCharCounters();
}

// ===================================
// Character Counters
// ===================================

function updateCharCounters() {
  updateCharCounter('linkedin');
  updateCharCounter('instagram');
  updateCharCounter('circle');
  updateCharCounter('kakaotalk');
}

function updateCharCounter(platform) {
  const output = elements[`${platform}Output`];
  const counter = elements[`${platform}Counter`];
  const text = output.value;

  switch (platform) {
    case 'linkedin':
      const charCount = text.length;
      counter.textContent = `${charCount} characters`;
      counter.classList.toggle('warning', charCount > 1500);
      counter.classList.toggle('error', charCount > 2000);
      break;

    case 'instagram':
    case 'circle':
      const wordCount = text.trim().split(/\s+/).filter(w => w).length;
      counter.textContent = `${wordCount} words`;

      if (platform === 'instagram') {
        counter.classList.toggle('warning', wordCount > 150);
        counter.classList.toggle('error', wordCount > 200);
      }
      break;

    case 'kakaotalk':
      const sentences = text.split(/[.!?]+/).filter(s => s.trim()).length;
      counter.textContent = `${sentences} sentence${sentences !== 1 ? 's' : ''}`;
      counter.classList.toggle('warning', sentences > 3);
      counter.classList.toggle('error', sentences > 4);
      break;
  }
}

// ===================================
// Clipboard Functions
// ===================================

async function copyToClipboard(platform) {
  const output = elements[`${platform}Output`];
  const text = output.value;

  if (!text || text === 'Generating...') {
    showStatus('error', 'No content to copy');
    return;
  }

  try {
    await navigator.clipboard.writeText(text);
    showStatus('success', `✓ ${PLATFORM_PROMPTS[platform].name} content copied to clipboard!`);

    // Visual feedback on button
    const btn = document.querySelector(`.copy-btn[data-platform="${platform}"]`);
    const originalText = btn.textContent;
    btn.textContent = '✓ Copied!';
    setTimeout(() => {
      btn.textContent = originalText;
    }, 2000);
  } catch (error) {
    showStatus('error', 'Failed to copy to clipboard');
  }
}

// ===================================
// Status Messages
// ===================================

function showStatus(type, message) {
  const statusDiv = document.createElement('div');
  statusDiv.className = `status-message status-${type} fade-in`;
  statusDiv.textContent = message;

  elements.statusContainer.innerHTML = '';
  elements.statusContainer.appendChild(statusDiv);

  // Auto-remove after 5 seconds
  setTimeout(() => {
    statusDiv.style.opacity = '0';
    setTimeout(() => statusDiv.remove(), 300);
  }, 5000);
}

// ===================================
// Initialize App
// ===================================

document.addEventListener('DOMContentLoaded', init);
