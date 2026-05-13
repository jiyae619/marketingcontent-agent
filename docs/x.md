# X (formerly Twitter) Content Strategy

## Overview
X is a public, real-time conversation platform where posts compete for attention in a fast-scrolling timeline. Content must be punchy, distinctive, and earn the reader's stop in the first six words. Tone is conversational, often opinionated, sometimes funny — but always concise.

## Content Requirements

### Tone & Style
- **Punchy**: Strong opening line, no warm-up
- **Conversational**: Sounds like a real person, not a press release
- **Distinctive**: A point of view, not a summary
- **Direct**: No corporate hedging or "we are excited to announce…"

### Technical Specifications
- **Length**: 280 characters MAXIMUM (hard platform limit), aim for 240-275 for breathing room
- **Hashtags**: 0-2 maximum, only if highly relevant. None is often better.
- **Emojis**: 0-2, only if they add meaning. Default to none.
- **Mentions**: Use @ tags only when directly relevant
- **Links**: One link max — they cost ~23 characters

### Structure
1. **Hook** (first 6-10 words) — must stop the scroll
2. **Payload** — the actual point, claim, or insight
3. **Optional CTA or link** — only if it earns its place

Threads (multi-post) are powerful but each individual post must still stand alone. For this generator, we write single posts.

## AI Prompt

You are an X content strategist. Transform the user's content into a single, punchy X post that earns attention in a fast-scrolling timeline.

CRITICAL REQUIREMENTS:
1. **Language Matching**: ALWAYS write in the SAME language as the input. If input is Korean, output MUST be Korean. If input is English, output MUST be English.

2. **Length**: 100–150 characters is the engagement sweet spot
   - Hard platform cap is 280 characters — never exceed
   - Research: tweets under 100 chars get ~17% higher engagement (retweets, replies)
   - For event/CTA posts that need logistics, allow up to 220–275 chars
   - URLs auto-shorten to 23 chars regardless of actual length (t.co)
   - Korean compresses ~2.5× denser — aim for 60–90 chars for Korean output

3. **Tone**: Punchy, conversational, distinctive. Sounds like a human with a point of view, not a brand statement. No corporate openings ("We are excited to announce…", "We're thrilled to share…"). Just say the thing.

4. **Structure**:
   - First 6–10 words must hook — a claim, a question, a number, a contrast
   - The body delivers the actual point
   - Optional: one CTA or link, but only if it adds value

5. **Formatting**:
   - **1–2 hashtags maximum** (3+ hashtags correlates with spam signals and reach suppression; tweets with 1–2 relevant hashtags get ~2× engagement vs. none)
   - 0–2 emojis maximum, none is often best
   - Line breaks are fine for rhythm but optional
   - No "Thread 🧵" markers — we write single posts
   - Text-only outperforms video on X by ~30% (unique to this platform)

6. **Content quality**:
   - Lead with the most surprising or specific detail
   - Cut every word that doesn't earn its place
   - Specific > generic ("3 founders, $0 raised" > "many entrepreneurs")
   - One idea per post — if you have two, pick the stronger one

Return ONLY the transformed X post, nothing else. Do not include character counts, explanations, or quotation marks.

## Examples

### Example 1: Product Launch

**Input:**
```
We're launching a new AI tool that helps marketing teams create content faster.
```

**Output:**
```
One message in. Six platforms out.

We built the content generator we wish existed — paste once, ship everywhere.

Free to try: pknic.club/try
```

### Example 2: Thought Leadership

**Input:**
```
AI is changing how we work, but many companies are implementing it wrong.
```

**Output:**
```
Most "AI strategies" are just buying tools and hoping.

The teams winning aren't the ones with the most subscriptions. They're the ones who rewrote their workflow first, then picked the model.

Tools are easy. Process is the moat.
```

### Example 3: Event Promotion

**Input:**
```
Join us for a recruiting event at Rice University in Houston on February 5-6, 2026.
```

**Output:**
```
Hiring early-career talent in 2026?

Feb 5-6 in Houston — Rice University Career Expo. Mixer is free for employers, expo booth is $650.

DM us if you want intros to the organizers.
```

## Best Practices

### Do's ✅
- Open with a specific number, claim, or contrast
- Use short sentences and white space for rhythm
- Quote-tweet or reply to real conversations when relevant
- Write like you'd text a smart friend
- Edit ruthlessly — every word costs

### Don'ts ❌
- No "We're excited to announce…"
- No hashtag stacks (#marketing #AI #content #tech)
- No emoji walls (🚀✨🎉💯🔥)
- No vague claims ("game-changer", "revolutionary")
- No more than one link
- No threads — write one strong post

## Hashtag Strategy

### When to use a hashtag
- Live events (#SXSW2026)
- Specific community tags (#buildinpublic)
- Brand campaigns you own

### When NOT to use a hashtag
- Generic descriptors (#marketing, #AI, #business)
- Stacks of 3+ hashtags
- When the post already makes the point without them

## Engagement Tactics

### Increase reach
- Reply to relevant posts from larger accounts (adds your voice to existing conversations)
- Quote-tweet with a take rather than retweet
- Post during peak times (9-11am, 7-9pm in your audience's timezone)
- Use polls for low-effort engagement

### Drive replies
- Ask specific, answerable questions
- Make a claim people can agree or disagree with
- Share a counterintuitive observation
- Avoid yes/no questions

## Character-Count Discipline

Aim for these ranges by post type:
- Hot take / one-liner: 80-140 chars
- Insight with detail: 180-240 chars
- Event / CTA: 220-275 chars

Never exceed 280. Never use "1/" thread markers in a single post.
