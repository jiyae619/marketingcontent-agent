"""
Evaluation functions for testing generated marketing content quality.
Each evaluator checks specific criteria from the content strategy.
"""

import re
from typing import Dict, List, Tuple


class ContentEvaluator:
    """Base class for content evaluation"""
    
    def __init__(self, platform: str):
        self.platform = platform
        self.results = []
    
    def add_result(self, criterion: str, passed: bool, message: str, score: float = None):
        """Add an evaluation result"""
        self.results.append({
            'criterion': criterion,
            'passed': passed,
            'message': message,
            'score': score
        })
    
    def get_results(self) -> List[Dict]:
        """Get all evaluation results"""
        return self.results


class LinkedInEvaluator(ContentEvaluator):
    """Evaluator for LinkedIn content"""
    
    def __init__(self):
        super().__init__('linkedin')
    
    def evaluate(self, content: str) -> List[Dict]:
        """Run all LinkedIn evaluations"""
        self.check_length(content)
        self.check_tone(content)
        self.check_format(content)
        return self.get_results()
    
    def check_length(self, content: str):
        """LinkedIn should be around 1000 characters"""
        char_count = len(content)
        target_min = 900
        target_max = 1100
        optimal = 1000
        
        # Calculate score (0-100)
        if target_min <= char_count <= target_max:
            score = 100
            passed = True
            message = f"✓ Character count ({char_count}) is within optimal range ({target_min}-{target_max})"
            suggestion = "Perfect length for LinkedIn engagement!"
        elif char_count < target_min:
            # Too short - score based on how far from target
            gap = target_min - char_count
            gap_percentage = (gap / target_min) * 100
            score = max(0, 100 - gap_percentage)
            passed = False
            message = f"✗ Too short: {char_count} characters (minimum: {target_min})"
            suggestion = f"Add {gap} more characters ({gap_percentage:.0f}% too short). Consider expanding on key points, adding examples, or including more detail."
        else:
            # Too long - score based on how far over
            gap = char_count - target_max
            gap_percentage = (gap / target_max) * 100
            score = max(0, 100 - gap_percentage)
            passed = False
            message = f"✗ Too long: {char_count} characters (maximum: {target_max})"
            suggestion = f"Remove {gap} characters ({gap_percentage:.0f}% too long). Consider being more concise or removing less critical details."
        
        self.add_result('length', passed, message, score)
        self.results[-1]['suggestion'] = suggestion
        self.results[-1]['actual'] = char_count
        self.results[-1]['expected'] = f"{target_min}-{target_max} characters"
    
    def check_tone(self, content: str):
        """Check for professional tone indicators"""
        professional_indicators = [
            'insight', 'strategy', 'professional', 'expertise', 'industry',
            'leadership', 'innovation', 'growth', 'development', 'success'
        ]
        
        content_lower = content.lower()
        found_indicators = [ind for ind in professional_indicators if ind in content_lower]
        
        # Score based on number of indicators
        num_found = len(found_indicators)
        if num_found >= 5:
            score = 100
        elif num_found >= 3:
            score = 75
        elif num_found >= 2:
            score = 50
        else:
            score = 25
        
        passed = num_found >= 2
        
        if passed:
            message = f"✓ Professional tone detected ({num_found} indicators: {', '.join(found_indicators[:3])})"
            suggestion = "Excellent professional tone!" if num_found >= 4 else "Good professional tone. Consider adding more industry-specific terms."
        else:
            message = f"✗ Lacks professional tone (found only {num_found} indicators)"
            suggestion = f"Add more professional language. Try including words like: {', '.join(professional_indicators[:5])}"
        
        self.add_result('tone', passed, message, score)
        self.results[-1]['suggestion'] = suggestion
        self.results[-1]['actual'] = f"{num_found} professional indicators"
        self.results[-1]['expected'] = "At least 2 professional indicators"
    
    def check_format(self, content: str):
        """Check formatting requirements"""
        # Check for paragraph structure (multiple lines)
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        num_paragraphs = len(paragraphs)
        
        # Score based on paragraph count
        if num_paragraphs >= 3:
            score = 100
            passed = True
            message = f"✓ Excellent paragraph structure ({num_paragraphs} paragraphs)"
            suggestion = "Great formatting with clear paragraph breaks!"
        elif num_paragraphs >= 2:
            score = 75
            passed = True
            message = f"✓ Has proper paragraph structure ({num_paragraphs} paragraphs)"
            suggestion = "Good structure. Consider adding one more paragraph for better readability."
        else:
            score = 30
            passed = False
            message = f"✗ Lacks paragraph structure ({num_paragraphs} paragraph)"
            suggestion = "Break content into multiple paragraphs using line breaks for better readability."
        
        self.add_result('format', passed, message, score)
        self.results[-1]['suggestion'] = suggestion
        self.results[-1]['actual'] = f"{num_paragraphs} paragraphs"
        self.results[-1]['expected'] = "At least 2-3 paragraphs"


class InstagramEvaluator(ContentEvaluator):
    """Evaluator for Instagram content"""
    
    def __init__(self):
        super().__init__('instagram')
    
    def evaluate(self, content: str) -> List[Dict]:
        """Run all Instagram evaluations"""
        self.check_length(content)
        self.check_tone(content)
        self.check_emojis(content)
        return self.get_results()
    
    def check_length(self, content: str):
        """Instagram should be 125-150 words"""
        words = content.strip().split()
        word_count = len(words)
        target_min = 125
        target_max = 150
        
        # Calculate score
        if target_min <= word_count <= target_max:
            score = 100
            passed = True
            message = f"✓ Word count ({word_count}) is within optimal range ({target_min}-{target_max})"
            suggestion = "Perfect length for Instagram engagement!"
        elif word_count < target_min:
            gap = target_min - word_count
            gap_percentage = (gap / target_min) * 100
            score = max(0, 100 - gap_percentage)
            passed = False
            message = f"✗ Too short: {word_count} words (minimum: {target_min})"
            suggestion = f"Add {gap} more words ({gap_percentage:.0f}% too short). Expand with more details or examples."
        else:
            gap = word_count - target_max
            gap_percentage = (gap / target_max) * 100
            score = max(0, 100 - gap_percentage)
            passed = False
            message = f"✗ Too long: {word_count} words (maximum: {target_max})"
            suggestion = f"Remove {gap} words ({gap_percentage:.0f}% too long). Be more concise."
        
        self.add_result('length', passed, message, score)
        self.results[-1]['suggestion'] = suggestion
        self.results[-1]['actual'] = word_count
        self.results[-1]['expected'] = f"{target_min}-{target_max} words"
    
    def check_tone(self, content: str):
        """Check for casual, engaging tone"""
        casual_indicators = [
            '!', '?', 'you', 'your', 'we', 'our', 'let\'s', 'check out',
            'amazing', 'awesome', 'love', 'excited'
        ]
        
        content_lower = content.lower()
        found_indicators = [ind for ind in casual_indicators if ind in content_lower]
        
        # At least 3 casual/engaging indicators expected
        passed = len(found_indicators) >= 3
        
        if passed:
            message = f"✓ Casual/engaging tone detected ({len(found_indicators)} indicators)"
        else:
            message = f"✗ Tone too formal (found only {len(found_indicators)} casual indicators)"
        
        self.add_result('tone', passed, message)
    
    def check_emojis(self, content: str):
        """Instagram should have emojis"""
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+", 
            flags=re.UNICODE
        )
        
        emojis = emoji_pattern.findall(content)
        has_emojis = len(emojis) > 0
        
        message = f"✓ Contains {len(emojis)} emoji(s)" if has_emojis else "✗ No emojis found"
        self.add_result('emojis', has_emojis, message)


class CircleEvaluator(ContentEvaluator):
    """Evaluator for CIRCLE content"""
    
    def __init__(self):
        super().__init__('circle')
    
    def evaluate(self, content: str) -> List[Dict]:
        """Run all CIRCLE evaluations"""
        self.check_length(content)
        self.check_structure(content)
        self.check_formatting(content)
        return self.get_results()
    
    def check_length(self, content: str):
        """CIRCLE should be 500-800 words"""
        words = content.strip().split()
        word_count = len(words)
        target_min = 500
        target_max = 800
        
        # Calculate score
        if target_min <= word_count <= target_max:
            score = 100
            passed = True
            message = f"✓ Word count ({word_count}) is within optimal range ({target_min}-{target_max})"
            suggestion = "Perfect length for CIRCLE community posts!"
        elif word_count < target_min:
            gap = target_min - word_count
            gap_percentage = (gap / target_min) * 100
            score = max(0, 100 - gap_percentage)
            passed = False
            message = f"✗ Too short: {word_count} words (minimum: {target_min})"
            suggestion = f"Add {gap} more words ({gap_percentage:.0f}% too short). Include more details, examples, or expand sections."
        else:
            gap = word_count - target_max
            gap_percentage = (gap / target_max) * 100
            score = max(0, 100 - gap_percentage)
            passed = False
            message = f"✗ Too long: {word_count} words (maximum: {target_max})"
            suggestion = f"Remove {gap} words ({gap_percentage:.0f}% too long). Focus on key information."
        
        self.add_result('length', passed, message, score)
        self.results[-1]['suggestion'] = suggestion
        self.results[-1]['actual'] = word_count
        self.results[-1]['expected'] = f"{target_min}-{target_max} words"
    
    def check_structure(self, content: str):
        """Check for required sections"""
        # Look for title pattern [PKNIC X ...]
        has_title = bool(re.search(r'\[PKNIC [xX×]', content))
        
        # Look for section headers (##)
        has_headers = '##' in content or re.search(r'^[A-Z][^.!?]*:$', content, re.MULTILINE)
        
        # Check for community engagement elements
        has_engagement = any(word in content.lower() for word in ['question', 'community', 'join', 'participate', 'share'])
        
        all_passed = has_title and has_headers and has_engagement
        
        details = []
        if has_title:
            details.append("title ✓")
        else:
            details.append("title ✗")
        if has_headers:
            details.append("headers ✓")
        else:
            details.append("headers ✗")
        if has_engagement:
            details.append("engagement ✓")
        else:
            details.append("engagement ✗")
        
        message = f"Structure check: {', '.join(details)}"
        self.add_result('structure', all_passed, message)
    
    def check_formatting(self, content: str):
        """Check for bullet points and clear formatting"""
        has_bullets = bool(re.search(r'[•\-\*]\s', content))
        has_emojis = bool(re.search(r'[\U0001F300-\U0001F9FF]', content))
        
        passed = has_bullets or has_emojis
        
        if has_bullets and has_emojis:
            message = "✓ Has bullet points and emojis"
        elif has_bullets:
            message = "✓ Has bullet points"
        elif has_emojis:
            message = "✓ Has emojis for formatting"
        else:
            message = "✗ Missing bullet points or formatting elements"
        
        self.add_result('formatting', passed, message)


class KakaotalkEvaluator(ContentEvaluator):
    """Evaluator for Kakaotalk content"""
    
    def __init__(self):
        super().__init__('kakaotalk')
    
    def evaluate(self, content: str) -> List[Dict]:
        """Run all Kakaotalk evaluations"""
        self.check_length(content)
        self.check_tone(content)
        return self.get_results()
    
    def check_length(self, content: str):
        """Kakaotalk should be maximum 3 sentences"""
        # Split by sentence-ending punctuation
        sentences = re.split(r'[.!?]+', content)
        sentences = [s.strip() for s in sentences if s.strip()]
        sentence_count = len(sentences)
        target_max = 3
        
        # Calculate score
        if sentence_count <= target_max:
            score = 100 if sentence_count >= 2 else 75
            passed = True
            message = f"✓ Sentence count ({sentence_count}) is within limit (max {target_max})"
            suggestion = "Perfect brevity for Kakaotalk!" if sentence_count == 3 else "Good length. Consider using all 3 sentences for maximum impact."
        else:
            gap = sentence_count - target_max
            score = max(0, 100 - (gap * 30))
            passed = False
            message = f"✗ Too many sentences: {sentence_count} (maximum: {target_max})"
            suggestion = f"Remove {gap} sentence(s). Combine ideas or remove less critical information."
        
        self.add_result('length', passed, message, score)
        self.results[-1]['suggestion'] = suggestion
        self.results[-1]['actual'] = sentence_count
        self.results[-1]['expected'] = f"Maximum {target_max} sentences"
    
    def check_tone(self, content: str):
        """Check for conversational, direct tone"""
        direct_indicators = [
            '!', '?', 'you', 'your', 'check', 'join', 'register',
            'don\'t miss', 'hurry', 'now', 'today'
        ]
        
        content_lower = content.lower()
        found_indicators = [ind for ind in direct_indicators if ind in content_lower]
        
        # At least 2 direct/actionable indicators expected
        passed = len(found_indicators) >= 2
        
        if passed:
            message = f"✓ Direct/conversational tone detected ({len(found_indicators)} indicators)"
        else:
            message = f"✗ Lacks direct tone (found only {len(found_indicators)} indicators)"
        
        self.add_result('tone', passed, message)


def get_evaluator(platform: str) -> ContentEvaluator:
    """Factory function to get the appropriate evaluator"""
    evaluators = {
        'linkedin': LinkedInEvaluator,
        'instagram': InstagramEvaluator,
        'circle': CircleEvaluator,
        'kakaotalk': KakaotalkEvaluator
    }
    
    evaluator_class = evaluators.get(platform.lower())
    if not evaluator_class:
        raise ValueError(f"Unknown platform: {platform}")
    
    return evaluator_class()
