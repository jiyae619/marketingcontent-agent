#!/usr/bin/env python3
"""
Evaluation runner for marketing content generation.
Tests AI-generated content against platform-specific criteria.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime
from typing import Dict, List
from dotenv import load_dotenv

# Add testing/core directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from evaluators import get_evaluator
from report_generator import generate_html_report

# Load environment variables
load_dotenv()


class EvalRunner:
    """Main evaluation runner"""
    
    def __init__(self, test_cases_path: str = 'testing/test_data/test_cases.json'):
        self.test_cases_path = test_cases_path
        self.test_cases = []
        self.results = []
        self.api_key = os.getenv('GEMINI_API_KEY')
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
    
    def load_test_cases(self):
        """Load test cases from JSON file"""
        with open(self.test_cases_path, 'r') as f:
            data = json.load(f)
            self.test_cases = data.get('test_cases', [])
        
        print(f"✓ Loaded {len(self.test_cases)} test cases")
    
    def load_platform_prompt(self, platform: str) -> str:
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
    
    def generate_content(self, platform: str, input_text: str) -> str:
        """Generate content using Gemini API"""
        system_prompt = self.load_platform_prompt(platform)
        full_prompt = f"{system_prompt}\n\nUser content to transform:\n{input_text}"
        
        gemini_url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={self.api_key}'
        
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
        
        try:
            with urllib.request.urlopen(req) as response:
                response_data = json.loads(response.read().decode('utf-8'))
                
                if 'candidates' in response_data and len(response_data['candidates']) > 0:
                    return response_data['candidates'][0]['content']['parts'][0]['text']
                else:
                    raise Exception('No response from Gemini')
        
        except urllib.error.HTTPError as e:
            error_data = e.read().decode('utf-8')
            raise Exception(f"API Error: {error_data}")
    
    def run_evaluation(self, test_case: Dict) -> Dict:
        """Run evaluation for a single test case"""
        test_id = test_case['id']
        platform = test_case['platform']
        input_text = test_case['input']
        description = test_case.get('description', '')
        
        print(f"\n{'='*60}")
        print(f"Test: {test_id}")
        print(f"Platform: {platform.upper()}")
        print(f"Description: {description}")
        print(f"{'='*60}")
        
        # Generate content
        print(f"⏳ Generating content...")
        try:
            generated_content = self.generate_content(platform, input_text)
            print(f"✓ Content generated ({len(generated_content)} chars)")
        except Exception as e:
            print(f"✗ Generation failed: {e}")
            return {
                'test_id': test_id,
                'platform': platform,
                'description': description,
                'status': 'FAILED',
                'error': str(e),
                'criteria_results': []
            }
        
        # Evaluate content
        print(f"⏳ Evaluating content...")
        evaluator = get_evaluator(platform)
        criteria_results = evaluator.evaluate(generated_content)

        # Weighted 0-100 total
        overall_score = round(sum(r.get('weighted_score', 0) for r in criteria_results), 1)
        passed_count = sum(1 for r in criteria_results if r['passed'])
        total_count = len(criteria_results)
        
        print(f"\n📊 DETAILED EVALUATION RESULTS\n")
        
        for result in criteria_results:
            criterion_name = result['criterion'].upper()
            score = result.get('score')
            passed = result['passed']
            message = result['message']
            suggestion = result.get('suggestion', '')
            actual = result.get('actual', '')
            expected = result.get('expected', '')
            
            status_icon = "✅" if passed else "❌"
            score_display = f"{score:.0f}/100" if score is not None else "N/A"
            
            weight = result.get('weight', 0)
            weighted = result.get('weighted_score', 0)
            print(f"{criterion_name} Criterion (weight {weight}):")
            print(f"  Score: {score_display} → weighted {weighted:.1f} {status_icon}")
            print(f"  {message}")
            if expected:
                print(f"  Expected: {expected}")
            if actual:
                print(f"  Actual: {actual}")
            if suggestion:
                print(f"  💡 Suggestion: {suggestion}")
            print()

        print(f"Overall Score: {overall_score}/100 ({passed_count}/{total_count} criteria passed)")
        overall_status = 'PASSED' if overall_score >= 70 else 'FAILED'
        print(f"Status: {overall_status} (threshold 70/100)\n")
        
        return {
            'test_id': test_id,
            'platform': platform,
            'description': description,
            'input': input_text,
            'generated_content': generated_content,
            'status': overall_status,
            'passed_criteria': passed_count,
            'total_criteria': total_count,
            'overall_score': overall_score,
            'criteria_results': criteria_results
        }
    
    def run_all(self):
        """Run all test cases"""
        print("="*60)
        print("MARKETING CONTENT EVALUATION")
        print("="*60)
        
        self.load_test_cases()
        
        for test_case in self.test_cases:
            result = self.run_evaluation(test_case)
            self.results.append(result)
        
        self.print_summary()
        self.save_results()
    
    def print_summary(self):
        """Print evaluation summary"""
        print("\n" + "="*60)
        print("EVALUATION SUMMARY")
        print("="*60)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r['status'] == 'PASSED')
        
        print(f"\nTotal Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")
        
        # Breakdown by platform
        print("\nBreakdown by Platform:")
        platforms = {}
        for result in self.results:
            platform = result['platform']
            if platform not in platforms:
                platforms[platform] = {'total': 0, 'passed': 0}
            platforms[platform]['total'] += 1
            if result['status'] == 'PASSED':
                platforms[platform]['passed'] += 1
        
        for platform, stats in platforms.items():
            rate = (stats['passed'] / stats['total'] * 100) if stats['total'] > 0 else 0
            print(f"  {platform.upper()}: {stats['passed']}/{stats['total']} ({rate:.1f}%)")
        
        # Failed tests detail
        failed_tests = [r for r in self.results if r['status'] == 'FAILED']
        if failed_tests:
            print("\nFailed Tests:")
            for result in failed_tests:
                print(f"  ✗ {result['test_id']} ({result['platform']})")
                for criteria in result.get('criteria_results', []):
                    if not criteria['passed']:
                        print(f"    - {criteria['message']}")
    
    def save_results(self):
        """Save results to JSON file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'testing/results/results_{timestamp}.json'
        
        os.makedirs('testing/results', exist_ok=True)
        
        results_data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_tests': len(self.results),
            'passed_tests': sum(1 for r in self.results if r['status'] == 'PASSED'),
            'results': self.results
        }
        
        with open(output_file, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        print(f"\n✓ Results saved to: {output_file}")
        
        # Generate HTML report
        html_file = generate_html_report(results_data, f'testing/results/report_{timestamp}.html')
        print(f"✓ HTML report generated: {html_file}")
        print(f"\n💡 Open the HTML report in your browser to see visual results!")


def main():
    """Main entry point"""
    try:
        runner = EvalRunner()
        runner.run_all()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
