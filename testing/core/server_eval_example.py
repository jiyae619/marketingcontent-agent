#!/usr/bin/env python3
"""
Example: Integrate evaluation into your server.py
This shows how to add quality checks to your content generation endpoint.
"""

from eval_api import evaluate_content, get_quality_grade


def generate_and_evaluate(platform: str, input_text: str, gemini_api_key: str) -> dict:
    """
    Example function showing how to integrate evaluation into your server.
    
    This would replace or augment your existing content generation logic.
    """
    # Step 1: Generate content (your existing logic)
    # generated_content = call_gemini_api(platform, input_text, gemini_api_key)
    
    # For this example, using sample content
    generated_content = "Sample generated content here..."
    
    # Step 2: Evaluate the generated content
    eval_result = evaluate_content(platform, generated_content)
    
    # Step 3: Return both content and quality metrics
    return {
        'content': generated_content,
        'quality': {
            'score': eval_result['overall_score'],
            'grade': get_quality_grade(eval_result['overall_score']),
            'passed': eval_result['passed'],
            'summary': eval_result['summary'],
            'issues': [
                {
                    'criterion': c['criterion'],
                    'message': c['message'],
                    'suggestion': c.get('suggestion', '')
                }
                for c in eval_result['failed_criteria']
            ]
        }
    }


# Example: Add this to your Flask/HTTP server endpoint
def example_api_endpoint():
    """
    Example of how your API endpoint might look with evaluation.
    """
    # Pseudo-code for your server endpoint
    
    # POST /api/generate
    # {
    #   "platform": "linkedin",
    #   "input": "user input text"
    # }
    
    # Response:
    # {
    #   "content": "generated content...",
    #   "quality": {
    #     "score": 75.5,
    #     "grade": "C",
    #     "passed": false,
    #     "summary": "2/3 criteria passed",
    #     "issues": [
    #       {
    #         "criterion": "length",
    #         "message": "Too short: 437 characters",
    #         "suggestion": "Add 863 more characters..."
    #       }
    #     ]
    #   }
    # }
    
    pass


if __name__ == '__main__':
    # Test the integration
    result = generate_and_evaluate('linkedin', 'Test input', 'fake-api-key')
    
    print("API Response:")
    print(f"Content: {result['content']}")
    print(f"Quality Score: {result['quality']['score']}/100")
    print(f"Grade: {result['quality']['grade']}")
    print(f"Passed: {result['quality']['passed']}")
    
    if result['quality']['issues']:
        print("\nIssues to fix:")
        for issue in result['quality']['issues']:
            print(f"  - {issue['criterion']}: {issue['message']}")
