# Marketing Channel Agent 🚀

Transform your marketing content for every platform with AI-powered intelligent adaptation.

## Features

- **Multi-Platform Support**: Generate optimized content for LinkedIn, Instagram, CIRCLE, and Kakaotalk
- **AI-Powered**: Uses Google Gemini API for intelligent content transformation
- **Platform-Specific**: Each platform gets content tailored to its unique style and requirements
- **Real-time Generation**: Instant content adaptation with live character/word counters

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/jiyae619/marketingcontent-agent.git
cd marketingcontent-agent
```

### 2. Install Dependencies

```bash
pip3 install python-dotenv
```

### 3. Configure API Key

Create a `.env` file from the template:

```bash
cp .env.example .env
```

Then edit `.env` and add your Google Gemini API key:

```
GEMINI_API_KEY=your_actual_api_key_here
```

> **Get your API key**: https://aistudio.google.com/app/apikey

> **Important**: The `.env` file is gitignored and will NOT be committed to version control. Your API key stays private!

### 4. Run the Server

```bash
python3 server.py
```

The server will start on `http://localhost:8080`

### 5. Open the App

Open your browser and navigate to:
```
http://localhost:8080
```

## How It Works

1. **Backend**: Python server (`server.py`) acts as a proxy to the Gemini API
   - Reads API key from `.env` file (secure)
   - Handles CORS for local development
   - Forwards requests to Google Gemini API

2. **Frontend**: Single-page application
   - Input your original marketing content
   - Click "Generate for All Platforms"
   - Get optimized versions for each platform instantly

## Platform-Specific Transformations

- **LinkedIn**: Professional tone, 1300-1500 characters, thought leadership focus
- **Instagram**: Casual tone, 125-150 words, emoji-enhanced, engaging
- **CIRCLE**: Community-focused, 500-800 words, comprehensive with bullet points
- **Kakaotalk**: Conversational, maximum 3 sentences, direct and actionable

## Security

✅ API key stored in `.env` file (not committed to git)  
✅ `.gitignore` protects sensitive files  
✅ API key never exposed to frontend  
✅ Server-side API key management

## Files

- `index.html` - Frontend UI
- `app.js` - Frontend logic
- `style.css` - Styling
- `server.py` - Backend proxy server
- `.env.example` - Template for environment variables
- `.gitignore` - Git ignore rules

## License

MIT
