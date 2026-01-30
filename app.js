// ===================================
// State Management
// ===================================

const APP_STATE = {
  apiKey: null,
  isGenerating: false,
  originalContent: ''
};

// ===================================
// Platform Prompts (loaded dynamically from markdown files)
// ===================================

let PLATFORM_PROMPTS = {};

// ===================================
// DOM Elements
// ===================================

const elements = {
  // Main content
  mainContent: document.getElementById('mainContent'),

  // Platform selectors
  selectLinkedin: document.getElementById('selectLinkedin'),
  selectInstagram: document.getElementById('selectInstagram'),
  selectCircle: document.getElementById('selectCircle'),
  selectKakaotalk: document.getElementById('selectKakaotalk'),

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
  // Platform Selection
  elements.selectLinkedin.addEventListener('change', updateGenerateButtonText);
  elements.selectInstagram.addEventListener('change', updateGenerateButtonText);
  elements.selectCircle.addEventListener('change', updateGenerateButtonText);
  elements.selectKakaotalk.addEventListener('change', updateGenerateButtonText);

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
  elements.linkedinOutput.addEventListener('input', () => {
    updateCharCounter('linkedin');
    updatePreview('linkedin');
  });
  elements.instagramOutput.addEventListener('input', () => {
    updateCharCounter('instagram');
    updatePreview('instagram');
  });
  elements.circleOutput.addEventListener('input', () => {
    updateCharCounter('circle');
    updatePreview('circle');
  });
  elements.kakaotalkOutput.addEventListener('input', () => {
    updateCharCounter('kakaotalk');
    updatePreview('kakaotalk');
  });

  // Tab Switching
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const targetTab = e.currentTarget.getAttribute('data-tab');
      switchTab(targetTab);
    });
  });
}

// ===================================
// API Key Management
// ===================================
// API key management removed - now handled in backend via .env file

// ===================================
// Platform Selection
// ===================================

function getSelectedPlatforms() {
  const selected = [];
  if (elements.selectLinkedin.checked) selected.push('linkedin');
  if (elements.selectInstagram.checked) selected.push('instagram');
  if (elements.selectCircle.checked) selected.push('circle');
  if (elements.selectKakaotalk.checked) selected.push('kakaotalk');
  return selected;
}

function updateGenerateButtonText() {
  const selected = getSelectedPlatforms();
  const btnText = elements.generateBtnText;

  if (selected.length === 0) {
    btnText.textContent = '🚀 Select at least one platform';
    elements.generateBtn.disabled = true;
  } else {
    btnText.textContent = '🚀 Generate Content!';
    elements.generateBtn.disabled = false;
  }
}

// ===================================
// Content Generation
// ===================================

async function generateAllPlatforms() {
  const content = elements.originalContent.value.trim();

  if (!content) {
    showStatus('error', 'Please enter some content to transform');
    return;
  }

  const selectedPlatforms = getSelectedPlatforms();

  if (selectedPlatforms.length === 0) {
    showStatus('error', 'Please select at least one platform');
    return;
  }

  APP_STATE.isGenerating = true;
  setGeneratingState(true);

  // Hide all platform cards first
  elements.linkedinCard.style.display = 'none';
  elements.instagramCard.style.display = 'none';
  elements.circleCard.style.display = 'none';
  elements.kakaotalkCard.style.display = 'none';

  // Show and prepare only selected platform cards
  selectedPlatforms.forEach(platform => {
    elements[`${platform}Card`].style.display = 'block';
    elements[`${platform}Output`].value = 'Generating...';
  });

  // Convert to markdown (simple conversion)
  const markdownContent = convertToMarkdown(content);

  // Generate for selected platforms in parallel
  const promises = selectedPlatforms.map(platform =>
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
    updatePreview(platform); // Update preview after generation
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
// Initialization
// ===================================

async function loadPlatformPrompts() {
  const platforms = ['linkedin', 'instagram', 'circle', 'kakaotalk'];
  const prompts = {};

  try {
    for (const platform of platforms) {
      const response = await fetch(`http://localhost:8080/api/prompts/${platform}`);
      const data = await response.json();

      if (data.error) {
        throw new Error(`Failed to load ${platform} prompt: ${data.error}`);
      }

      prompts[platform] = {
        name: platform.charAt(0).toUpperCase() + platform.slice(1),
        systemPrompt: data.prompt
      };
    }

    // Special case for CIRCLE (all caps)
    if (prompts.circle) {
      prompts.circle.name = 'CIRCLE';
    }

    return prompts;
  } catch (error) {
    console.error('Error loading platform prompts:', error);
    showStatus('error', 'Failed to load platform instructions. Please refresh the page.');
    throw error;
  }
}


async function init() {
  try {
    // Load prompts from markdown files
    PLATFORM_PROMPTS = await loadPlatformPrompts();
    console.log('Platform prompts loaded successfully');

    // Attach event listeners
    attachEventListeners();

    // Initialize UI
    updateGenerateButtonText();
  } catch (error) {
    console.error('Initialization failed:', error);
  }
}


// ===================================
// Preview Update Functions
// ===================================

function updatePreview(platform) {
  const content = elements[`${platform}Output`].value;
  const previewElement = document.getElementById(`${platform}PreviewContent`);

  if (!previewElement || !content) return;

  // Update preview based on platform
  switch (platform) {
    case 'linkedin':
      updateLinkedInPreview(content, previewElement);
      break;
    case 'instagram':
      updateInstagramPreview(content, previewElement);
      break;
    case 'circle':
      updateCirclePreview(content, previewElement);
      break;
    case 'kakaotalk':
      updateKakaotalkPreview(content, previewElement);
      break;
  }
}

function updateLinkedInPreview(content, element) {
  // Preserve line breaks and format hashtags
  const formatted = content
    .split('\n')
    .map(line => {
      // Make hashtags blue
      return line.replace(/#(\w+)/g, '<span style="color: #0077b5;">#$1</span>');
    })
    .join('\n');

  element.innerHTML = formatted;
}

function updateInstagramPreview(content, element) {
  // Format hashtags in blue and preserve emojis
  const formatted = content.replace(/#(\w+)/g, '<span style="color: #0095f6;">#$1</span>');
  element.innerHTML = `<span class="instagram-username">pknic_official</span> ${formatted}`;
}

function updateCirclePreview(content, element) {
  // Parse markdown-style headers and format them
  const formatted = content
    .split('\n')
    .map(line => {
      // Convert ## headers to styled headers
      if (line.startsWith('## ')) {
        return `<h2>${line.substring(3)}</h2>`;
      }
      // Convert bullet points
      if (line.trim().startsWith('*   ') || line.trim().startsWith('- ')) {
        return `<li>${line.trim().substring(4)}</li>`;
      }
      return line;
    })
    .join('\n');

  element.innerHTML = formatted;
}

function updateKakaotalkPreview(content, element) {
  // Simple text display for Kakaotalk
  element.textContent = content;
}

// ===================================
// Tab Switching
// ===================================

function switchTab(tabName) {
  // Remove active class from all tabs and tab contents
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('active');
  });
  document.querySelectorAll('.tab-content').forEach(content => {
    content.classList.remove('active');
  });

  // Add active class to selected tab and content
  const selectedBtn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
  const selectedContent = document.getElementById(`tab-${tabName}`);

  if (selectedBtn && selectedContent) {
    selectedBtn.classList.add('active');
    selectedContent.classList.add('active');
  }
}

async function init() {
  try {
    // Load prompts from markdown files
    PLATFORM_PROMPTS = await loadPlatformPrompts();
    console.log('Platform prompts loaded successfully');

    // Attach event listeners
    attachEventListeners();

    // Initialize UI
    updateGenerateButtonText();
  } catch (error) {
    console.error('Initialization failed:', error);
  }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', init);
