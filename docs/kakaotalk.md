# Kakaotalk Content Strategy

## Overview
Kakaotalk is a mobile messaging platform where brevity and directness are essential. Content should be conversational, concise, and action-oriented—like a message from a friend.

## Content Requirements

### Tone & Style
- **Conversational**: Like texting a friend but not too casual
- **Direct**: Get to the point quickly
- **Friendly**: Warm and approachable
- **Action-oriented**: Clear next steps

### Technical Specifications
- **Length**: MAXIMUM 3 sentences (critical constraint)
- **Emojis**: Only if extremely natural (avoid overuse), Maximum 2 emojis
- **Hashtags**: Never
- **Links**: Keep short or use link shorteners

### Structure
1. **Opening** (Sentence 1)
   - Hook or main point
   - Grab attention immediately

2. **Value** (Sentence 2)
   - Key information (time, location, speakers)

3. **Action** (Sentence 3)
   - Clear CTA
   - What to do next


## AI Prompt

You are a KakaoTalk messaging strategist. Turn the brief into a short message
announcing an UPCOMING event.

GROUNDING — this overrides every rule below it:
- Use ONLY facts stated in the brief. Never invent a name, date, time, weekday,
  location, price, topic or benefit. If the brief gives a date but no weekday,
  do not supply one.
- A missing detail is omitted — never guessed, and never a placeholder or an
  invented link — no [링크], no [Link], no [날짜].
- Never re-label the event. Career coaching stays career coaching — never 세미나,
  워크샵, 워크숍, 마스터클래스, 특강, 강연 or 컨퍼런스, and never their English forms.
- Nothing in these instructions is content. Never copy a phrase or place name out
  of this prompt into the message.
- The event has NOT happened yet. Announce it — never a recap and never
  참석해 주셔서 감사합니다 / 마쳤습니다 / 진행했습니다 / 배웠습니다.

LANGUAGE:
- Korean brief -> Korean message. English brief -> English message.
- Keep names, venues, places and time-zone codes exactly as the brief writes them —
  including English inside a Korean message (Seattle University, PST). Never
  translate or romanise them: 박운영 stays 박운영, never "Park Won-young".

FORMAT:
- 1-3 sentences, 50-150 characters (Korean 30-80). HARD MAXIMUM 3 sentences —
  KakaoTalk competes with friend texts and longer reads as spam.
- Sentence 1: the single most compelling reason to care.
- Sentence 2: one key detail.
- Sentence 3: the call to action.
- At most 2 emojis. No hashtags, ever.
- Plain text only: no **bold**, no *italic*, no ## headings, no [text](url).

Return only the message — no explanation, notes or commentary.
## Examples


### Example 1: Event Invitation

**Input:**
```
Join us for a webinar about AI in marketing next Tuesday at 2pm.
```

**Output:**
```
We're hosting a free webinar on AI marketing tools next Tuesday at 2pm! 
You'll learn how to 10x your content production. Click here to register: 
[link]
```

### Example 3: Update Notification

**Input:**
```
We've added new features to our platform based on your feedback.
```

**Output:**
```
Good news! We just added the features you requested—batch processing and 
custom templates. Update your app to try them now!
```

### Example 4: Promotional Offer

**Input:**
```
Get 50% off our premium plan this week only with special discount code.
```

**Output:**
```
Flash sale! Get 50% off premium this week with code SAVE50. Offer ends 
Friday—don't miss out!
```

### Example 5: Content Share

**Input:**
```
Check out our new blog post about improving social media engagement.
```

**Output:**
```
Just published: 5 proven ways to boost your social media engagement (with 
real examples). Read it here: [link]
```

### Example 6: Question/Poll

**Input:**
```
We want to know which feature you'd like us to build next.
```

**Output:**
```
Quick question: Which feature would help you most—TikTok support or team 
collaboration? Reply with A or B!
```

### Example 7: Thank You Message

**Input:**
```
Thanks for being an early adopter and providing valuable feedback.
```

**Output:**
```
Thank you for being an early supporter! Your feedback helped shape the 
product. Check your email for a special gift 🎁
```

## Best Practices

### Do's ✅
- Keep it under 3 sentences (strict rule)
- Use active voice
- Be specific and clear
- Include one clear CTA
- Make it feel personal
- Use conversational language
- Test readability on mobile
- Respond quickly to replies

### Don'ts ❌
- Don't exceed 3 sentences
- Avoid jargon or complex terms
- Skip unnecessary details
- Don't use multiple CTAs
- Avoid formal or stiff language
- Don't use hashtags
- Skip emoji overload
- Don't send without a clear purpose

## Message Types

### Announcement
**Format**: [What] + [Benefit] + [Action]

**Example:**
```
We just launched dark mode! It's easier on your eyes and saves battery. 
Update your app to enable it.
```

### Invitation
**Format**: [Event] + [Value] + [How to join]

**Example:**
```
Join our live Q&A tomorrow at 3pm! Ask anything about AI marketing. 
Register here: [link]
```

### Update
**Format**: [What changed] + [Why it matters] + [Next step]

**Example:**
```
Your dashboard just got faster! Pages now load 3x quicker. Refresh to see 
the difference.
```

### Offer
**Format**: [Deal] + [Urgency] + [How to claim]

**Example:**
```
Early bird special: 40% off for the next 24 hours! Use code EARLY40 at 
checkout.
```

### Question
**Format**: [Context] + [Question] + [How to respond]

**Example:**
```
We're planning our next feature update! What would help you most—analytics 
or automation? Reply with your pick!
```

## Emoji Usage

### When to Use
- Celebration/excitement: 🎉, ✨, 🚀
- Gifts/offers: 🎁, 💝
- Alerts: ⚠️, 🔔
- Questions: ❓, 🤔

### When to Skip
- Professional announcements
- Problem notifications
- Formal communications
- When it doesn't add value

### Best Practices
- Maximum 1-2 emojis per message
- Use only if it feels natural
- Match emoji to message tone
- Don't replace words with emojis

## Timing & Frequency

### Best Times to Send
- **Morning**: 8-9am (commute time)
- **Lunch**: 12-1pm (break time)
- **Evening**: 7-9pm (after work)

### Avoid
- Late night (after 9pm)
- Very early morning (before 7am)
- During typical work hours (10am-5pm)

### Frequency
- **Promotional**: Max 2-3 times per week
- **Updates**: As needed, but batch when possible
- **Responses**: Immediately to within 1 hour

## Link Handling

### Best Practices
- Use link shorteners (bit.ly, tinyurl)
- Make purpose clear before link
- Test links on mobile
- Track click-through rates

### Example
```
❌ Check this out: https://www.example.com/blog/post/how-to-improve-marketing-roi-2024
✅ 5 ways to boost your ROI: bit.ly/roi-tips
```

## Call-to-Action Examples

### Strong CTAs
- "Want to try it?"
- "Click here to register"
- "Reply with your answer"
- "Update now"
- "Grab your spot"
- "Don't miss out"

### Weak CTAs
- "Let us know what you think"
- "Check it out if you want"
- "Maybe you'd be interested"
- "Feel free to..."

## Common Mistakes

### ❌ Too Long
```
We're excited to announce that after months of development and testing, 
we've finally launched our new AI-powered marketing tool that helps teams 
create platform-specific content in just seconds, and we'd love for you 
to try it out!
```

### ✅ Just Right
```
We just launched an AI tool that creates platform-specific content in 
seconds! Try it now: [link]
```

### ❌ Too Vague
```
Something exciting is coming soon. Stay tuned for updates!
```

### ✅ Specific
```
New feature drops Monday at 9am! It'll save you 5+ hours per week. Set a 
reminder!
```

### ❌ Multiple CTAs
```
Check out our new blog post, follow us on Instagram, and don't forget to 
register for the webinar!
```

### ✅ Single CTA
```
New blog post: How to 10x your content output. Read it here: [link]
```

## Performance Metrics

### Track These KPIs
- Open rate
- Response rate
- Click-through rate (for links)
- Conversion rate
- Unsubscribe rate

### Optimization
- Test different message lengths (1-3 sentences)
- A/B test CTAs
- Monitor response times
- Analyze best-performing messages
- Adjust timing based on engagement

## Platform-Specific Notes

### Kakaotalk Features
- **Read receipts**: Know when messages are seen
- **Group chats**: Different strategy than 1-on-1
- **Stickers**: Use sparingly in marketing
- **Voice messages**: Generally avoid for marketing

### Cultural Considerations
- Popular in South Korea and some Asian markets
- More casual than email
- Expected quick responses
- Personal feel is important

## Testing Checklist

Before sending, verify:
- [ ] 3 sentences or less
- [ ] Clear single CTA
- [ ] Readable on mobile
- [ ] Links work and are shortened
- [ ] Tone is conversational
- [ ] Purpose is immediately clear
- [ ] Emojis (if used) add value
- [ ] No typos or errors
