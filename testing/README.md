# Testing Framework

Unified testing system for validating AI-generated marketing content quality across all platforms.

## 📁 Structure

```
testing/
├── core/                       # Python testing modules
│   ├── evaluators.py          # Platform-specific quality rules
│   ├── report_generator.py   # HTML report creator
│   ├── eval_runner.py         # Full test suite runner
│   ├── eval_api.py            # Evaluation API library
│   ├── test_user_input.py     # Quick content tester
│   └── server_eval_example.py # Integration example
│
├── test_data/                  # Test inputs
│   └── test_cases.json        # Predefined test scenarios
│
└── results/                    # Test outputs (auto-generated)
    ├── results_*.json         # Test results data
    └── report_*.html          # Visual HTML reports
```

---

## 🚀 Quick Start

### Run Full Test Suite
```bash
python3 testing/core/eval_runner.py
```
**Output:** `testing/results/report_TIMESTAMP.html`

### Test Your Own Content
1. Edit `testing/core/test_user_input.py` (line 125)
2. Run: `python3 testing/core/test_user_input.py`

### Check Quality Programmatically
```python
from testing.core.eval_api import evaluate_content

result = evaluate_content('linkedin', 'your content here')
print(f"Score: {result['overall_score']}/100")
```

---

## 📊 Core Modules

### `evaluators.py` - Quality Rules Engine
Defines platform-specific criteria:
- **LinkedIn:** 900-1100 characters, professional tone, paragraph structure
- **Instagram:** 125-150 words, casual tone, emojis
- **CIRCLE:** 500-800 words, community-focused, structured
- **Kakaotalk:** Max 3 sentences, conversational, direct

### `report_generator.py` - HTML Report Creator
Generates visual reports with:
- Pass/fail status for each test
- Detailed criterion breakdown
- Scores and suggestions
- Platform-specific metrics

### `eval_runner.py` - Test Suite Runner
Runs comprehensive tests:
1. Loads test cases from `test_data/test_cases.json`
2. Generates content via Gemini API
3. Evaluates against platform criteria
4. Saves results to `results/` directory

### `eval_api.py` - Evaluation Library
Reusable functions for programmatic access:
- `evaluate_content(platform, content)` - Evaluate single content
- `get_quality_grade(score)` - Convert score to letter grade
- `evaluate_and_print(platform, content)` - Evaluate and display

### `test_user_input.py` - Quick Tester
Tests specific input across all platforms. Useful for validating real content before publishing.

### `server_eval_example.py` - Integration Example
Reference code showing how to add quality checking to the main server.

---

## 📝 Test Data

### `test_cases.json` Format
```json
{
  "test_cases": [
    {
      "id": "test_001",
      "platform": "linkedin",
      "description": "Event announcement",
      "input": "Your test content here..."
    }
  ]
}
```

**Add new test cases** by editing this file.

---

## 📈 Results

### JSON Results (`results_*.json`)
Machine-readable test results containing:
- Test metadata (timestamp, counts)
- Individual test results
- Detailed criterion scores
- Generated content

### HTML Reports (`report_*.html`)
Human-friendly visual reports with:
- Summary dashboard
- Platform breakdown
- Detailed test results
- Color-coded pass/fail indicators

**View reports:** Open `testing/results/report_*.html` in your browser

---

## 🔧 Usage Examples

### Example 1: Validate Prompt Changes
```bash
# 1. Edit docs/linkedin.md AI Prompt section
# 2. Run tests
python3 testing/core/eval_runner.py
# 3. Check testing/results/report_*.html
```

### Example 2: Test Specific Content
```python
# testing/core/test_user_input.py
input_text = "북클럽이 2026년에 다시 돌아옵니다!"
# Run: python3 testing/core/test_user_input.py
```

### Example 3: Programmatic Evaluation
```python
from testing.core.eval_api import evaluate_content, get_quality_grade

content = "Your LinkedIn post here..."
result = evaluate_content('linkedin', content)

if result['passed']:
    print(f"✅ Quality check passed! Grade: {get_quality_grade(result['overall_score'])}")
else:
    print("❌ Issues found:")
    for issue in result['failed_criteria']:
        print(f"  - {issue['message']}")
```

---

## 🎯 Evaluation Criteria

Each platform has specific criteria checked:

| Platform | Length | Tone | Format | Other |
|----------|--------|------|--------|-------|
| LinkedIn | 900-1100 chars | Professional indicators | Paragraphs | Hashtags |
| Instagram | 125-150 words | Casual indicators | Emojis | Hashtags |
| CIRCLE | 500-800 words | Community focus | Headers, bullets | Structure |
| Kakaotalk | Max 3 sentences | Direct/actionable | Brevity | No hashtags |

---

## 🔄 Workflow

1. **Write/Edit Prompts** → `docs/*.md`
2. **Run Tests** → `python3 testing/core/eval_runner.py`
3. **Review Results** → Open `testing/results/report_*.html`
4. **Iterate** → Adjust prompts based on feedback
5. **Repeat** → Until all tests pass

---

## 💡 Tips

- **Run tests after every prompt change** to catch regressions
- **Add test cases** for edge cases and new content types
- **Check HTML reports** for visual insights
- **Use eval_api.py** to integrate quality checks into your workflow
- **Keep test_cases.json** updated with real-world examples

---

## 🐛 Troubleshooting

**Import errors?**
→ Run from project root: `python3 testing/core/eval_runner.py`

**No API key?**
→ Check `.env` file has `GEMINI_API_KEY=your_key`

**Tests failing?**
→ Review `testing/results/report_*.html` for specific issues

**Want to add criteria?**
→ Edit `testing/core/evaluators.py`
