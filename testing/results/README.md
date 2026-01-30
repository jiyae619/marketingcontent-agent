# Test Results

This folder contains auto-generated test outputs from the evaluation system.

## Files

### `results_TIMESTAMP.json`
Machine-readable test results in JSON format containing:
- Test metadata (timestamp, total/passed counts)
- Individual test results with scores
- Detailed criterion evaluations
- Generated content for each test

### `report_TIMESTAMP.html`
Human-friendly HTML reports with visual formatting:
- Summary dashboard
- Platform-specific breakdowns
- Color-coded pass/fail indicators
- Detailed suggestions for improvements

## Usage

**View HTML reports:**
```bash
open testing/results/report_*.html
```

**Parse JSON results programmatically:**
```python
import json

with open('testing/results/results_20260130_120000.json') as f:
    data = json.load(f)
    
print(f"Success rate: {data['passed_tests']}/{data['total_tests']}")
```

## File Naming

Files are timestamped with format: `YYYYMMDD_HHMMSS`

Example: `results_20260130_143052.json` = January 30, 2026 at 2:30:52 PM

## Cleanup

Old test results can be safely deleted. The system generates new files on each run.

**Keep recent results** for tracking improvements over time.

## Gitignore

This folder is gitignored to avoid committing test outputs to version control. Results are local-only.
