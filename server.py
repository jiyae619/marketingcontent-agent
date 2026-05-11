from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import json
import urllib.request
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class CORSRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS for all origins
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, x-api-key')
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()
    
    def do_GET(self):
        # Handle /api/prompts/<platform> endpoint
        if self.path.startswith('/api/prompts/'):
            platform = self.path.split('/')[-1]
            
            # Validate platform
            valid_platforms = ['linkedin', 'instagram', 'circle', 'kakaotalk']
            if platform not in valid_platforms:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(json.dumps({
                    'error': f'Invalid platform. Must be one of: {", ".join(valid_platforms)}'
                }).encode())
                return
            
            # Load prompt from markdown file
            try:
                prompt = self.load_prompt_from_md(platform)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'platform': platform,
                    'prompt': prompt
                }).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({
                    'error': f'Failed to load prompt: {str(e)}'
                }).encode())
            return
        
        # Default: serve static files
        return super().do_GET()
    
    def load_prompt_from_md(self, platform):
        """Extract AI Prompt section from markdown file"""
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
        
        # Find the start of the prompt content (after the header)
        prompt_start = start_idx + len(start_marker)
        
        # Find the next "##" header
        next_header_idx = content.find('\n##', prompt_start)
        
        if next_header_idx == -1:
            # No next header, take until end of file
            prompt_content = content[prompt_start:]
        else:
            prompt_content = content[prompt_start:next_header_idx]
        
        # Clean up the prompt (remove leading/trailing whitespace)
        prompt = prompt_content.strip()
        
        return prompt
    
    def do_POST(self):
        # Handle /api/gemini endpoint
        if self.path == '/api/gemini':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            # Get API key from environment variable first, fallback to request
            api_key = os.getenv('GEMINI_API_KEY') or data.get('api_key')
            if not api_key:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({
                    'error': 'API key required. Set GEMINI_API_KEY environment variable or provide api_key in request.'
                }).encode())
                return
            
            # Extract data for Gemini
            system_prompt = data.get('system', '')
            user_message = data.get('messages', [{}])[0].get('content', '')
            
            # Combine system and user for Gemini
            full_prompt = f"{system_prompt}\n\nUser content to transform:\n{user_message}"
            
            # Forward request to Gemini API
            try:
                gemini_url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}'
                
                gemini_payload = {
                    "contents": [{
                        "parts": [{
                            "text": full_prompt
                        }]
                    }]
                }
                
                req = urllib.request.Request(
                    gemini_url,
                    data=json.dumps(gemini_payload).encode('utf-8'),
                    headers={
                        'Content-Type': 'application/json'
                    }
                )
                
                with urllib.request.urlopen(req) as response:
                    response_data = json.loads(response.read().decode('utf-8'))
                    
                    # Convert Gemini response to match our expected format
                    if 'candidates' in response_data and len(response_data['candidates']) > 0:
                        text = response_data['candidates'][0]['content']['parts'][0]['text']
                        result = {
                            'content': [{'text': text}]
                        }
                    else:
                        result = {'error': 'No response from Gemini'}
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())
            
            except urllib.error.HTTPError as e:
                error_data = e.read().decode('utf-8')
                self.send_response(e.code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(error_data.encode())
            
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            # For other requests, use default handler
            super().do_POST()

if __name__ == '__main__':
    PORT = int(os.getenv('API_PORT', '8081'))
    server = ThreadingHTTPServer(('localhost', PORT), CORSRequestHandler)
    print(f'Server running on http://localhost:{PORT}')
    print('Press Ctrl+C to stop')
    server.serve_forever()
