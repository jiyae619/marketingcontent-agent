# Test Data

This folder contains input test cases for the evaluation system.

## Files

### `test_cases.json`
Predefined test scenarios used by `eval_runner.py` to validate AI-generated content quality.

## Format

```json
{
  "test_cases": [
    {
      "id": "unique_test_id",
      "platform": "linkedin|instagram|circle|kakaotalk",
      "description": "Brief description of what this tests",
      "input": "The content to transform..."
    }
  ]
}
```

## Adding Test Cases

1. Open `test_cases.json`
2. Add a new object to the `test_cases` array
3. Provide unique `id`, target `platform`, `description`, and `input` text
4. Run `python3 testing/core/eval_runner.py` to test

## Best Practices

- **Use real examples** from actual marketing content
- **Cover edge cases** (very short, very long, multilingual)
- **Test each platform** with multiple content types
- **Update regularly** as requirements change
- **Include Korean and English** examples for language matching tests

## Example Test Cases

- Event announcements
- Product launches
- Community updates
- Educational content
- Promotional offers
