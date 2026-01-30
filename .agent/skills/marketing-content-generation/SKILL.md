---
name: marketing-content-generation
description: Generate platform-optimized marketing content for LinkedIn, Instagram, CIRCLE, and Kakaotalk using AI. Adapts tone, length, and format for each platform's unique requirements.
---

# Marketing Content Generation

Transform marketing messages into platform-specific content optimized for LinkedIn, Instagram, CIRCLE, and Kakaotalk.

## When to Use This Skill

Use when the user needs to:
- Adapt marketing content for multiple social platforms
- Generate platform-specific posts from a single message
- Ensure content meets platform requirements (length, tone, format)
- Test or refine AI prompts for content generation

## Quick Start

Copy this checklist and track progress:

```
Content Generation Progress:
- [ ] Step 1: Understand the source content
- [ ] Step 2: Select target platforms
- [ ] Step 3: Generate platform-specific content
- [ ] Step 4: Review and refine outputs
- [ ] Step 5: Update prompts if needed
```

## Platform Requirements

### LinkedIn
- **Prompt**: `docs/linkedin.md` (## AI Prompt section)

### Instagram
- **Prompt**: `docs/instagram.md` (## AI Prompt section)

### CIRCLE
- **Prompt**: `docs/circle.md` (## AI Prompt section)

### Kakaotalk
- **Prompt**: `docs/kakaotalk.md` (## AI Prompt section)

## Workflow

### Step 1: Understand the Source Content

Identify:
- Core message or announcement including time, location, and any logistic details
- Target audience
- Key value propositions
- Desired call-to-action

### Step 2: Select Target Platforms

Determine which platforms to generate for based on:
- Platform selection (LinkedIn, Instagram, CIRCLE, Kakaotalk)
- Content type (announcement, educational, promotional, event)
- Campaign goals

### Step 3: Generate Platform-Specific Content

**Using the Web App:**

1. Start server: `python3 server.py`
2. Open `http://localhost:8080`
3. Enter source content in textarea
4. Select platforms via checkboxes
5. Click "Generate for Selected Platforms"
6. Review generated content in platform cards

**Using API Directly:**

```bash
# Get platform prompt
curl http://localhost:8080/api/prompts/linkedin

# Generate content
curl -X POST http://localhost:8080/api/gemini \
  -H "Content-Type: application/json" \
  -d '{
    "system": "prompt from above",
    "messages": [{"role": "user", "content": "your content"}]
  }'
```

### Step 4: Review and Refine Outputs

Check each platform output for:
- **Length compliance**: Character/word count within limits
- **Tone accuracy**: Matches platform expectations
- **Format correctness**: Proper structure, hashtags, emojis
- **Message clarity**: Core value proposition preserved

If output doesn't meet requirements, proceed to Step 5.

### Step 5: Update Prompts if Needed

**To modify prompts:**

1. Open `docs/<platform>.md`
2. Find `## AI Prompt` section
3. Edit requirements or instructions
4. Save file
5. Refresh browser (prompts reload automatically)
6. Regenerate content

**Common prompt adjustments:**
- Adjust length requirements
- Modify tone instructions
- Add/remove formatting rules
- Update hashtag guidelines

## File Structure

```
marketingcontent/
├── docs/
│   ├── linkedin.md      # LinkedIn strategy + AI prompt
│   ├── instagram.md     # Instagram strategy + AI prompt
│   ├── circle.md        # CIRCLE strategy + AI prompt
│   └── kakaotalk.md     # Kakaotalk strategy + AI prompt
├── server.py            # Backend API server
├── app.js               # Frontend logic
├── index.html           # Web interface
└── .env                 # API key (gitignored)
```

## Evaluating Output Quality

Run evaluations to test prompt effectiveness:

```bash
# Run evaluation suite
python3 eval_runner.py

# View results
open evals/report_*.html
```

Evaluation criteria:
- Length compliance
- Tone appropriateness
- Format correctness
- Logistic details when mentioned (time, location, etc.)
- Hashtag usage
- Emoji placement (Instagram)
- Sentence count (Kakaotalk)

## Common Issues

**Issue**: Generated content too long/short
- **Fix**: Edit length requirement in `docs/<platform>.md` AI Prompt section

**Issue**: Wrong tone (too formal/casual)
- **Fix**: Adjust tone description in AI Prompt section

**Issue**: Missing hashtags or emojis
- **Fix**: Emphasize requirement in prompt (e.g., "MUST include 3-5 hashtags")

**Issue**: Prompts not loading
- **Fix**: Check server is running, verify `docs/*.md` files exist, check browser console

## Environment Setup

Required:
- Python 3.x
- Google Gemini API key
- `python-dotenv` package

Setup:
```bash
# Install dependencies
pip3 install python-dotenv

# Configure API key
cp .env.example .env
# Edit .env and add: GEMINI_API_KEY=your_key_here

# Start server
python3 server.py
```

## Advanced: Prompt Engineering

Best practices for editing AI prompts in `docs/*.md`:

1. **Be specific**: "1,300-1,500 characters" not "short"
2. **Use constraints**: "MAXIMUM 3 sentences" for hard limits
3. **Provide structure**: "Hook → Key points → CTA"
4. **Set expectations**: "Return ONLY the transformed post, nothing else"
5. **Test iteratively**: Make small changes, test, refine

## Reference Documentation

- Platform strategies: `docs/<platform>.md`
- API endpoints: `server.py`
- Frontend logic: `app.js`
- Evaluation framework: `evals/evaluators.py`
