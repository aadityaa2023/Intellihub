"""
IDE Views - Web IDE interface views and API endpoints
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
from django import forms
import json
import time
import base64
from datetime import timedelta

from .models import (
    IDEProject, CodeFile, IDEChatMessage, CodeExecutionResult,
    ProjectDeployment, ProjectExport, UserIDEPreferences
)
from .services.ide_service import ide_service, ai_code_assistant
from .services.openrouter import generate_response


# ============================================================================
# FORMS
# ============================================================================

class ProjectCreateForm(forms.ModelForm):
    """Form for creating a new IDE project"""
    
    class Meta:
        model = IDEProject
        fields = ['name', 'description', 'project_type', 'is_public', 'ai_enabled']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class FileCreateForm(forms.ModelForm):
    """Form for creating a new file"""
    
    class Meta:
        model = CodeFile
        fields = ['name', 'path', 'file_type']


class FileEditForm(forms.ModelForm):
    """Form for editing file content"""
    
    class Meta:
        model = CodeFile
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 20}),
        }


# ============================================================================
# PROJECT VIEWS
# ============================================================================

class IDEDashboardView(LoginRequiredMixin, View):
    """IDE dashboard - shows all user projects"""
    
    template_name = 'ide_dashboard.html'
    
    def get(self, request):
        projects = IDEProject.objects.filter(user=request.user).order_by('-updated_at')
        
        # Pagination
        paginator = Paginator(projects, 12)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Get or create user preferences
        preferences, created = UserIDEPreferences.objects.get_or_create(user=request.user)
        
        context = {
            'projects': page_obj,
            'preferences': preferences,
            'total_projects': projects.count(),
        }
        
        return render(request, self.template_name, context)


class ProjectCreateView(LoginRequiredMixin, View):
    """Create a new IDE project"""
    
    template_name = 'ide_project_create.html'
    
    def get(self, request):
        form = ProjectCreateForm()
        context = {'form': form}
        return render(request, self.template_name, context)
    
    def post(self, request):
        form = ProjectCreateForm(request.POST)
        
        if form.is_valid():
            with transaction.atomic():
                # Create project
                project = form.save(commit=False)
                project.user = request.user
                project.save()
                
                # Create initial project structure
                structure = ide_service.create_project_structure(project.project_type)
                
                # Create files
                for file_data in structure['files']:
                    CodeFile.objects.create(
                        project=project,
                        name=file_data['name'],
                        path=file_data['name'],
                        content=file_data['content'],
                        file_type=CodeFile.objects.model.detect_language(
                            CodeFile(name=file_data['name'])
                        ) if hasattr(CodeFile.objects.model, 'detect_language') else 'text'
                    )
                
                # Update user preferences
                preferences, _ = UserIDEPreferences.objects.get_or_create(user=request.user)
                preferences.total_projects += 1
                preferences.save()
                
                return redirect('ide_editor', project_id=project.id)
        
        context = {'form': form}
        return render(request, self.template_name, context)


class IDEEditorView(LoginRequiredMixin, View):
    """Main IDE editor interface - Currently under construction"""
    
    template_name = 'ide_under_construction.html'
    
    def get(self, request, project_id):
        # Verify project exists and belongs to user
        project = get_object_or_404(IDEProject, id=project_id, user=request.user)
        
        # Update last accessed time
        project.update_access_time()
        
        # For now, just show under construction page
        # TODO: Replace with full IDE editor implementation
        context = {
            'project': project,
        }
        
        return render(request, self.template_name, context)


class ProjectDeleteView(LoginRequiredMixin, View):
    """Delete a project"""
    
    def post(self, request, project_id):
        project = get_object_or_404(IDEProject, id=project_id, user=request.user)
        project.delete()
        
        return JsonResponse({'success': True, 'message': 'Project deleted successfully'})


# ============================================================================
# FILE MANAGEMENT VIEWS
# ============================================================================

class FileAPIView(LoginRequiredMixin, View):
    """API for file operations (CRUD)"""
    
    def get(self, request, project_id, file_id=None):
        """Get file content or list of files"""
        project = get_object_or_404(IDEProject, id=project_id, user=request.user)
        
        if file_id:
            # Get specific file
            file = get_object_or_404(CodeFile, id=file_id, project=project)
            
            return JsonResponse({
                'success': True,
                'file': {
                    'id': file.id,
                    'name': file.name,
                    'path': file.path,
                    'content': file.content,
                    'file_type': file.file_type,
                    'language': file.language or file.file_type,
                    'size': file.size_bytes,
                    'lines': file.line_count,
                    'updated_at': file.updated_at.isoformat(),
                }
            })
        else:
            # Get all files
            files = project.files.all()
            
            return JsonResponse({
                'success': True,
                'files': [
                    {
                        'id': f.id,
                        'name': f.name,
                        'path': f.path,
                        'file_type': f.file_type,
                        'size': f.size_bytes,
                    }
                    for f in files
                ]
            })
    
    def post(self, request, project_id):
        """Create a new file"""
        project = get_object_or_404(IDEProject, id=project_id, user=request.user)
        
        try:
            data = json.loads(request.body)
            
            file = CodeFile.objects.create(
                project=project,
                name=data.get('name', 'untitled'),
                path=data.get('path', data.get('name', 'untitled')),
                content=data.get('content', ''),
                file_type=data.get('file_type', 'text'),
                language=data.get('language'),
            )
            
            return JsonResponse({
                'success': True,
                'file': {
                    'id': file.id,
                    'name': file.name,
                    'path': file.path,
                    'file_type': file.file_type,
                }
            })
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    def put(self, request, project_id, file_id):
        """Update file content"""
        project = get_object_or_404(IDEProject, id=project_id, user=request.user)
        file = get_object_or_404(CodeFile, id=file_id, project=project)
        
        try:
            data = json.loads(request.body)
            
            # Save previous version if content changed
            if file.content != data.get('content'):
                # Create version backup
                file.version += 1
            
            file.content = data.get('content', file.content)
            file.name = data.get('name', file.name)
            file.path = data.get('path', file.path)
            file.save()
            
            return JsonResponse({
                'success': True,
                'message': 'File updated successfully',
                'file': {
                    'id': file.id,
                    'version': file.version,
                    'updated_at': file.updated_at.isoformat(),
                }
            })
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    def delete(self, request, project_id, file_id):
        """Delete a file"""
        project = get_object_or_404(IDEProject, id=project_id, user=request.user)
        file = get_object_or_404(CodeFile, id=file_id, project=project)
        
        file.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'File deleted successfully'
        })


# ============================================================================
# CODE EXECUTION VIEWS
# ============================================================================

class CodeExecutionView(LoginRequiredMixin, View):
    """Execute code and return results"""
    
    def post(self, request, project_id):
        project = get_object_or_404(IDEProject, id=project_id, user=request.user)
        
        try:
            data = json.loads(request.body)
            
            code = data.get('code', '')
            language = data.get('language', 'python')
            file_id = data.get('file_id')
            execution_type = data.get('execution_type', 'snippet')
            
            # Create execution record
            execution = CodeExecutionResult.objects.create(
                project=project,
                user=request.user,
                code=code,
                execution_type=execution_type,
                status='running'
            )
            
            if file_id:
                execution.file = CodeFile.objects.get(id=file_id, project=project)
                execution.save()
            
            # Execute code
            result = ide_service.execute_code(
                code=code,
                language=language,
                timeout=30
            )
            
            # Update execution record
            execution.status = result.get('status', 'completed')
            execution.stdout = result.get('stdout', '')
            execution.stderr = result.get('stderr', '')
            execution.exit_code = result.get('exit_code')
            execution.execution_time = result.get('execution_time', 0)
            execution.completed_at = timezone.now()
            execution.save()
            
            # Update project stats
            project.total_executions += 1
            project.save(update_fields=['total_executions'])
            
            # Update user preferences stats
            preferences, _ = UserIDEPreferences.objects.get_or_create(user=request.user)
            preferences.total_executions += 1
            preferences.save()
            
            return JsonResponse({
                'success': True,
                'execution_id': execution.id,
                'status': execution.status,
                'stdout': execution.stdout,
                'stderr': execution.stderr,
                'exit_code': execution.exit_code,
                'execution_time': execution.execution_time,
                'html_content': result.get('html_content'),  # For HTML preview
            })
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)


class ExecutionHistoryView(LoginRequiredMixin, View):
    """View execution history"""
    
    def get(self, request, project_id):
        project = get_object_or_404(IDEProject, id=project_id, user=request.user)
        
        executions = project.executions.all()[:50]
        
        return JsonResponse({
            'success': True,
            'executions': [
                {
                    'id': ex.id,
                    'status': ex.status,
                    'execution_type': ex.execution_type,
                    'exit_code': ex.exit_code,
                    'execution_time': ex.execution_time,
                    'created_at': ex.created_at.isoformat(),
                }
                for ex in executions
            ]
        })


# ============================================================================
# AI CHAT VIEWS
# ============================================================================

class IDEChatView(LoginRequiredMixin, View):
    """Chat with AI assistant in IDE"""
    
    def post(self, request, project_id):
        project = get_object_or_404(IDEProject, id=project_id, user=request.user)
        
        if not project.ai_enabled:
            return JsonResponse({
                'success': False,
                'error': 'AI is not enabled for this project'
            }, status=400)
        
        try:
            data = json.loads(request.body)
            
            message = data.get('message', '')
            message_type = data.get('type', 'chat')
            context_file_ids = data.get('context_files', [])
            
            # Save user message
            user_message = IDEChatMessage.objects.create(
                project=project,
                role='user',
                content=message,
                message_type=message_type
            )
            
            # Add context files
            if context_file_ids:
                context_files = CodeFile.objects.filter(
                    id__in=context_file_ids,
                    project=project
                )
                user_message.context_files.set(context_files)
            
            # Build context for AI
            context = self._build_ai_context(project, context_file_ids)
            
            # Generate AI response based on message type
            start_time = time.time()
            
            if message_type == 'code_generation':
                ai_result = ai_code_assistant.generate_code(
                    prompt=message,
                    language=project.project_type,
                    context=context
                )
            elif message_type == 'code_explanation':
                code = data.get('code', '')
                ai_result = ai_code_assistant.explain_code(
                    code=code,
                    language=project.project_type
                )
            elif message_type == 'code_fix':
                code = data.get('code', '')
                error = data.get('error', '')
                ai_result = ai_code_assistant.fix_code(
                    code=code,
                    error=error,
                    language=project.project_type
                )
            else:
                # General chat
                full_prompt = f"{context}\n\nUser: {message}"
                response = generate_response(prompt=full_prompt)
                ai_result = {
                    'success': True,
                    'model': response.get('model', 'unknown'),
                }
                # Extract response text based on message type
                if message_type == 'code_generation':
                    ai_result['code'] = response.get('assistant_text', '')
                elif message_type == 'code_explanation':
                    ai_result['explanation'] = response.get('assistant_text', '')
                else:
                    ai_result['response'] = response.get('assistant_text', '')
            
            response_time = time.time() - start_time
            
            # Save assistant message
            assistant_content = ai_result.get('code') or ai_result.get('explanation') or ai_result.get('response', 'No response')
            
            assistant_message = IDEChatMessage.objects.create(
                project=project,
                role='assistant',
                content=assistant_content,
                message_type=message_type,
                model_used=ai_result.get('model', 'unknown'),
                response_time=response_time
            )
            
            # Update project stats
            project.total_ai_queries += 1
            project.save(update_fields=['total_ai_queries'])
            
            # Update user preferences
            preferences, _ = UserIDEPreferences.objects.get_or_create(user=request.user)
            preferences.total_ai_queries += 1
            preferences.save()
            
            return JsonResponse({
                'success': True,
                'message_id': assistant_message.id,
                'content': assistant_content,
                'model': ai_result.get('model', 'unknown'),
                'response_time': response_time,
                'type': message_type,
            })
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    def _build_ai_context(self, project, file_ids=None):
        """Build context for AI from project files"""
        
        context = f"Project: {project.name}\nType: {project.project_type}\n\n"
        
        if file_ids:
            files = CodeFile.objects.filter(id__in=file_ids, project=project)
            for file in files:
                context += f"\nFile: {file.path}\n```{file.file_type}\n{file.content}\n```\n"
        
        return context
    
    def get(self, request, project_id):
        """Get chat history"""
        project = get_object_or_404(IDEProject, id=project_id, user=request.user)
        
        messages = project.chat_messages.all()[:100]
        
        return JsonResponse({
            'success': True,
            'messages': [
                {
                    'id': msg.id,
                    'role': msg.role,
                    'content': msg.content,
                    'type': msg.message_type,
                    'model': msg.model_used,
                    'created_at': msg.created_at.isoformat(),
                }
                for msg in messages
            ]
        })


# ============================================================================
# EXPORT & DEPLOYMENT VIEWS
# ============================================================================

class ProjectExportView(LoginRequiredMixin, View):
    """Export project as ZIP or other formats"""
    
    def post(self, request, project_id):
        project = get_object_or_404(IDEProject, id=project_id, user=request.user)
        
        try:
            data = json.loads(request.body)
            export_format = data.get('format', 'zip')
            
            # Create export record
            export = ProjectExport.objects.create(
                project=project,
                user=request.user,
                export_format=export_format,
                status='processing'
            )
            
            # Generate export
            result = ide_service.export_project(project, export_format)
            
            if result['status'] == 'completed':
                export.file_data = result['file_data']
                export.file_size = result['file_size']
                export.status = 'completed'
                
                # Set expiration (24 hours)
                export.expires_at = timezone.now() + timedelta(hours=24)
            else:
                export.status = 'failed'
            
            export.save()
            
            return JsonResponse({
                'success': result['status'] == 'completed',
                'export_id': export.id,
                'file_size': export.file_size,
                'expires_at': export.expires_at.isoformat() if export.expires_at else None,
            })
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    def get(self, request, project_id, export_id):
        """Download exported project"""
        project = get_object_or_404(IDEProject, id=project_id, user=request.user)
        export = get_object_or_404(ProjectExport, id=export_id, project=project)
        
        if export.is_expired:
            return JsonResponse({
                'success': False,
                'error': 'Export has expired'
            }, status=410)
        
        if export.status != 'completed':
            return JsonResponse({
                'success': False,
                'error': 'Export is not ready'
            }, status=400)
        
        # Decode file data
        file_data = base64.b64decode(export.file_data)
        
        # Return file
        response = HttpResponse(file_data, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{project.name}.zip"'
        
        return response


class ProjectDeploymentView(LoginRequiredMixin, View):
    """Handle project deployment to various platforms"""
    
    def post(self, request, project_id):
        project = get_object_or_404(IDEProject, id=project_id, user=request.user)
        
        try:
            data = json.loads(request.body)
            platform = data.get('platform', 'github')
            config = data.get('config', {})
            
            # Create deployment record
            deployment = ProjectDeployment.objects.create(
                project=project,
                user=request.user,
                platform=platform,
                config=config,
                status='pending'
            )
            
            # For now, return success
            # In production, integrate with GitHub API, Vercel, etc.
            
            return JsonResponse({
                'success': True,
                'deployment_id': deployment.id,
                'message': f'Deployment to {platform} initiated',
                'status': 'pending'
            })
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)


# ============================================================================
# PREFERENCES VIEWS
# ============================================================================

class IDEPreferencesView(LoginRequiredMixin, View):
    """Manage IDE user preferences"""
    
    def get(self, request):
        preferences, _ = UserIDEPreferences.objects.get_or_create(user=request.user)
        
        return JsonResponse({
            'success': True,
            'preferences': {
                'theme': preferences.theme,
                'font_size': preferences.font_size,
                'font_family': preferences.font_family,
                'tab_size': preferences.tab_size,
                'use_spaces': preferences.use_spaces,
                'word_wrap': preferences.word_wrap,
                'line_numbers': preferences.line_numbers,
                'minimap_enabled': preferences.minimap_enabled,
                'ai_autocomplete': preferences.ai_autocomplete,
                'ai_suggestions': preferences.ai_suggestions,
                'auto_save': preferences.auto_save,
                'auto_format': preferences.auto_format,
            }
        })
    
    def post(self, request):
        preferences, _ = UserIDEPreferences.objects.get_or_create(user=request.user)
        
        try:
            data = json.loads(request.body)
            
            # Update preferences
            for key, value in data.items():
                if hasattr(preferences, key):
                    setattr(preferences, key, value)
            
            preferences.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Preferences updated successfully'
            })
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)


class WebsiteTemplateView(LoginRequiredMixin, View):
    """Generate website templates"""
    
    def get(self, request):
        """Get available template types"""
        templates = {
            'landing': {
                'name': 'Landing Page',
                'description': 'Modern landing page with hero section, features, and contact form',
                'preview': '/static/previews/landing.png',
                'features': ['Responsive design', 'Contact form', 'Hero section', 'Modern styling']
            },
            'portfolio': {
                'name': 'Portfolio',
                'description': 'Professional portfolio website to showcase your work',
                'preview': '/static/previews/portfolio.png',
                'features': ['Project gallery', 'About section', 'Contact info', 'Skills showcase']
            },
            'blog': {
                'name': 'Blog',
                'description': 'Clean blog layout with articles and sidebar',
                'preview': '/static/previews/blog.png',
                'features': ['Article layout', 'Sidebar', 'Tags system', 'Archive pages']
            },
            'ecommerce': {
                'name': 'E-commerce',
                'description': 'Online store with product catalog and shopping cart',
                'preview': '/static/previews/ecommerce.png',
                'features': ['Product grid', 'Cart system', 'Checkout form', 'Product details']
            },
            'dashboard': {
                'name': 'Dashboard',
                'description': 'Admin dashboard with charts, tables, and navigation',
                'preview': '/static/previews/dashboard.png',
                'features': ['Charts & graphs', 'Data tables', 'Navigation', 'Statistics cards']
            }
        }
        
        return JsonResponse({
            'success': True,
            'templates': templates
        })
    
    def post(self, request):
        """Generate a website template"""
        try:
            data = json.loads(request.body)
            template_type = data.get('template_type')
            customizations = data.get('customizations', {})
            project_name = data.get('project_name', f'{template_type.title()} Site')
            
            if not template_type:
                return JsonResponse({
                    'success': False,
                    'error': 'Template type is required'
                }, status=400)
            
            # Generate template using IDE service
            template_data = ai_code_assistant.generate_website_template(
                template_type, customizations
            )
            
            # Create new project
            project = IDEProject.objects.create(
                user=request.user,
                name=project_name,
                description=f'{template_type.title()} website generated from template',
                project_type='html',
                template_type=template_type
            )
            
            # Create files from template
            files_created = []
            for filename, content in template_data.get('files', {}).items():
                file = CodeFile.objects.create(
                    project=project,
                    name=filename,
                    content=content,
                    file_type=filename.split('.')[-1] if '.' in filename else 'txt',
                    language=self._detect_language(filename)
                )
                files_created.append({
                    'id': file.id,
                    'name': file.name,
                    'language': file.language
                })
            
            return JsonResponse({
                'success': True,
                'project': {
                    'id': project.id,
                    'name': project.name,
                    'description': project.description
                },
                'files': files_created,
                'template_type': template_type,
                'redirect_url': f'/ide/projects/{project.id}/'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def _detect_language(self, filename):
        """Detect programming language from filename"""
        ext_map = {
            'html': 'html',
            'css': 'css',
            'js': 'javascript',
            'py': 'python',
            'json': 'json',
            'md': 'markdown',
            'yaml': 'yaml',
            'yml': 'yaml'
        }
        
        ext = filename.split('.')[-1].lower() if '.' in filename else 'txt'
        return ext_map.get(ext, 'plaintext')


class ComponentLibraryView(LoginRequiredMixin, View):
    """UI Component library for web development"""
    
    def get(self, request):
        """Get available UI components"""
        components = {
            'navigation': {
                'navbar': {
                    'name': 'Navigation Bar',
                    'description': 'Responsive navigation with menu items',
                    'code': self._get_navbar_code(),
                    'preview': '<nav>Preview...</nav>'
                },
                'sidebar': {
                    'name': 'Sidebar Navigation',
                    'description': 'Collapsible sidebar for dashboards',
                    'code': self._get_sidebar_code(),
                    'preview': '<aside>Sidebar...</aside>'
                }
            },
            'forms': {
                'contact_form': {
                    'name': 'Contact Form',
                    'description': 'Complete contact form with validation',
                    'code': self._get_contact_form_code(),
                    'preview': '<form>Form...</form>'
                },
                'login_form': {
                    'name': 'Login Form',
                    'description': 'Modern login form with styling',
                    'code': self._get_login_form_code(),
                    'preview': '<form>Login...</form>'
                }
            },
            'cards': {
                'feature_card': {
                    'name': 'Feature Card',
                    'description': 'Card component for features or services',
                    'code': self._get_feature_card_code(),
                    'preview': '<div>Card...</div>'
                },
                'pricing_card': {
                    'name': 'Pricing Card',
                    'description': 'Pricing table card component',
                    'code': self._get_pricing_card_code(),
                    'preview': '<div>Pricing...</div>'
                }
            },
            'layouts': {
                'hero_section': {
                    'name': 'Hero Section',
                    'description': 'Landing page hero with call-to-action',
                    'code': self._get_hero_section_code(),
                    'preview': '<section>Hero...</section>'
                },
                'footer': {
                    'name': 'Footer',
                    'description': 'Complete footer with links and social media',
                    'code': self._get_footer_code(),
                    'preview': '<footer>Footer...</footer>'
                }
            }
        }
        
        return JsonResponse({
            'success': True,
            'components': components
        })
    
    def _get_navbar_code(self):
        return {
            'html': '''<nav class="navbar">
    <div class="nav-container">
        <a href="#" class="nav-brand">Brand</a>
        <ul class="nav-menu">
            <li><a href="#home">Home</a></li>
            <li><a href="#about">About</a></li>
            <li><a href="#services">Services</a></li>
            <li><a href="#contact">Contact</a></li>
        </ul>
        <div class="hamburger">
            <span></span>
            <span></span>
            <span></span>
        </div>
    </div>
</nav>''',
            'css': '''.navbar {
    background: #ffffff;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    position: fixed;
    top: 0;
    width: 100%;
    z-index: 1000;
}

.nav-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    height: 60px;
}

.nav-brand {
    font-size: 1.5rem;
    font-weight: bold;
    color: #333;
    text-decoration: none;
}

.nav-menu {
    display: flex;
    list-style: none;
    margin: 0;
    padding: 0;
    gap: 2rem;
}

.nav-menu a {
    color: #333;
    text-decoration: none;
    transition: color 0.3s;
}

.nav-menu a:hover {
    color: #007acc;
}

.hamburger {
    display: none;
    flex-direction: column;
    cursor: pointer;
}

.hamburger span {
    width: 25px;
    height: 3px;
    background: #333;
    margin: 3px 0;
    transition: 0.3s;
}

@media (max-width: 768px) {
    .nav-menu {
        position: fixed;
        top: 60px;
        left: -100%;
        width: 100%;
        background: #ffffff;
        flex-direction: column;
        text-align: center;
        transition: 0.3s;
        box-shadow: 0 10px 27px rgba(0,0,0,0.05);
    }
    
    .nav-menu.active {
        left: 0;
    }
    
    .hamburger {
        display: flex;
    }
}''',
            'js': '''// Navbar functionality
document.addEventListener('DOMContentLoaded', function() {
    const hamburger = document.querySelector('.hamburger');
    const navMenu = document.querySelector('.nav-menu');
    
    hamburger.addEventListener('click', function() {
        navMenu.classList.toggle('active');
    });
    
    // Close menu when clicking on links
    document.querySelectorAll('.nav-menu a').forEach(link => {
        link.addEventListener('click', () => {
            navMenu.classList.remove('active');
        });
    });
});'''
        }
    
    def _get_contact_form_code(self):
        return {
            'html': '''<form class="contact-form" id="contactForm">
    <h2>Get in Touch</h2>
    <div class="form-group">
        <label for="name">Name</label>
        <input type="text" id="name" name="name" required>
    </div>
    <div class="form-group">
        <label for="email">Email</label>
        <input type="email" id="email" name="email" required>
    </div>
    <div class="form-group">
        <label for="subject">Subject</label>
        <input type="text" id="subject" name="subject" required>
    </div>
    <div class="form-group">
        <label for="message">Message</label>
        <textarea id="message" name="message" rows="5" required></textarea>
    </div>
    <button type="submit" class="submit-btn">Send Message</button>
</form>''',
            'css': '''.contact-form {
    max-width: 600px;
    margin: 0 auto;
    padding: 30px;
    background: #ffffff;
    border-radius: 10px;
    box-shadow: 0 5px 20px rgba(0,0,0,0.1);
}

.contact-form h2 {
    text-align: center;
    margin-bottom: 30px;
    color: #333;
}

.form-group {
    margin-bottom: 20px;
}

.form-group label {
    display: block;
    margin-bottom: 5px;
    color: #333;
    font-weight: 500;
}

.form-group input,
.form-group textarea {
    width: 100%;
    padding: 12px;
    border: 1px solid #ddd;
    border-radius: 5px;
    font-size: 14px;
    transition: border-color 0.3s;
}

.form-group input:focus,
.form-group textarea:focus {
    outline: none;
    border-color: #007acc;
}

.submit-btn {
    width: 100%;
    padding: 12px;
    background: #007acc;
    color: white;
    border: none;
    border-radius: 5px;
    cursor: pointer;
    font-size: 16px;
    transition: background 0.3s;
}

.submit-btn:hover {
    background: #0056b3;
}''',
            'js': '''// Contact form functionality
document.getElementById('contactForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    // Get form data
    const formData = new FormData(this);
    const data = Object.fromEntries(formData);
    
    // Simple validation
    if (!data.name || !data.email || !data.message) {
        alert('Please fill in all required fields');
        return;
    }
    
    // Simulate sending (replace with actual API call)
    alert('Thank you! Your message has been sent.');
    this.reset();
});'''
        }
    
    def _get_hero_section_code(self):
        return {
            'html': '''<section class="hero">
    <div class="hero-container">
        <div class="hero-content">
            <h1 class="hero-title">Welcome to Our Platform</h1>
            <p class="hero-subtitle">Create amazing digital experiences with our powerful tools and intuitive interface.</p>
            <div class="hero-buttons">
                <a href="#get-started" class="btn btn-primary">Get Started</a>
                <a href="#learn-more" class="btn btn-secondary">Learn More</a>
            </div>
        </div>
        <div class="hero-image">
            <img src="https://via.placeholder.com/600x400" alt="Hero Image">
        </div>
    </div>
</section>''',
            'css': '''.hero {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 100px 0;
    min-height: 600px;
    display: flex;
    align-items: center;
}

.hero-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 50px;
    align-items: center;
}

.hero-title {
    font-size: 3rem;
    margin-bottom: 20px;
    line-height: 1.2;
}

.hero-subtitle {
    font-size: 1.2rem;
    margin-bottom: 30px;
    opacity: 0.9;
}

.hero-buttons {
    display: flex;
    gap: 15px;
}

.btn {
    padding: 12px 30px;
    border-radius: 5px;
    text-decoration: none;
    font-weight: 500;
    transition: all 0.3s;
    border: 2px solid transparent;
}

.btn-primary {
    background: white;
    color: #667eea;
}

.btn-primary:hover {
    background: transparent;
    color: white;
    border-color: white;
}

.btn-secondary {
    background: transparent;
    color: white;
    border-color: white;
}

.btn-secondary:hover {
    background: white;
    color: #667eea;
}

.hero-image img {
    width: 100%;
    border-radius: 10px;
}

@media (max-width: 768px) {
    .hero-container {
        grid-template-columns: 1fr;
        text-align: center;
    }
    
    .hero-title {
        font-size: 2rem;
    }
}'''
        }
    
    # Add placeholder methods for other components
    def _get_sidebar_code(self): return {'html': '', 'css': '', 'js': ''}
    def _get_login_form_code(self): return {'html': '', 'css': '', 'js': ''}
    def _get_feature_card_code(self): return {'html': '', 'css': ''}
    def _get_pricing_card_code(self): return {'html': '', 'css': ''}
    def _get_footer_code(self): return {'html': '', 'css': ''}
