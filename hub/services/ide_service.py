"""
IDE Service - Handles IDE functionality including code execution, file management, and AI assistance
"""

import os
import json
import subprocess
import tempfile
import shutil
import zipfile
import io
import base64
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import timedelta
from django.utils import timezone
from django.conf import settings


class IDEService:
    """Service for IDE operations"""
    
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
    
    def create_project_structure(self, project_type: str) -> Dict[str, Any]:
        """Create initial project structure based on project type"""
        
        structures = {
            'python': {
                'files': [
                    {'name': 'main.py', 'content': '# Main Python file\nprint("Hello, World!")\n'},
                    {'name': 'README.md', 'content': '# Python Project\n\nDescription of your project.\n'},
                    {'name': 'requirements.txt', 'content': '# Add your dependencies here\n'},
                ],
                'folders': ['src', 'tests']
            },
            'javascript': {
                'files': [
                    {'name': 'index.js', 'content': '// Main JavaScript file\nconsole.log("Hello, World!");\n'},
                    {'name': 'package.json', 'content': json.dumps({
                        'name': 'project',
                        'version': '1.0.0',
                        'main': 'index.js',
                        'scripts': {'start': 'node index.js'}
                    }, indent=2)},
                    {'name': 'README.md', 'content': '# JavaScript Project\n\nDescription of your project.\n'},
                ],
                'folders': ['src']
            },
            'html': {
                'files': [
                    {'name': 'index.html', 'content': '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Project</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <h1>Hello, World!</h1>
    <script src="script.js"></script>
</body>
</html>
'''},
                    {'name': 'style.css', 'content': '/* Add your styles here */\nbody {\n    font-family: Arial, sans-serif;\n    margin: 0;\n    padding: 20px;\n}\n'},
                    {'name': 'script.js', 'content': '// Add your JavaScript here\nconsole.log("Page loaded!");\n'},
                ],
                'folders': []
            },
            'react': {
                'files': [
                    {'name': 'App.jsx', 'content': '''import React from 'react';

function App() {
    return (
        <div className="App">
            <h1>Hello, React!</h1>
        </div>
    );
}

export default App;
'''},
                    {'name': 'index.jsx', 'content': '''import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
'''},
                    {'name': 'package.json', 'content': json.dumps({
                        'name': 'react-project',
                        'version': '1.0.0',
                        'dependencies': {
                            'react': '^18.0.0',
                            'react-dom': '^18.0.0'
                        }
                    }, indent=2)},
                ],
                'folders': ['src', 'public']
            },
            'django': {
                'files': [
                    {'name': 'manage.py', 'content': '''#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
'''},
                    {'name': 'requirements.txt', 'content': 'Django>=4.2\n'},
                    {'name': 'README.md', 'content': '# Django Project\n\nDescription of your project.\n'},
                ],
                'folders': ['project', 'app']
            },
        }
        
        return structures.get(project_type, structures['python'])
    
    def execute_code(self, code: str, language: str = 'python', timeout: int = 30, 
                     environment: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Execute code in a sandboxed environment
        
        Args:
            code: Code to execute
            language: Programming language
            timeout: Timeout in seconds
            environment: Environment variables
            
        Returns:
            Dictionary with execution results
        """
        
        start_time = time.time()
        result = {
            'status': 'pending',
            'stdout': '',
            'stderr': '',
            'exit_code': None,
            'execution_time': 0,
            'error': None
        }
        
        try:
            if language == 'python':
                result = self._execute_python(code, timeout, environment)
            elif language in ['javascript', 'js']:
                result = self._execute_javascript(code, timeout, environment)
            elif language == 'html':
                result = self._execute_html(code)
            else:
                result['status'] = 'error'
                result['stderr'] = f"Unsupported language: {language}"
                result['exit_code'] = 1
            
            result['execution_time'] = time.time() - start_time
            
        except subprocess.TimeoutExpired:
            result['status'] = 'timeout'
            result['stderr'] = f"Execution timed out after {timeout} seconds"
            result['exit_code'] = -1
            result['execution_time'] = timeout
        except Exception as e:
            result['status'] = 'error'
            result['stderr'] = str(e)
            result['exit_code'] = 1
            result['execution_time'] = time.time() - start_time
        
        return result
    
    def _execute_python(self, code: str, timeout: int = 30, 
                       environment: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Execute Python code"""
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            # Prepare environment
            env = os.environ.copy()
            if environment:
                env.update(environment)
            
            # Execute code
            process = subprocess.run(
                ['python', temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )
            
            return {
                'status': 'completed' if process.returncode == 0 else 'error',
                'stdout': process.stdout,
                'stderr': process.stderr,
                'exit_code': process.returncode,
                'execution_time': 0  # Will be set by caller
            }
        finally:
            # Clean up
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def _execute_javascript(self, code: str, timeout: int = 30,
                           environment: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Execute JavaScript code using Node.js"""
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            # Prepare environment
            env = os.environ.copy()
            if environment:
                env.update(environment)
            
            # Execute code with Node.js
            process = subprocess.run(
                ['node', temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )
            
            return {
                'status': 'completed' if process.returncode == 0 else 'error',
                'stdout': process.stdout,
                'stderr': process.stderr,
                'exit_code': process.returncode,
                'execution_time': 0
            }
        except FileNotFoundError:
            return {
                'status': 'error',
                'stdout': '',
                'stderr': 'Node.js is not installed or not in PATH',
                'exit_code': 1,
                'execution_time': 0
            }
        finally:
            # Clean up
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def _execute_html(self, code: str) -> Dict[str, Any]:
        """
        For HTML, we don't execute it server-side.
        Return the HTML for client-side rendering.
        """
        return {
            'status': 'completed',
            'stdout': 'HTML ready for preview',
            'stderr': '',
            'exit_code': 0,
            'html_content': code,
            'execution_time': 0
        }
    
    def export_project(self, project, export_format: str = 'zip') -> Dict[str, Any]:
        """
        Export project files
        
        Args:
            project: IDEProject instance
            export_format: 'zip' or 'tar'
            
        Returns:
            Dictionary with export data
        """
        
        result = {
            'status': 'pending',
            'file_data': None,
            'file_size': 0,
            'error': None
        }
        
        try:
            # Create temporary directory for project
            temp_project_dir = tempfile.mkdtemp()
            
            try:
                # Write all files
                for code_file in project.files.all():
                    file_path = os.path.join(temp_project_dir, code_file.path)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(code_file.content)
                
                # Create archive
                if export_format == 'zip':
                    archive_buffer = io.BytesIO()
                    with zipfile.ZipFile(archive_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(temp_project_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, temp_project_dir)
                                zipf.write(file_path, arcname)
                    
                    archive_data = archive_buffer.getvalue()
                    result['file_data'] = base64.b64encode(archive_data).decode('utf-8')
                    result['file_size'] = len(archive_data)
                    result['status'] = 'completed'
                else:
                    result['status'] = 'error'
                    result['error'] = f"Unsupported export format: {export_format}"
                
            finally:
                # Clean up temporary directory
                shutil.rmtree(temp_project_dir, ignore_errors=True)
        
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
        
        return result
    
    def analyze_code(self, code: str, language: str = 'python') -> Dict[str, Any]:
        """
        Analyze code for errors, complexity, etc.
        
        Args:
            code: Code to analyze
            language: Programming language
            
        Returns:
            Analysis results
        """
        
        result = {
            'errors': [],
            'warnings': [],
            'suggestions': [],
            'metrics': {
                'lines': 0,
                'complexity': 0
            }
        }
        
        try:
            # Count lines
            lines = code.split('\n')
            result['metrics']['lines'] = len(lines)
            
            if language == 'python':
                # Basic Python syntax check
                try:
                    compile(code, '<string>', 'exec')
                except SyntaxError as e:
                    result['errors'].append({
                        'line': e.lineno,
                        'message': e.msg,
                        'type': 'SyntaxError'
                    })
            
            # Add basic code quality suggestions
            if len(lines) > 100:
                result['suggestions'].append({
                    'message': 'Consider breaking this file into smaller modules',
                    'type': 'complexity'
                })
        
        except Exception as e:
            result['errors'].append({
                'message': str(e),
                'type': 'AnalysisError'
            })
        
        return result
    
    def format_code(self, code: str, language: str = 'python') -> str:
        """
        Format code according to language standards
        
        Args:
            code: Code to format
            language: Programming language
            
        Returns:
            Formatted code
        """
        
        # For now, return as-is. In production, use formatters like:
        # - black for Python
        # - prettier for JavaScript
        # - etc.
        
        return code
    
    def get_file_tree(self, project) -> List[Dict[str, Any]]:
        """
        Generate file tree structure for a project
        
        Args:
            project: IDEProject instance
            
        Returns:
            List of file tree nodes
        """
        
        files = project.files.all().order_by('path')
        tree = []
        
        # Build directory structure
        dirs_created = set()
        
        for file in files:
            parts = file.path.split('/')
            
            # Create directory nodes
            for i in range(len(parts) - 1):
                dir_path = '/'.join(parts[:i+1])
                if dir_path not in dirs_created:
                    tree.append({
                        'type': 'directory',
                        'name': parts[i],
                        'path': dir_path,
                        'children': []
                    })
                    dirs_created.add(dir_path)
            
            # Add file node
            tree.append({
                'type': 'file',
                'name': file.name,
                'path': file.path,
                'file_type': file.file_type,
                'size': file.size_bytes,
                'id': file.id
            })
        
        return tree


class AICodeAssistant:
    """AI assistant for code generation, explanation, and debugging"""
    
    def __init__(self, ai_service=None):
        """
        Initialize AI assistant
        
        Args:
            ai_service: AI service to use (OpenRouter, Gemini, etc.)
        """
        self.ai_service = ai_service
    
    def generate_code(self, prompt: str, language: str = 'python', 
                     context: Optional[str] = None, code_type: str = 'general') -> Dict[str, Any]:
        """
        Generate code based on prompt with specialized web development features
        
        Args:
            prompt: Code generation prompt
            language: Target programming language
            context: Optional context (existing code, project files, etc.)
            code_type: Type of code (component, page, api, template, etc.)
            
        Returns:
            Generated code and metadata
        """
        
        # Enhanced prompts for web development
        web_prompts = {
            'html': """You are an expert web developer. Generate semantic, accessible HTML5 code.
Use modern HTML best practices, proper structure, and include meta tags for SEO.""",
            
            'css': """You are a CSS expert. Generate modern CSS with flexbox/grid layouts, 
responsive design, and clean styling. Use CSS variables and BEM methodology.""",
            
            'javascript': """You are a JavaScript expert. Generate modern ES6+ code with 
proper error handling, clean functions, and performance optimization. Use async/await where appropriate.""",
            
            'react': """You are a React expert. Generate functional components with hooks,
proper prop types, clean JSX, and follow React best practices. Include error boundaries.""",
            
            'vue': """You are a Vue.js expert. Generate Vue 3 composition API components
with reactive data, computed properties, and lifecycle hooks.""",
            
            'typescript': """You are a TypeScript expert. Generate type-safe code with
proper interfaces, generics, and advanced TypeScript features."""
        }
        
        system_prompt = web_prompts.get(language, f"""You are an expert {language} programmer. 
Generate clean, efficient, well-documented code based on the user's request.""")
        
        # Add context-aware enhancements
        if context:
            system_prompt += f"\n\nExisting code context:\n{context}"
            
        # Add specialized instructions for code types
        if code_type == 'component':
            system_prompt += "\n\nGenerate a reusable, well-structured component with props and documentation."
        elif code_type == 'page':
            system_prompt += "\n\nGenerate a complete page layout with header, main content, and footer."
        elif code_type == 'api':
            system_prompt += "\n\nGenerate a RESTful API endpoint with proper validation and error handling."
        elif code_type == 'template':
            system_prompt += "\n\nGenerate a template/boilerplate with placeholder content and structure."
        
        # Use the AI service to generate code
        if self.ai_service:
            try:
                from ..services.openrouter import generate_response
                
                full_prompt = f"""{system_prompt}

User request: {prompt}

Requirements:
- Generate clean, production-ready {language} code
- Include comprehensive comments
- Follow modern best practices
- Ensure code is accessible and performant
- Add error handling where appropriate

Generate the code:"""
                
                response = generate_response(
                    prompt=full_prompt,
                    max_tokens=3000,  # Increased for complex components
                    model="gpt-4-1106-preview"  # Use advanced model for better code generation
                )
                
                generated_code = response.get('assistant_text', '')
                
                # Post-process the generated code
                processed_code = self._enhance_generated_code(generated_code, language, code_type)
                
                return {
                    'code': processed_code,
                    'model': response.get('model', 'unknown'),
                    'success': True,
                    'suggestions': self._get_code_suggestions(generated_code, language),
                    'dependencies': self._extract_dependencies(generated_code, language)
                }
            except Exception as e:
                return {
                    'code': f'# Error generating code: {str(e)}',
                    'error': str(e),
                    'success': False
                }
        
        # Enhanced fallback templates for web development
        return self._generate_enhanced_template(prompt, language, code_type)
    
    def _enhance_generated_code(self, code: str, language: str, code_type: str) -> str:
        """Post-process generated code for better quality"""
        
        if language == 'html' and code_type == 'page':
            # Ensure proper HTML structure
            if not '<!DOCTYPE html>' in code:
                code = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generated Page</title>
</head>
<body>
{code}
</body>
</html>"""
        
        elif language == 'css':
            # Add CSS reset and modern practices
            if not ':root' in code and not '--' in code:
                code = """:root {
    --primary-color: #007acc;
    --secondary-color: #6c757d;
    --background-color: #ffffff;
    --text-color: #333333;
    --border-radius: 8px;
    --box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

* {
    box-sizing: border-box;
}

""" + code
                
        elif language == 'javascript':
            # Add error handling wrapper if not present
            if not 'try' in code and not 'catch' in code:
                if 'function' in code or 'const' in code:
                    code = f"""// Error handling wrapper
try {{
{code}
}} catch (error) {{
    console.error('Error:', error);
}}"""
        
        return code
    
    def _get_code_suggestions(self, code: str, language: str) -> List[str]:
        """Generate improvement suggestions for code"""
        suggestions = []
        
        if language == 'html':
            if 'alt=' not in code and '<img' in code:
                suggestions.append("Add alt attributes to images for accessibility")
            if 'aria-' not in code:
                suggestions.append("Consider adding ARIA attributes for better accessibility")
                
        elif language == 'css':
            if '@media' not in code:
                suggestions.append("Consider adding responsive breakpoints")
            if 'transition' not in code and 'hover:' not in code:
                suggestions.append("Add hover transitions for better UX")
                
        elif language == 'javascript':
            if 'const' not in code and 'let' not in code:
                suggestions.append("Use const/let instead of var for better scope management")
            if 'addEventListener' in code and 'removeEventListener' not in code:
                suggestions.append("Consider cleanup with removeEventListener")
        
        return suggestions
    
    def _extract_dependencies(self, code: str, language: str) -> List[str]:
        """Extract dependencies from generated code"""
        dependencies = []
        
        if language == 'javascript' or language == 'typescript':
            # Extract import statements
            import re
            imports = re.findall(r'import.*from [\'\"](.*?)[\'\"]', code)
            dependencies.extend(imports)
            
            # Check for common libraries
            if 'axios' in code:
                dependencies.append('axios')
            if 'lodash' in code or '_.' in code:
                dependencies.append('lodash')
            if 'moment' in code:
                dependencies.append('moment')
                
        elif language == 'css':
            if '@import' in code:
                imports = re.findall(r'@import url\([\'\"](.*?)[\'\"]\)', code)
                dependencies.extend(imports)
        
        return list(set(dependencies))  # Remove duplicates
    
    def _generate_enhanced_template(self, prompt: str, language: str, code_type: str) -> Dict[str, Any]:
        """Generate enhanced templates for web development"""
        
        templates = {
            'html': {
                'page': f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Generated page for: {prompt}">
    <title>{prompt}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        header {{ background: #f8f9fa; padding: 20px 0; }}
        main {{ padding: 40px 0; }}
        footer {{ background: #333; color: white; text-align: center; padding: 20px 0; }}
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>{prompt}</h1>
        </div>
    </header>
    <main>
        <div class="container">
            <p>Your content here...</p>
        </div>
    </main>
    <footer>
        <div class="container">
            <p>&copy; 2025 Generated with IntelliHub IDE</p>
        </div>
    </footer>
</body>
</html>''',
                'component': f'''<div class="component">
    <h2>{prompt}</h2>
    <p>Component content here...</p>
</div>'''
            },
            
            'css': {
                'general': f'''/* Styles for: {prompt} */
:root {{
    --primary: #007acc;
    --secondary: #6c757d;
    --success: #28a745;
    --danger: #dc3545;
    --warning: #ffc107;
    --info: #17a2b8;
}}

* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    line-height: 1.6;
    color: #333;
}}

.container {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
}}

/* Add your styles here */
'''
            },
            
            'javascript': {
                'general': f'''// JavaScript for: {prompt}

class Component {{
    constructor(element) {{
        this.element = element;
        this.init();
    }}
    
    init() {{
        // Initialize component
        this.bindEvents();
    }}
    
    bindEvents() {{
        // Bind event listeners
    }}
    
    destroy() {{
        // Cleanup
    }}
}}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {{
    // Your code here
}});''',
                'component': f'''// {prompt} Component

export class {prompt.replace(' ', '')}Component {{
    constructor(options = {{}}) {{
        this.options = {{
            element: null,
            ...options
        }};
        
        if (this.options.element) {{
            this.init();
        }}
    }}
    
    init() {{
        this.bindEvents();
        this.render();
    }}
    
    bindEvents() {{
        // Event listeners
    }}
    
    render() {{
        // Render component
    }}
    
    destroy() {{
        // Cleanup
    }}
}}'''
            },
            
            'react': {
                'component': f'''import React, {{ useState, useEffect }} from 'react';

const {prompt.replace(' ', '')}Component = ({{ ...props }}) => {{
    const [state, setState] = useState(null);
    
    useEffect(() => {{
        // Component mount logic
    }}, []);
    
    return (
        <div className="{prompt.lower().replace(' ', '-')}-component">
            <h2>{prompt}</h2>
            <p>Component content here...</p>
        </div>
    );
}};

export default {prompt.replace(' ', '')}Component;'''
            }
        }
        
        code = templates.get(language, {}).get(code_type) or templates.get(language, {}).get('general', f'// TODO: Implement {prompt}')
        
        return {
            'code': code,
            'model': 'enhanced-template',
            'success': True,
            'suggestions': ['Consider adding error handling', 'Add accessibility features', 'Optimize for performance'],
            'dependencies': []
        }
    
    def _generate_template_code(self, prompt: str, language: str) -> Dict[str, Any]:
        """Generate basic template code when AI is not available"""
        return self._generate_enhanced_template(prompt, language, 'general')
    
    def generate_website_template(self, template_type: str, customizations: Dict = None) -> Dict[str, Any]:
        """
        Generate complete website templates
        
        Args:
            template_type: Type of website (landing, portfolio, blog, ecommerce, dashboard)
            customizations: Custom options (colors, layout, features)
            
        Returns:
            Complete website structure with files
        """
        customizations = customizations or {}
        
        templates = {
            'landing': self._generate_landing_page(customizations),
            'portfolio': self._generate_portfolio_site(customizations),
            'blog': self._generate_blog_site(customizations),
            'ecommerce': self._generate_ecommerce_site(customizations),
            'dashboard': self._generate_dashboard_site(customizations)
        }
        
        return templates.get(template_type, {
            'files': {
                'index.html': '<!DOCTYPE html><html><head><title>New Site</title></head><body><h1>Welcome</h1></body></html>',
                'style.css': 'body { font-family: Arial, sans-serif; }',
                'script.js': 'console.log("Site loaded");'
            },
            'structure': ['index.html', 'style.css', 'script.js']
        })
    
    def _generate_landing_page(self, customizations: Dict) -> Dict[str, Any]:
        """Generate landing page template"""
        primary_color = customizations.get('primary_color', '#007acc')
        company_name = customizations.get('company_name', 'Your Company')
        
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{company_name} - Welcome</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <header class="header">
        <nav class="navbar">
            <div class="container">
                <div class="brand">{company_name}</div>
                <ul class="nav-links">
                    <li><a href="#home">Home</a></li>
                    <li><a href="#about">About</a></li>
                    <li><a href="#services">Services</a></li>
                    <li><a href="#contact">Contact</a></li>
                </ul>
                <button class="menu-toggle">☰</button>
            </div>
        </nav>
    </header>

    <main>
        <section id="home" class="hero">
            <div class="container">
                <div class="hero-content">
                    <h1>Welcome to {company_name}</h1>
                    <p>We create amazing digital experiences that drive results</p>
                    <button class="cta-button">Get Started</button>
                </div>
            </div>
        </section>

        <section id="about" class="section">
            <div class="container">
                <h2>About Us</h2>
                <p>We are a team of passionate professionals dedicated to delivering excellence.</p>
            </div>
        </section>

        <section id="services" class="section">
            <div class="container">
                <h2>Our Services</h2>
                <div class="services-grid">
                    <div class="service-card">
                        <h3>Web Design</h3>
                        <p>Beautiful, responsive websites</p>
                    </div>
                    <div class="service-card">
                        <h3>Development</h3>
                        <p>Custom web applications</p>
                    </div>
                    <div class="service-card">
                        <h3>Marketing</h3>
                        <p>Digital marketing strategies</p>
                    </div>
                </div>
            </div>
        </section>

        <section id="contact" class="section">
            <div class="container">
                <h2>Contact Us</h2>
                <form class="contact-form">
                    <input type="text" placeholder="Your Name" required>
                    <input type="email" placeholder="Your Email" required>
                    <textarea placeholder="Your Message" required></textarea>
                    <button type="submit">Send Message</button>
                </form>
            </div>
        </section>
    </main>

    <footer class="footer">
        <div class="container">
            <p>&copy; 2025 {company_name}. All rights reserved.</p>
        </div>
    </footer>

    <script src="script.js"></script>
</body>
</html>'''

        css = f'''/* Landing Page Styles */
:root {{
    --primary-color: {primary_color};
    --secondary-color: #6c757d;
    --background-color: #ffffff;
    --text-color: #333333;
    --light-bg: #f8f9fa;
    --border-color: #e9ecef;
    --shadow: 0 2px 10px rgba(0,0,0,0.1);
}}

* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    line-height: 1.6;
    color: var(--text-color);
    overflow-x: hidden;
}}

.container {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
}}

/* Header */
.header {{
    background: var(--background-color);
    box-shadow: var(--shadow);
    position: fixed;
    top: 0;
    width: 100%;
    z-index: 1000;
}}

.navbar {{
    padding: 1rem 0;
}}

.navbar .container {{
    display: flex;
    justify-content: space-between;
    align-items: center;
}}

.brand {{
    font-size: 1.5rem;
    font-weight: bold;
    color: var(--primary-color);
}}

.nav-links {{
    display: flex;
    list-style: none;
    gap: 2rem;
}}

.nav-links a {{
    text-decoration: none;
    color: var(--text-color);
    transition: color 0.3s;
}}

.nav-links a:hover {{
    color: var(--primary-color);
}}

.menu-toggle {{
    display: none;
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
}}

/* Hero Section */
.hero {{
    background: linear-gradient(135deg, var(--primary-color), #4a90e2);
    color: white;
    padding: 150px 0 100px;
    text-align: center;
}}

.hero-content h1 {{
    font-size: 3rem;
    margin-bottom: 1rem;
    animation: fadeInUp 1s ease-out;
}}

.hero-content p {{
    font-size: 1.2rem;
    margin-bottom: 2rem;
    animation: fadeInUp 1s ease-out 0.2s both;
}}

.cta-button {{
    background: white;
    color: var(--primary-color);
    border: none;
    padding: 15px 30px;
    font-size: 1.1rem;
    border-radius: 30px;
    cursor: pointer;
    transition: transform 0.3s;
    animation: fadeInUp 1s ease-out 0.4s both;
}}

.cta-button:hover {{
    transform: translateY(-2px);
}}

/* Sections */
.section {{
    padding: 80px 0;
}}

.section:nth-child(even) {{
    background: var(--light-bg);
}}

.section h2 {{
    text-align: center;
    font-size: 2.5rem;
    margin-bottom: 3rem;
    color: var(--primary-color);
}}

/* Services Grid */
.services-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 2rem;
    margin-top: 3rem;
}}

.service-card {{
    background: white;
    padding: 2rem;
    border-radius: 10px;
    box-shadow: var(--shadow);
    text-align: center;
    transition: transform 0.3s;
}}

.service-card:hover {{
    transform: translateY(-5px);
}}

.service-card h3 {{
    color: var(--primary-color);
    margin-bottom: 1rem;
}}

/* Contact Form */
.contact-form {{
    max-width: 600px;
    margin: 0 auto;
    display: grid;
    gap: 1rem;
}}

.contact-form input,
.contact-form textarea {{
    padding: 15px;
    border: 1px solid var(--border-color);
    border-radius: 5px;
    font-family: inherit;
}}

.contact-form textarea {{
    min-height: 120px;
    resize: vertical;
}}

.contact-form button {{
    background: var(--primary-color);
    color: white;
    border: none;
    padding: 15px;
    border-radius: 5px;
    cursor: pointer;
    transition: background 0.3s;
}}

.contact-form button:hover {{
    background: #0056b3;
}}

/* Footer */
.footer {{
    background: #333;
    color: white;
    text-align: center;
    padding: 2rem 0;
}}

/* Animations */
@keyframes fadeInUp {{
    from {{
        opacity: 0;
        transform: translateY(30px);
    }}
    to {{
        opacity: 1;
        transform: translateY(0);
    }}
}}

/* Responsive Design */
@media (max-width: 768px) {{
    .nav-links {{
        display: none;
    }}
    
    .menu-toggle {{
        display: block;
    }}
    
    .hero-content h1 {{
        font-size: 2rem;
    }}
    
    .section h2 {{
        font-size: 2rem;
    }}
    
    .services-grid {{
        grid-template-columns: 1fr;
    }}
}}'''

        js = '''// Landing Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Mobile menu toggle
    const menuToggle = document.querySelector('.menu-toggle');
    const navLinks = document.querySelector('.nav-links');
    
    menuToggle.addEventListener('click', function() {
        navLinks.style.display = navLinks.style.display === 'flex' ? 'none' : 'flex';
    });
    
    // Smooth scrolling for navigation links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
    
    // Contact form submission
    const contactForm = document.querySelector('.contact-form');
    contactForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Get form data
        const formData = new FormData(contactForm);
        
        // Show success message (replace with actual form submission)
        alert('Thank you for your message! We will get back to you soon.');
        contactForm.reset();
    });
    
    // Add scroll effect to navbar
    window.addEventListener('scroll', function() {
        const header = document.querySelector('.header');
        if (window.scrollY > 100) {
            header.style.background = 'rgba(255, 255, 255, 0.95)';
            header.style.backdropFilter = 'blur(10px)';
        } else {
            header.style.background = 'var(--background-color)';
            header.style.backdropFilter = 'none';
        }
    });
    
    // Animate elements on scroll
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };
    
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);
    
    // Observe all sections
    document.querySelectorAll('.section').forEach(section => {
        section.style.opacity = '0';
        section.style.transform = 'translateY(30px)';
        section.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(section);
    });
});'''

        return {
            'files': {
                'index.html': html,
                'style.css': css,
                'script.js': js
            },
            'structure': ['index.html', 'style.css', 'script.js'],
            'template_type': 'landing',
            'customizations_applied': customizations
        }
    
    def generate_autocomplete_suggestions(self, code: str, cursor_position: int, 
                                        language: str, context: Dict = None) -> List[Dict]:
        """
        Generate intelligent autocomplete suggestions
        
        Args:
            code: Current code content
            cursor_position: Cursor position in code
            language: Programming language
            context: Additional context (project files, imports, etc.)
            
        Returns:
            List of autocomplete suggestions
        """
        suggestions = []
        
        # Get current word being typed
        lines = code[:cursor_position].split('\n')
        current_line = lines[-1]
        current_word = current_line.split()[-1] if current_line.split() else ''
        
        # Language-specific suggestions
        if language == 'html':
            suggestions.extend(self._get_html_suggestions(current_word, current_line))
        elif language == 'css':
            suggestions.extend(self._get_css_suggestions(current_word, current_line))
        elif language == 'javascript':
            suggestions.extend(self._get_js_suggestions(current_word, current_line, context))
        elif language == 'python':
            suggestions.extend(self._get_python_suggestions(current_word, current_line, context))
        
        return suggestions
    
    def _get_html_suggestions(self, current_word: str, current_line: str) -> List[Dict]:
        """Get HTML-specific suggestions"""
        suggestions = []
        
        if current_word.startswith('<'):
            # HTML tag suggestions
            tags = ['div', 'span', 'p', 'h1', 'h2', 'h3', 'img', 'a', 'button', 'input', 
                   'form', 'section', 'header', 'footer', 'nav', 'main', 'article']
            for tag in tags:
                if tag.startswith(current_word[1:]):
                    suggestions.append({
                        'label': tag,
                        'kind': 'snippet',
                        'insertText': f'{tag}>${{1}}</{tag}>',
                        'documentation': f'HTML {tag} element'
                    })
        
        elif 'class=' in current_line or 'id=' in current_line:
            # CSS class/id suggestions
            common_classes = ['container', 'row', 'col', 'btn', 'card', 'navbar', 'footer']
            for cls in common_classes:
                suggestions.append({
                    'label': cls,
                    'kind': 'value',
                    'insertText': cls,
                    'documentation': f'Common CSS class: {cls}'
                })
        
        return suggestions
    
    def _get_css_suggestions(self, current_word: str, current_line: str) -> List[Dict]:
        """Get CSS-specific suggestions"""
        suggestions = []
        
        # CSS property suggestions
        if ':' not in current_line or current_line.endswith(':'):
            properties = [
                'display', 'position', 'top', 'left', 'right', 'bottom',
                'width', 'height', 'margin', 'padding', 'border',
                'background', 'color', 'font-family', 'font-size',
                'text-align', 'text-decoration', 'line-height',
                'flex-direction', 'justify-content', 'align-items',
                'grid-template-columns', 'grid-template-rows'
            ]
            
            for prop in properties:
                if prop.startswith(current_word):
                    suggestions.append({
                        'label': prop,
                        'kind': 'property',
                        'insertText': f'{prop}: ${{1}};',
                        'documentation': f'CSS property: {prop}'
                    })
        
        return suggestions
    
    def _get_js_suggestions(self, current_word: str, current_line: str, context: Dict) -> List[Dict]:
        """Get JavaScript-specific suggestions"""
        suggestions = []
        
        # JavaScript keywords and methods
        keywords = [
            'function', 'const', 'let', 'var', 'if', 'else', 'for', 'while',
            'return', 'try', 'catch', 'throw', 'async', 'await', 'import', 'export'
        ]
        
        methods = [
            'addEventListener', 'querySelector', 'querySelectorAll',
            'getElementById', 'getElementsByClassName', 'createElement',
            'appendChild', 'removeChild', 'setAttribute', 'getAttribute'
        ]
        
        for keyword in keywords:
            if keyword.startswith(current_word):
                suggestions.append({
                    'label': keyword,
                    'kind': 'keyword',
                    'insertText': keyword,
                    'documentation': f'JavaScript keyword: {keyword}'
                })
        
        for method in methods:
            if method.startswith(current_word):
                suggestions.append({
                    'label': method,
                    'kind': 'method',
                    'insertText': f'{method}(${{1}})',
                    'documentation': f'JavaScript method: {method}'
                })
        
        return suggestions
    
    def explain_code(self, code: str, language: str = 'python') -> Dict[str, Any]:
        """
        Explain what code does
        
        Args:
            code: Code to explain
            language: Programming language
            
        Returns:
            Code explanation
        """
        
        if self.ai_service:
            try:
                from ..services.openrouter import generate_response
                
                prompt = f"""Explain the following {language} code in detail. 
Include:
1. What the code does
2. Key components and their purpose
3. Any potential issues or improvements

Code:
```{language}
{code}
```
"""
                
                response = generate_response(prompt=prompt)
                
                return {
                    'explanation': response.get('assistant_text', ''),
                    'model': response.get('model', 'unknown'),
                    'success': True
                }
            except Exception as e:
                return {
                    'explanation': f'Error generating explanation: {str(e)}',
                    'error': str(e),
                    'success': False
                }
        
        return {
            'explanation': 'AI explanation not available. Please configure an AI service.',
            'success': False
        }
    
    def fix_code(self, code: str, error: str, language: str = 'python') -> Dict[str, Any]:
        """
        Fix code based on error message
        
        Args:
            code: Code with errors
            error: Error message
            language: Programming language
            
        Returns:
            Fixed code and explanation
        """
        
        if self.ai_service:
            try:
                from ..services.openrouter import generate_response
                
                prompt = f"""Fix the following {language} code. The error is:
{error}

Code:
```{language}
{code}
```

Provide the fixed code and explain what was wrong.
"""
                
                response = generate_response(prompt=prompt)
                
                return {
                    'fixed_code': response.get('assistant_text', ''),
                    'model': response.get('model', 'unknown'),
                    'success': True
                }
            except Exception as e:
                return {
                    'fixed_code': code,
                    'error': str(e),
                    'success': False
                }
        
        return {
            'fixed_code': code,
            'explanation': 'AI code fixing not available.',
            'success': False
        }
    
    def suggest_improvements(self, code: str, language: str = 'python') -> Dict[str, Any]:
        """
        Suggest code improvements
        
        Args:
            code: Code to improve
            language: Programming language
            
        Returns:
            Improvement suggestions
        """
        
        if self.ai_service:
            try:
                from ..services.openrouter import generate_response
                
                prompt = f"""Review this {language} code and suggest improvements for:
1. Code quality and readability
2. Performance optimization
3. Best practices
4. Security considerations

Code:
```{language}
{code}
```
"""
                
                response = generate_response(prompt=prompt)
                
                return {
                    'suggestions': response.get('assistant_text', ''),
                    'model': response.get('model', 'unknown'),
                    'success': True
                }
            except Exception as e:
                return {
                    'suggestions': f'Error generating suggestions: {str(e)}',
                    'error': str(e),
                    'success': False
                }
        
        return {
            'suggestions': 'AI suggestions not available.',
            'success': False
        }


# Service instances
ide_service = IDEService()
ai_code_assistant = AICodeAssistant()
