#!/usr/bin/env python3
"""
Test script to generate and evaluate content for all platforms
with the user's input data.
"""

import json
import os
import urllib.request
from dotenv import load_dotenv
from eval_api import evaluate_content, get_quality_grade

load_dotenv()

def load_platform_prompt(platform: str) -> str:
    """Load prompt from markdown file"""
    md_path = f'docs/{platform}.md'
    
    if not os.path.exists(md_path):
        raise FileNotFoundError(f'Documentation file not found: {md_path}')
    
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract content between "## AI Prompt" and next "##"
    start_marker = '## AI Prompt'
    start_idx = content.find(start_marker)
    
    if start_idx == -1:
        raise ValueError(f'AI Prompt section not found in {md_path}')
    
    prompt_start = start_idx + len(start_marker)
    next_header_idx = content.find('\n##', prompt_start)
    
    if next_header_idx == -1:
        prompt_content = content[prompt_start:]
    else:
        prompt_content = content[prompt_start:next_header_idx]
    
    return prompt_content.strip()


def generate_content(platform: str, input_text: str, api_key: str) -> str:
    """Generate content using Gemini API"""
    system_prompt = load_platform_prompt(platform)
    full_prompt = f"{system_prompt}\n\nUser content to transform:\n{input_text}"
    
    gemini_url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={api_key}'
    
    payload = {
        "contents": [{
            "parts": [{
                "text": full_prompt
            }]
        }]
    }
    
    req = urllib.request.Request(
        gemini_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    with urllib.request.urlopen(req) as response:
        response_data = json.loads(response.read().decode('utf-8'))
        
        if 'candidates' in response_data and len(response_data['candidates']) > 0:
            return response_data['candidates'][0]['content']['parts'][0]['text']
        else:
            raise Exception('No response from Gemini')


def test_platform(platform: str, input_text: str, api_key: str):
    """Generate and evaluate content for a platform"""
    print(f"\n{'='*70}")
    print(f"🎯 TESTING: {platform.upper()}")
    print(f"{'='*70}")
    print(f"Input: {input_text}\n")
    
    # Generate content
    print("⏳ Generating content...")
    try:
        generated = generate_content(platform, input_text, api_key)
        print(f"✅ Generated ({len(generated)} chars)\n")
        print(f"Generated Content:\n{'-'*70}")
        print(generated)
        print(f"{'-'*70}\n")
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        return
    
    # Evaluate content
    print("⏳ Evaluating quality...")
    result = evaluate_content(platform, generated)
    
    print(f"\n📊 EVALUATION RESULTS")
    print(f"{'='*70}")
    print(f"Overall Score: {result['overall_score']}/100 (Grade: {get_quality_grade(result['overall_score'])})")
    print(f"Status: {'✅ PASSED' if result['passed'] else '❌ FAILED'}")
    print(f"Summary: {result['summary']}\n")
    
    # Show detailed results
    print("Criteria Breakdown:")
    for criterion in result['criteria_results']:
        status = "✅" if criterion['passed'] else "❌"
        score = criterion.get('score')
        score_str = f"{score:.0f}/100" if score is not None else "N/A"
        
        print(f"  {status} {criterion['criterion'].upper()}: {score_str}")
        print(f"     {criterion['message']}")
        
        if not criterion['passed'] and criterion.get('suggestion'):
            print(f"     💡 {criterion['suggestion']}")
        print()


def main():
    """Test all platforms with user input"""
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY not found in environment variables")
        return
    
    # User's input
    input_text = "북클럽이 2026년에 다시 돌아옵니다! 2/22일, 3회 세션, 2명의 pker와 함께 함."
    
    platforms = ['linkedin', 'instagram', 'circle', 'kakaotalk']
    
    print("\n" + "="*70)
    print("🚀 TESTING ALL PLATFORMS WITH USER INPUT")
    print("="*70)
    
    for platform in platforms:
        test_platform(platform, input_text, api_key)
    
    print("\n" + "="*70)
    print("✅ ALL TESTS COMPLETE")
    print("="*70)


if __name__ == '__main__':
    main()
