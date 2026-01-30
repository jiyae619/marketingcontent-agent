# Project Structure Overview

## 📂 Complete File Organization

```
marketingcontent/
│
├── 🌐 WEB APP (Main Application)
│   ├── index.html              # Web page interface
│   ├── app.js                  # Frontend logic
│   ├── style.css               # Styling
│   └── server.py               # ⭐ Backend server (START HERE!)
│
├── 📚 DOCUMENTATION
│   ├── README.md               # Setup & usage guide
│   ├── PYTHON_FILES_GUIDE.md   # Simple Python explanation
│   ├── PROJECT_STRUCTURE.md    # This file
│   │
│   ├── docs/                   # Platform strategies & AI prompts
│   │   ├── linkedin.md
│   │   ├── instagram.md
│   │   ├── circle.md
│   │   └── kakaotalk.md
│   │
│   └── references/             # Historical documentation
│       ├── README.md
│       ├── strategic_analysis.md
│       └── walkthrough.md
│
├── 🧪 TESTING (Quality Validation)
│   └── testing/
│       ├── README.md
│       ├── core/                   # Python testing modules
│       │   ├── evaluators.py
│       │   ├── report_generator.py
│       │   ├── eval_runner.py
│       │   ├── eval_api.py
│       │   ├── test_user_input.py
│       │   └── server_eval_example.py
│       │
│       ├── test_data/              # Test inputs
│       │   ├── README.md
│       │   └── test_cases.json
│       │
│       └── results/                # Test outputs (auto-generated)
│           ├── README.md
│           ├── results_*.json
│           └── report_*.html
│
├── 🤖 AI ASSISTANT
│   └── .agent/
│       └── skills/
│           └── marketing-content-generation/
│               └── SKILL.md        # AI assistant instructions
│
└── ⚙️ CONFIGURATION
    ├── .env                    # API key (SECRET - not in git)
    ├── .env.example            # Template for .env
    └── .gitignore              # Files to ignore in git
```

---

## 🎯 Quick Start Guide

### For Regular Use:
1. Make sure `.env` file has your API key
2. Run: `python3 server.py`
3. Open: `http://localhost:8080`
4. Generate content! 🚀

### For Testing Prompts:
1. Run: `python3 testing/core/eval_runner.py`
2. Check: `testing/results/report_*.html` in browser

### For Testing Your Content:
1. Edit: `testing/core/test_user_input.py` (line 125)
2. Run: `python3 testing/core/test_user_input.py`

---

## 📖 Documentation Hierarchy

**Need to use the app?**
→ Read `README.md`

**Don't understand Python files?**
→ Read `PYTHON_FILES_GUIDE.md` (simple explanations)

**Want to edit AI prompts?**
→ Edit files in `docs/` folder

**Want to test content quality?**
→ Read `testing/README.md`

**Need historical context?**
→ Check `references/` folder

---

## 🔑 Key Files Explained

| File | Purpose | When to Use |
|------|---------|-------------|
| `server.py` | Main application server | Every time you use the app |
| `docs/*.md` | Platform strategies & AI prompts | When editing content requirements |
| `testing/core/eval_runner.py` | Test suite runner | When validating prompt changes |
| `testing/core/test_user_input.py` | Quick content tester | When testing specific messages |
| `testing/core/evaluators.py` | Quality checking rules | When understanding evaluation criteria |
| `testing/test_data/test_cases.json` | Test scenarios | When adding new test cases |
| `testing/results/*.html` | Visual test reports | When reviewing test results |

---

## 🎨 Color Key

- 🌐 = User-facing web application
- 📚 = Documentation (read these!)
- 🧪 = Testing & quality validation
- 🤖 = AI assistant configuration
- ⚙️ = System configuration

---

## 📁 Folder Purposes

### `/docs` - Platform Documentation
Contains strategy guides and AI prompts for each platform. **Edit these to change AI behavior.**

### `/testing` - Quality Validation System
Unified testing framework with three parts:
- **core/** - Python testing modules
- **test_data/** - Input test cases
- **results/** - Output reports (gitignored)

### `/references` - Historical Documentation
Background context and implementation history. Not required for daily use.

### `/.agent` - AI Assistant Configuration
Instructions for AI coding assistants to help with the project.

---

## 💡 Pro Tips

1. **Only `server.py` is required** for the app to work
2. **Edit `docs/*.md`** to change AI behavior, not Python files
3. **Use `testing/core/eval_runner.py`** to test changes before deploying
4. **Check `testing/results/report_*.html`** for visual test results
5. **Never commit `.env`** file (it's gitignored for security)
6. **Keep `testing/test_data/test_cases.json`** updated with real examples

---

## 🔄 Typical Workflow

1. **Edit AI Prompt** → `docs/linkedin.md` (or other platform)
2. **Run Tests** → `python3 testing/core/eval_runner.py`
3. **Review Results** → Open `testing/results/report_*.html`
4. **Fix Issues** → Adjust prompts based on feedback
5. **Test Again** → Repeat until all tests pass
6. **Deploy** → Use updated prompts in production

---

## 🚀 Getting Started Checklist

- [ ] Read `README.md` for setup instructions
- [ ] Create `.env` file with your API key
- [ ] Run `python3 server.py` to start the app
- [ ] Test the app at `http://localhost:8080`
- [ ] Read `PYTHON_FILES_GUIDE.md` to understand the code
- [ ] Run `python3 testing/core/eval_runner.py` to see testing in action
- [ ] Review `testing/results/report_*.html` to understand quality metrics
