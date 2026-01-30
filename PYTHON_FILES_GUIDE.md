# Python Files Explained (Simple Guide) 🐍

## What Are Python Files?

Python files (ending in `.py`) are like recipe books that tell the computer what to do, step by step. Think of them as instruction manuals written in a language computers understand!

---

## 📁 Project Structure

Here's how our project is organized:

```
marketingcontent/
├── server.py                    ⭐ Main server (the boss!)
├── scripts/                     🔧 Helper tools
│   ├── eval_runner.py          
│   ├── eval_api.py             
│   ├── test_user_input.py      
│   └── server_eval_example.py  
└── evals/                       📊 Quality checkers
    ├── evaluators.py           
    └── report_generator.py     
```

---

## ⭐ Main File (You Need This!)

### `server.py` - The Boss
**What it does:** This is like the manager of a restaurant. It:
- Listens for requests from your web browser
- Sends your content to Google's AI (Gemini)
- Sends the AI's response back to you

**When to use:** Every time you want to use the app!
```bash
python3 server.py
```

**Simple analogy:** It's like a waiter who takes your order (content), brings it to the chef (AI), and brings back your food (transformed content).

---

## 🔧 Helper Scripts (Optional Tools)

These are in the `scripts/` folder. You don't need them to run the app, but they're useful for testing!

### `eval_runner.py` - The Quality Inspector
**What it does:** Tests if the AI is doing a good job by:
- Generating content for test cases
- Checking if it meets requirements (length, tone, format)
- Creating a report card (HTML file)

**When to use:** When you want to test if your AI prompts are working well
```bash
python3 scripts/eval_runner.py
```

**Simple analogy:** Like a teacher grading homework to see if students followed the instructions.

---

### `test_user_input.py` - The Quick Tester
**What it does:** Quickly tests YOUR content on all 4 platforms
- Takes your input
- Generates content for LinkedIn, Instagram, CIRCLE, Kakaotalk
- Shows you quality scores

**When to use:** When you want to test a specific message
```bash
python3 scripts/test_user_input.py
```

**Simple analogy:** Like trying on an outfit in 4 different mirrors to see how it looks.

---

### `eval_api.py` - The Quality Checker Library
**What it does:** Contains reusable code for checking content quality
- Checks length, tone, format
- Gives scores (0-100)
- Provides suggestions for improvement

**When to use:** Other scripts use this automatically. You don't run it directly.

**Simple analogy:** Like a ruler and scale that other tools use to measure things.

---

### `server_eval_example.py` - The Example Code
**What it does:** Shows programmers how to add quality checking to the server
- Example code only
- Not used in the actual app

**When to use:** Only if you're a programmer wanting to add features

**Simple analogy:** Like a sample recipe showing how to combine ingredients.

---

## 📊 Quality Checkers (Auto-Used)

These are in the `evals/` folder. They work automatically when you run the scripts.

### `evaluators.py` - The Rule Book
**What it does:** Contains all the rules for each platform:
- LinkedIn: Must be 900-1100 characters
- Instagram: Must be 125-150 words
- CIRCLE: Must be 500-800 words
- Kakaotalk: Must be max 3 sentences

**Simple analogy:** Like a referee's rulebook in sports.

---

### `report_generator.py` - The Report Card Maker
**What it does:** Creates pretty HTML reports showing:
- Which tests passed ✅
- Which tests failed ❌
- Scores and suggestions

**Simple analogy:** Like a teacher creating a colorful report card with grades and comments.

---

## 🎯 Quick Reference

**Just want to use the app?**
→ Only run `server.py`

**Want to test if AI prompts are good?**
→ Run `scripts/eval_runner.py`

**Want to test your own content?**
→ Edit and run `scripts/test_user_input.py`

**Want to understand the code?**
→ Read `scripts/eval_api.py` and `evals/evaluators.py`

---

## 🤔 Common Questions

**Q: Do I need all these files?**
A: No! You only need `server.py` to use the app. The others are for testing and quality checking.

**Q: What's the difference between `scripts/` and `evals/`?**
A: 
- `scripts/` = Tools you run directly
- `evals/` = Helper code that scripts use automatically

**Q: Can I delete the scripts folder?**
A: Yes, if you never want to test content quality. But it's useful to keep!

**Q: Which file should I edit to change AI prompts?**
A: None of these! Edit the files in `docs/` folder (like `docs/linkedin.md`)

---

## 📚 Summary

Think of it like a kitchen:
- **server.py** = The head chef (makes your food)
- **scripts/** = Quality inspectors (taste-test the food)
- **evals/** = Recipe books and measuring tools (used by inspectors)
- **docs/** = The menu (what to make and how)

You only need the head chef to run the restaurant, but the inspectors help make sure the food is great! 🍳
