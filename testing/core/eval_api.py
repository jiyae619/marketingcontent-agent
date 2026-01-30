#!/usr/bin/env python3
"""
Backend API for evaluating content quality.
Use this to evaluate generated content programmatically without running full test suite.
"""

import sys
import os

# Import from same directory
from evaluators import get_evaluator


def evaluate_content(platform: str, content: str) -> dict:
    """
    Evaluate a single piece of content for a given platform.
    
    Args:
        platform: Platform name (linkedin, instagram, circle, kakaotalk)
        content: Generated content to evaluate
    
    Returns:
        dict with evaluation results including:
        - overall_score: 0-100 score
        - passed: boolean if all criteria passed
        - criteria_results: detailed breakdown
        - summary: human-readable summary
    """
    evaluator = get_evaluator(platform)
    criteria_results = evaluator.evaluate(content)
    
    # Calculate overall metrics
    scores = [r.get('score', 0) for r in criteria_results if r.get('score') is not None]
    overall_score = sum(scores) / len(scores) if scores else 0
    
    passed_count = sum(1 for r in criteria_results if r['passed'])
    total_count = len(criteria_results)
    all_passed = passed_count == total_count
    
    # Create summary
    failed_criteria = [r for r in criteria_results if not r['passed']]
    summary = f"{passed_count}/{total_count} criteria passed"
    
    return {
        'platform': platform,
        'overall_score': round(overall_score, 1),
        'passed': all_passed,
        'passed_criteria': passed_count,
        'total_criteria': total_count,
        'summary': summary,
        'criteria_results': criteria_results,
        'failed_criteria': failed_criteria
    }


def get_quality_grade(score: float) -> str:
    """Convert numeric score to letter grade"""
    if score >= 90:
        return 'A'
    elif score >= 80:
        return 'B'
    elif score >= 70:
        return 'C'
    elif score >= 60:
        return 'D'
    else:
        return 'F'


def evaluate_and_print(platform: str, content: str) -> dict:
    """
    Evaluate content and print results to console.
    Useful for quick testing.
    """
    result = evaluate_content(platform, content)
    
    print(f"\n{'='*60}")
    print(f"Platform: {platform.upper()}")
    print(f"{'='*60}")
    print(f"Overall Score: {result['overall_score']}/100 (Grade: {get_quality_grade(result['overall_score'])})")
    print(f"Status: {'✅ PASSED' if result['passed'] else '❌ FAILED'}")
    print(f"Summary: {result['summary']}\n")
    
    if result['failed_criteria']:
        print("Failed Criteria:")
        for criterion in result['failed_criteria']:
            print(f"  ❌ {criterion['criterion'].upper()}")
            print(f"     {criterion['message']}")
            if criterion.get('suggestion'):
                print(f"     💡 {criterion['suggestion']}")
            print()
    
    return result


# Example usage
if __name__ == '__main__':
    # Test with sample content
    sample_linkedin = """
    Excited to share insights from our latest AI innovation! 
    Our team has developed cutting-edge technology that transforms how businesses approach data analytics.
    
    This breakthrough represents months of dedicated research and development.
    
    Looking forward to discussing this at upcoming industry events.
    """
    
    result = evaluate_and_print('linkedin', sample_linkedin)
    
    # You can also access the raw data
    print(f"\nRaw score: {result['overall_score']}")
    print(f"Passed all checks: {result['passed']}")
