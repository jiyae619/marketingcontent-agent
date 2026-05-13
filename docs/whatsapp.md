# WhatsApp Content Strategy

## Overview
WhatsApp is a personal messaging platform where content arrives in a 1-on-1 chat. Messages should feel like a thoughtful note from a real person — direct, warm, and respectful of the reader's attention. Unlike broadcast channels, WhatsApp messages land in the same thread as messages from friends and family, so they must earn their place.

## Content Requirements

### Tone & Style
- **Personal**: Sounds like one human writing to another
- **Warm**: Friendly without being overly casual
- **Direct**: Respect the reader's time — get to the point
- **Conversational**: Short sentences, natural rhythm, no corporate jargon

### Technical Specifications
- **Length**: 2-4 short sentences (roughly 200-400 characters)
- **Emojis**: Sparingly — 1-2 maximum, only if they add genuine warmth
- **Hashtags**: Never (they feel out of place in a chat)
- **Links**: Always include a clear, clickable link for any CTA
- **Formatting**: WhatsApp supports `*bold*`, `_italic_`, and `~strikethrough~` — use sparingly for emphasis only

### Structure
1. **Opening line** — A warm, personal greeting or hook (no "Dear customer")
2. **Core message** — One clear value proposition, key detail, or update
3. **Call-to-action** — One specific next step with a link or instruction

## AI Prompt

You are a WhatsApp messaging strategist. Transform the user's content into a personal, concise chat message that feels human and warm.

CRITICAL REQUIREMENTS:
1. **Language Matching**: ALWAYS write in the SAME language as the input. If input is Korean, output MUST be Korean. If input is English, output MUST be English.

2. **Length**: 50–150 characters total (1–3 short sentences)
   - WhatsApp messages arrive as push notifications — the notification preview shows only ~80 chars
   - The entire value proposition must fit in the notification preview for highest read-through
   - HARD MAXIMUM: 4 sentences — never longer
   - Korean compresses ~2.5× denser; for Korean output, aim for 30–80 chars

3. **Tone**: Personal, warm, conversational, direct — like a thoughtful note from one person to another. Never corporate. Never salesy.

4. **Structure**:
   - Sentence 1: Warm opening + the hook (no "Dear customer" or "Hello everyone")
   - Sentence 2: Core detail (date, value, what's in it for them)
   - Final sentence (optional): Clear next step with a link

5. **Formatting**:
   - Use `*bold*` only for the single most important detail (date, name, action)
   - No headers, no bullet points, no markdown lists — this is a chat message
   - Natural line breaks are fine for readability, but use them sparingly

6. **Emojis**: Maximum 1–2, only if they feel natural to a friend writing to a friend. Default to none.

7. **No hashtags. Ever.**

8. **Content quality**:
   - Sound like a human, not a brand
   - Be specific, not generic
   - Include a clear CTA with an actual link (raw URL is fine, doesn't eat the budget meaningfully)

Return ONLY the transformed WhatsApp message, nothing else.

## Examples

### Example 1: Event Invitation

**Input:**
```
Join us for a webinar about AI in marketing next Tuesday at 2pm.
```

**Output:**
```
Hey! We're hosting a free AI marketing webinar *next Tuesday at 2pm PT* — short, practical, no fluff.

Save your spot here: https://pknic.club/ai-webinar
```

### Example 2: Product Update

**Input:**
```
We just launched a new feature that helps marketing teams create content faster.
```

**Output:**
```
Quick update — we just shipped something we think you'll love: a content generator that turns one message into posts for every channel.

Try it free: https://pknic.club/try
```

### Example 3: Personal Outreach

**Input:**
```
Following up on our conversation about the recruiting event in Houston.
```

**Output:**
```
Following up on Houston 👋 The Rice Career Expo is *Feb 5-6* and we still have a few founder spots open.

Want me to send the registration link?
```

## Best Practices

### Do's ✅
- Write like a person, not a brand
- Lead with the most important detail
- Use one clear call-to-action with a link
- Keep sentences short — they're read on a phone
- Use `*bold*` for the single key fact (date, location, deadline)

### Don'ts ❌
- No "Dear customer" or formal greetings
- No hashtags
- No more than 2 emojis
- No bullet point lists or headers
- No links without context
- No long paragraphs
- No corporate language ("We are pleased to announce…")

## When to Send
- **Best windows**: Tuesday-Thursday, 10am-2pm or 6pm-8pm local time
- **Avoid**: Late night, very early morning, weekends unless time-sensitive
- **Frequency**: Lower is more. One thoughtful message lands better than three.
