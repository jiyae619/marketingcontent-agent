# How to Test the Model 🧪

Simple step-by-step guide for testing your AI content generation.

---

## 🎯 Option 1: Test Everything (Recommended)

**What it does:** Runs all predefined test cases and creates a visual report

**Command:**
```bash
python3 testing/core/eval_runner.py
```

**What happens:**
1. ✅ Loads test cases from `testing/test_data/test_cases.json`
2. ✅ Generates content for each test using Gemini API
3. ✅ Checks quality (length, tone, format)
4. ✅ Creates HTML report with results

**View results:**
```bash
open testing/results/report_*.html
```
Or manually open the HTML file in your browser.

**When to use:**
- After editing AI prompts in `docs/*.md`
- Before deploying changes
- To validate all platforms at once

---

## 🚀 Option 2: Test Your Own Content

**What it does:** Tests a specific message across all 4 platforms

**Steps:**

1. **Edit the test file:**
   ```bash
   # Open testing/core/test_user_input.py
   # Find line 125 and change the input_text
   ```

2. **Change this line:**
   ```python
   input_text = "Your content here!"
   ```

3. **Run the test:**
   ```bash
   python3 testing/core/test_user_input.py
   ```

**What you'll see:**
- Generated content for each platform
- Quality scores (0-100)
- Pass/fail status
- Specific suggestions for improvements

**When to use:**
- Testing a specific announcement
- Validating real content before publishing
- Quick quality check

---

## 💻 Option 3: Test Programmatically (Advanced)

**What it does:** Check quality from your own Python code

**Example:**
```python
from testing.core.eval_api import evaluate_content, get_quality_grade

# Your content
content = "Your LinkedIn post here..."

# Evaluate it
result = evaluate_content('linkedin', content)

# Check results
print(f"Score: {result['overall_score']}/100")
print(f"Grade: {get_quality_grade(result['overall_score'])}")
print(f"Passed: {result['passed']}")

# See what failed
if not result['passed']:
    for issue in result['failed_criteria']:
        print(f"❌ {issue['criterion']}: {issue['message']}")
        print(f"💡 {issue['suggestion']}")
```

**When to use:**
- Integrating quality checks into other tools
- Batch processing multiple pieces of content
- Custom testing workflows

---

## 📊 Understanding Results

### Quality Scores
- **90-100 (A):** Excellent! Ready to publish
- **80-89 (B):** Good, minor tweaks recommended
- **70-79 (C):** Acceptable, needs improvement
- **60-69 (D):** Poor, significant issues
- **0-59 (F):** Failed, major problems

### Common Issues

**"Too short"**
→ Add more details, examples, or context

**"Too long"**
→ Be more concise, remove less important details

**"Lacks professional tone" (LinkedIn)**
→ Add industry terms, professional language

**"Tone too formal" (Instagram)**
→ Use more casual language, emojis

**"Missing emojis" (Instagram)**
→ Add 3-5 emojis strategically

**"Too many sentences" (Kakaotalk)**
→ Combine ideas, maximum 3 sentences

---

## 🔄 Testing Workflow

```
1. Edit AI Prompt
   ↓
   docs/linkedin.md (or other platform)
   
2. Run Tests
   ↓
   python3 testing/core/eval_runner.py
   
3. Check Results
   ↓
   open testing/results/report_*.html
   
4. Fix Issues
   ↓
   Adjust prompts based on feedback
   
5. Test Again
   ↓
   Repeat until all tests pass ✅
```

---

## 🎓 Examples

### Example 1: After Editing LinkedIn Prompt
```bash
# 1. Edit the prompt
# Open docs/linkedin.md and modify the AI Prompt section

# 2. Test it
python3 testing/core/eval_runner.py

# 3. View results
open testing/results/report_*.html

# 4. Check if LinkedIn tests passed
# If not, review suggestions and adjust prompt
```

### Example 2: Testing Event Announcement
```bash
# 1. Edit test_user_input.py line 125
input_text = "북클럽이 2월 22일에 돌아옵니다! 3회 세션, 2명의 pker와 함께."

# 2. Run test
python3 testing/core/test_user_input.py

# 3. Review console output for each platform
# Check scores and suggestions
```

### Example 3: Adding New Test Case
```bash
# 1. Edit testing/test_data/test_cases.json
# Add new test case:
{
  "id": "test_new_001",
  "platform": "instagram",
  "description": "Product launch announcement",
  "input": "We're launching a new product next week!"
}

# 2. Run full test suite
python3 testing/core/eval_runner.py

# 3. Check if new test passes
open testing/results/report_*.html
```

---

## ⚡ Quick Commands Reference

| Task | Command |
|------|---------|
| Run all tests | `python3 testing/core/eval_runner.py` |
| Test your content | Edit `testing/core/test_user_input.py` then run it |
| View latest report | `open testing/results/report_*.html` |
| Add test cases | Edit `testing/test_data/test_cases.json` |
| Check specific platform | Edit test file to only test one platform |

---

## 🐛 Troubleshooting

**"GEMINI_API_KEY not found"**
→ Check `.env` file exists and has your API key

**"Import error"**
→ Run from project root directory

**"No such file"**
→ Make sure you're in `/Users/jiyaechoi/dev/marketingcontent/`

**"All tests failing"**
→ Check if prompts in `docs/*.md` are correct

**"Can't open HTML report"**
→ Manually navigate to `testing/results/` and double-click the HTML file

---

## 💡 Pro Tips

1. **Test after every prompt change** to catch issues early
2. **Keep test cases updated** with real-world examples
3. **Review HTML reports visually** - easier than reading JSON
4. **Use test_user_input.py** for quick iterations
5. **Add edge cases** to test_cases.json (very short, very long, etc.)

---

## 📚 Related Documentation

- **Full testing docs:** `testing/README.md`
- **Python explained simply:** `PYTHON_FILES_GUIDE.md`
- **Project structure:** `PROJECT_STRUCTURE.md`
- **Platform requirements:** `docs/*.md`
