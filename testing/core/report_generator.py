"""
HTML report generator for evaluation results.
Creates visual, easy-to-read reports with color-coded results.
"""

def generate_html_report(results_data, output_file='evals/report.html'):
    """Generate an HTML report from evaluation results"""
    
    timestamp = results_data.get('timestamp', 'Unknown')
    total_tests = results_data.get('total_tests', 0)
    passed_tests = results_data.get('passed_tests', 0)
    results = results_data.get('results', [])
    
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Evaluation Report - {timestamp}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}
        
        .header h1 {{
            color: #2d3748;
            margin-bottom: 10px;
        }}
        
        .header .timestamp {{
            color: #718096;
            font-size: 14px;
        }}
        
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        
        .summary-card {{
            background: #f7fafc;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        
        .summary-card h3 {{
            color: #4a5568;
            font-size: 14px;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .summary-card .value {{
            color: #2d3748;
            font-size: 32px;
            font-weight: bold;
        }}
        
        .test-card {{
            background: white;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        
        .test-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.15);
        }}
        
        .test-card.passed {{
            border-left: 5px solid #48bb78;
        }}
        
        .test-card.failed {{
            border-left: 5px solid #f56565;
        }}
        
        .test-header {{
            display: flex;
            justify-content: space-between;
            align-items: start;
            margin-bottom: 15px;
        }}
        
        .test-title {{
            flex: 1;
        }}
        
        .test-title h2 {{
            color: #2d3748;
            font-size: 20px;
            margin-bottom: 5px;
        }}
        
        .test-title .platform {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            text-transform: uppercase;
            font-weight: 600;
            margin-right: 10px;
        }}
        
        .test-title .description {{
            color: #718096;
            font-size: 14px;
        }}
        
        .status-badge {{
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 14px;
        }}
        
        .status-badge.passed {{
            background: #c6f6d5;
            color: #22543d;
        }}
        
        .status-badge.failed {{
            background: #fed7d7;
            color: #742a2a;
        }}
        
        .overall-score {{
            background: #f7fafc;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        
        .score-label {{
            color: #4a5568;
            font-weight: 600;
        }}
        
        .score-value {{
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
        }}
        
        .criteria-grid {{
            display: grid;
            gap: 15px;
            margin-top: 20px;
        }}
        
        .criterion {{
            background: #f7fafc;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #cbd5e0;
        }}
        
        .criterion.passed {{
            border-left-color: #48bb78;
            background: #f0fff4;
        }}
        
        .criterion.failed {{
            border-left-color: #f56565;
            background: #fff5f5;
        }}
        
        .criterion-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        
        .criterion-name {{
            font-weight: 600;
            color: #2d3748;
            text-transform: capitalize;
        }}
        
        .criterion-score {{
            font-size: 18px;
            font-weight: bold;
        }}
        
        .criterion.passed .criterion-score {{
            color: #22543d;
        }}
        
        .criterion.failed .criterion-score {{
            color: #742a2a;
        }}
        
        .criterion-message {{
            color: #4a5568;
            font-size: 14px;
            margin-bottom: 8px;
        }}
        
        .criterion-details {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #e2e8f0;
        }}
        
        .detail-item {{
            font-size: 13px;
        }}
        
        .detail-label {{
            color: #718096;
            font-weight: 500;
        }}
        
        .detail-value {{
            color: #2d3748;
            font-weight: 600;
        }}
        
        .suggestion {{
            background: #edf2f7;
            padding: 12px;
            border-radius: 6px;
            margin-top: 10px;
            font-size: 13px;
            color: #2d3748;
            border-left: 3px solid #667eea;
        }}
        
        .suggestion::before {{
            content: "💡 ";
        }}
        
        .generated-content {{
            background: #f7fafc;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            border: 1px solid #e2e8f0;
        }}
        
        .generated-content h4 {{
            color: #4a5568;
            font-size: 14px;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .generated-content pre {{
            white-space: pre-wrap;
            word-wrap: break-word;
            color: #2d3748;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.6;
        }}
        
        .progress-bar {{
            width: 100%;
            height: 8px;
            background: #e2e8f0;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 8px;
        }}
        
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #48bb78, #38a169);
            transition: width 0.3s ease;
        }}
        
        .progress-fill.low {{
            background: linear-gradient(90deg, #f56565, #e53e3e);
        }}
        
        .progress-fill.medium {{
            background: linear-gradient(90deg, #ed8936, #dd6b20);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Evaluation Report</h1>
            <p class="timestamp">Generated: {timestamp}</p>
            
            <div class="summary">
                <div class="summary-card">
                    <h3>Total Tests</h3>
                    <div class="value">{total_tests}</div>
                </div>
                <div class="summary-card">
                    <h3>Passed</h3>
                    <div class="value" style="color: #48bb78;">{passed_tests}</div>
                </div>
                <div class="summary-card">
                    <h3>Failed</h3>
                    <div class="value" style="color: #f56565;">{total_tests - passed_tests}</div>
                </div>
                <div class="summary-card">
                    <h3>Success Rate</h3>
                    <div class="value" style="color: {'#48bb78' if success_rate >= 70 else '#ed8936' if success_rate >= 40 else '#f56565'};">{success_rate:.1f}%</div>
                </div>
            </div>
        </div>
"""
    
    # Add test cards
    for result in results:
        test_id = result.get('test_id', 'Unknown')
        platform = result.get('platform', 'unknown')
        description = result.get('description', '')
        status = result.get('status', 'UNKNOWN')
        passed_criteria = result.get('passed_criteria', 0)
        total_criteria = result.get('total_criteria', 0)
        criteria_results = result.get('criteria_results', [])
        generated_content = result.get('generated_content', '')
        
        # Calculate overall score
        scores = [c.get('score', 0) for c in criteria_results if c.get('score') is not None]
        overall_score = sum(scores) / len(scores) if scores else 0
        
        status_class = 'passed' if status == 'PASSED' else 'failed'
        
        html += f"""
        <div class="test-card {status_class}">
            <div class="test-header">
                <div class="test-title">
                    <h2>{test_id}</h2>
                    <div>
                        <span class="platform">{platform}</span>
                        <span class="description">{description}</span>
                    </div>
                </div>
                <span class="status-badge {status_class}">{status}</span>
            </div>
            
            <div class="overall-score">
                <span class="score-label">Overall Score</span>
                <span class="score-value">{overall_score:.0f}/100</span>
            </div>
            <div class="progress-bar">
                <div class="progress-fill {'low' if overall_score < 50 else 'medium' if overall_score < 75 else ''}" style="width: {overall_score}%"></div>
            </div>
            
            <div class="criteria-grid">
"""
        
        # Add criteria
        for criterion in criteria_results:
            crit_name = criterion.get('criterion', 'Unknown')
            crit_passed = criterion.get('passed', False)
            crit_message = criterion.get('message', '')
            crit_score = criterion.get('score')
            crit_suggestion = criterion.get('suggestion', '')
            crit_actual = criterion.get('actual', '')
            crit_expected = criterion.get('expected', '')
            
            crit_class = 'passed' if crit_passed else 'failed'
            score_display = f"{crit_score:.0f}/100" if crit_score is not None else "N/A"
            
            html += f"""
                <div class="criterion {crit_class}">
                    <div class="criterion-header">
                        <span class="criterion-name">{crit_name}</span>
                        <span class="criterion-score">{score_display}</span>
                    </div>
                    <div class="criterion-message">{crit_message}</div>
"""
            
            if crit_actual or crit_expected:
                html += """
                    <div class="criterion-details">
"""
                if crit_expected:
                    html += f"""
                        <div class="detail-item">
                            <div class="detail-label">Expected</div>
                            <div class="detail-value">{crit_expected}</div>
                        </div>
"""
                if crit_actual:
                    html += f"""
                        <div class="detail-item">
                            <div class="detail-label">Actual</div>
                            <div class="detail-value">{crit_actual}</div>
                        </div>
"""
                html += """
                    </div>
"""
            
            if crit_suggestion:
                html += f"""
                    <div class="suggestion">{crit_suggestion}</div>
"""
            
            html += """
                </div>
"""
        
        html += """
            </div>
"""
        
        # Add generated content
        if generated_content:
            html += f"""
            <div class="generated-content">
                <h4>Generated Content</h4>
                <pre>{generated_content}</pre>
            </div>
"""
        
        html += """
        </div>
"""
    
    html += """
    </div>
</body>
</html>
"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return output_file
