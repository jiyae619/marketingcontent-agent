# Marketing Channel Agent - Walkthrough

AI-powered web app that transforms marketing content for LinkedIn, Instagram, CIRCLE, and Kakaotalk with platform-specific optimization.

---

## 🎯 What It Does

Reduces content adaptation time from **30-45 minutes to 5-10 minutes** by using AI (Google Gemini) to intelligently transform your content for each platform while you maintain full editing control.

---

## 📁 Files

Located in `/Users/jiyaechoi/dev/marketingcontent/`:

- `index.html` - Main application UI
- `style.css` - Premium dark mode design system
- `app.js` - Frontend logic & AI integration  
- `server.py` - Local proxy server (bypasses CORS)

---

## 🚀 How to Use

### 1. Start the Server

```bash
cd /Users/jiyaechoi/dev/marketingcontent
python3 server.py
```

Keep this running while using the app.

### 2. Get Gemini API Key (FREE!)

- Go to https://aistudio.google.com/app/apikey
- Click "Create API Key"
- Copy the key (starts with `AIza`)

### 3. Open the App

- Browser: http://localhost:8080
- Enter your Gemini API key
- Click "Save Key"

### 4. Transform Content

1. **Paste** your marketing content
2. **Click** "Generate for All Platforms"
3. **Review** AI-generated versions for each platform
4. **Edit** any content as needed
5. **Copy** to clipboard and paste into each platform

---

## 🎯 Platform-Specific Rules

### LinkedIn
- Professional tone, 1300-1500 characters
- 3-5 professional hashtags
- Hook → Key points → CTA structure

### Instagram  
- Casual tone, 125-150 words
- 3-5 emojis, 5-8 hashtags
- Strong first-line hook

### CIRCLE
- Informative, 500-800 words
- Bullet points for scannability
- Discussion prompts

### Kakaotalk
- Conversational, max 3 sentences
- Chat-like, ultra-concise
- Single key takeaway

---

## 💡 Technical Notes

**Why the proxy server?**

Browsers block direct API calls to Gemini due to CORS security policy. The `server.py` proxy:
- Receives requests from your browser (same origin = allowed)
- Forwards them to Gemini API (server-to-server = no CORS)
- Returns results to your browser

Think of it as: You → Assistant → Gemini → Assistant → You

**No SDK needed**: Uses Python's built-in libraries only (`http.server`, `json`, `urllib`)

---

## ✅ Features

✅ Multi-platform support (4 channels)  
✅ AI-powered transformations (Gemini 2.5 Flash)  
✅ Human-in-the-loop editing  
✅ Real-time character/word counting  
✅ Copy-to-clipboard  
✅ Premium dark mode UI  
✅ Free to use (Gemini API)

---

## 🎉 Benefits

**Time Savings**: 70%+ time reduction  
**Quality**: Platform-optimized content every time  
**Control**: Full editing before publishing  
**Cost**: Free with Gemini API  

Stop wasting 30-45 minutes per post. Start transforming content in 5-10 minutes!
