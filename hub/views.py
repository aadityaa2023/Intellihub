from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django import forms
from django.http import JsonResponse, StreamingHttpResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Sum
from django.utils import timezone
from .forms import (
    SignUpForm, ImageGenerationForm, QuickImageForm, ImageUpscaleForm, 
    VideoGenerationForm, QuickVideoForm, AudioGenerationForm, QuickAudioForm,
    PresentationGenerationForm, QuickPresentationForm, SlideEditForm, 
    PresentationShareForm, PresentationExportForm
)
from .models import (
    ChatConversation, ChatMessage,
    ImageGenerationRequest, GeneratedImage, ImageUpscaleRequest, UserImagePreferences, 
    VideoGenerationRequest, GeneratedVideo, UserVideoPreferences,
    AudioGenerationRequest, GeneratedAudio, UserAudioPreferences,
    PresentationProject, PresentationSlide, SlideElement, PresentationTemplate,
    PresentationExport, UserPresentationPreferences
)
from .services.stable_diffusion import generate_image, upscale_image, get_image_metrics
from .services.video_generation import generate_video, get_video_metrics
from .services.audio_generation import generate_audio, get_audio_metrics
from .services.presentation_generation import generate_presentation, get_presentation_metrics, get_available_themes, get_available_templates
import json
import time
import base64
from .services.openrouter import generate_response


def style_form_fields(form):
    """Apply Tailwind classes to form widgets for consistent styling."""
    base = 'w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary'
    try:
        for field in form:
            existing = field.field.widget.attrs.get('class', '')
            field.field.widget.attrs['class'] = (existing + ' ' + base).strip()
    except Exception:
        pass

class PromptForm(forms.Form):
    prompt = forms.CharField(widget=forms.Textarea(attrs={"rows":4}), label="Your Request")
    image_url = forms.URLField(required=False, label="Image URL (optional)")

class IndexView(LoginRequiredMixin, View):
    template_name = 'index.html'
    login_url = reverse_lazy('login')

    def get(self, request, conversation_id=None):
        if not request.user.is_authenticated:
            # Redirect to login with next
            next_url = request.get_full_path()
            return redirect(f"{reverse('login')}?next={next_url}")
        form = PromptForm()
        context = {
            "form": form,
            "conversation_id": conversation_id
        }
        return render(request, self.template_name, context)

    def stream_response(self, request):
        """Stream the AI response using Server-Sent Events"""
        def event_stream():
            try:
                data = json.loads(request.body)
                prompt = data.get('prompt', '')
                image_url = data.get('image_url') or None
                
                # Send start event
                yield f"data: {json.dumps({'type': 'start', 'message': 'Processing...'})}\n\n"
                time.sleep(0.1)  # Small delay for UX
                
                # Generate response
                result = generate_response(prompt=prompt, image_url=image_url)
                
                # Send the response in chunks for streaming effect
                assistant_text = result['assistant_text']
                words = assistant_text.split(' ')
                
                # Stream words gradually
                current_text = ""
                for i, word in enumerate(words):
                    current_text += word + " "
                    yield f"data: {json.dumps({'type': 'chunk', 'text': current_text.strip(), 'model': result['model'], 'task_type': result['task_type']})}\n\n"
                    time.sleep(0.05)  # Typing effect speed
                
                # Send completion event
                yield f"data: {json.dumps({'type': 'complete', 'text': assistant_text, 'model': result['model'], 'task_type': result['task_type']})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['Connection'] = 'keep-alive'
        return response

    def post(self, request, conversation_id=None):
        # Check if it's an AJAX request for streaming
        if request.headers.get('Accept') == 'text/event-stream':
            return self.stream_response(request)
        
        # Regular form submission
        form = PromptForm(request.POST)
        result = None
        error = None
        if form.is_valid():
            prompt = form.cleaned_data['prompt']
            image_url = form.cleaned_data['image_url'] or None
            try:
                result = generate_response(prompt=prompt, image_url=image_url)
                
                # If this is an AJAX request, return JSON response
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
                    # Get or create conversation
                    if conversation_id:
                        conversation = get_object_or_404(ChatConversation, id=conversation_id, user=request.user)
                    else:
                        # Create new conversation with title based on prompt
                        title = prompt[:50] + ('...' if len(prompt) > 50 else '')
                        conversation = ChatConversation.objects.create(
                            user=request.user,
                            title=title
                        )
                        conversation_id = conversation.id
                    
                    # Save user message
                    ChatMessage.objects.create(
                        conversation=conversation,
                        role='user',
                        content=prompt,
                        image_url=image_url
                    )
                    
                    # Save assistant message
                    ChatMessage.objects.create(
                        conversation=conversation,
                        role='assistant',
                        content=result['assistant_text'],
                        model_used=result['model'],
                        task_type=result['task_type'],
                        response_time=result.get('response_time', 1.0)
                    )
                    
                    # Update conversation timestamp
                    conversation.save()
                    
                    return JsonResponse({
                        'success': True,
                        'assistant_text': result['assistant_text'],
                        'model': result['model'],
                        'task_type': result['task_type'],
                        'response_time': result.get('response_time', 1.0),
                        'conversation_id': conversation_id,
                        'conversation_title': conversation.title
                    })
                    
            except Exception as e:
                error = str(e)
                
                # If AJAX request and error, return JSON error
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
                    return JsonResponse({'error': error}, status=500)
        
        context = {
            "form": form, 
            "result": result, 
            "error": error,
            "conversation_id": conversation_id
        }
        return render(request, self.template_name, context)


class SignUpView(View):
    template_name = 'signup.html'

    def get(self, request):
        form = SignUpForm()
        style_form_fields(form)
        next_url = request.GET.get('next', '')
        return render(request, self.template_name, {'form': form, 'next': next_url})

    def post(self, request):
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            # After signup, redirect user to login page instead of auto-login
            next_url = request.POST.get('next') or request.GET.get('next')
            login_url = reverse('login')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(f"{login_url}?next={next_url}")
            return redirect(login_url)
        # If form is invalid, render signup with safe next value
        next_url = request.POST.get('next') or request.GET.get('next', '')
        style_form_fields(form)
        return render(request, self.template_name, {'form': form, 'next': next_url})


class LoginView(View):
    template_name = 'login.html'

    def get(self, request):
        form = AuthenticationForm()
        style_form_fields(form)
        next_url = request.GET.get('next', '')
        return render(request, self.template_name, {'form': form, 'next': next_url})

    def post(self, request):
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            # Respect next parameter if present and safe
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('index')
        # If form is invalid, render login with safe next value
        next_url = request.POST.get('next') or request.GET.get('next', '')
        style_form_fields(form)
        return render(request, self.template_name, {'form': form, 'next': next_url})


class LogoutView(View):
    """Simple logout view that redirects to login."""
    def get(self, request):
        logout(request)
        return redirect('login')

@method_decorator(csrf_exempt, name='dispatch')
class ChatAPIView(LoginRequiredMixin, View):
    login_url = reverse_lazy('login')
    """AJAX endpoint for chat functionality"""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            # If AJAX/JSON client, return JSON 401, otherwise redirect to login
            content_type = request.headers.get('Content-Type', '')
            accept = request.headers.get('Accept', '')
            if 'application/json' in content_type or 'application/json' in accept or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Authentication required'}, status=401)
            return redirect(f"{reverse('login')}?next={request.get_full_path()}")
        return super().dispatch(request, *args, **kwargs)
    
    def get(self, request, conversation_id=None):
        """Handle GET requests for conversations and messages"""
        path = request.path
        
        if path == '/api/conversations/':
            # Return list of conversations for the user
            conversations = ChatConversation.objects.filter(user=request.user).values(
                'id', 'title', 'created_at', 'updated_at'
            )
            return JsonResponse(list(conversations), safe=False)
        
        elif conversation_id and 'messages' in path:
            # Return messages for a conversation
            conversation = get_object_or_404(ChatConversation, id=conversation_id, user=request.user)
            messages = conversation.messages.values(
                'id', 'role', 'content', 'image_url', 'model_used', 'task_type', 'response_time', 'created_at'
            ).order_by('created_at')  # Chronological order for display
            return JsonResponse(list(messages), safe=False)
        
        elif conversation_id:
            # Return conversation details
            conversation = get_object_or_404(ChatConversation, id=conversation_id, user=request.user)
            return JsonResponse({
                'id': conversation.id,
                'title': conversation.title,
                'created_at': conversation.created_at,
                'updated_at': conversation.updated_at
            })
        
        return JsonResponse({'error': 'Invalid endpoint'}, status=404)
    
    def delete(self, request, conversation_id=None):
        """Handle DELETE requests for conversations"""
        if conversation_id:
            try:
                conversation = get_object_or_404(ChatConversation, id=conversation_id, user=request.user)
                conversation.delete()
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)
        return JsonResponse({'error': 'Conversation ID required'}, status=400)
    
    def post(self, request, conversation_id=None):
        try:
            data = json.loads(request.body)
            prompt = data.get('prompt', '')
            image_url = data.get('image_url') or None
            
            if not prompt.strip():
                return JsonResponse({'error': 'Prompt is required'}, status=400)
            
            # Get or create conversation
            if conversation_id:
                conversation = get_object_or_404(ChatConversation, id=conversation_id, user=request.user)
            else:
                # Create new conversation with title based on prompt
                title = prompt[:50] + ('...' if len(prompt) > 50 else '')
                conversation = ChatConversation.objects.create(
                    user=request.user,
                    title=title
                )
                conversation_id = conversation.id
            
            # Save user message
            user_message = ChatMessage.objects.create(
                conversation=conversation,
                role='user',
                content=prompt,
                image_url=image_url
            )
            
            # Generate AI response
            result = generate_response(prompt=prompt, image_url=image_url)
            
            # Save assistant message
            assistant_message = ChatMessage.objects.create(
                conversation=conversation,
                role='assistant',
                content=result['assistant_text'],
                model_used=result['model'],
                task_type=result['task_type'],
                response_time=result.get('response_time', 1.0)
            )
            
            # Update conversation timestamp
            conversation.save()  # This will update updated_at
            
            return JsonResponse({
                'success': True,
                'assistant_text': result['assistant_text'],
                'model': result['model'],
                'task_type': result['task_type'],
                'response_time': result.get('response_time', 1.0),
                'conversation_id': conversation_id,
                'conversation_title': conversation.title
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


class ImageGenerationView(LoginRequiredMixin, View):
    """Main view for image generation"""
    template_name = 'image_generation.html'
    login_url = reverse_lazy('login')
    
    def get(self, request):
        form = ImageGenerationForm()
        
        # Get user's recent image requests
        recent_requests = ImageGenerationRequest.objects.filter(
            user=request.user
        ).select_related().prefetch_related('images')[:10]
        
        return render(request, self.template_name, {
            'form': form,
            'recent_requests': recent_requests
        })
    
    def post(self, request):
        form = ImageGenerationForm(request.POST)
        
        if form.is_valid():
            try:
                # Create image generation request
                with transaction.atomic():
                    image_request = ImageGenerationRequest.objects.create(
                        user=request.user,
                        prompt=form.cleaned_data['prompt'],
                        negative_prompt=form.cleaned_data.get('negative_prompt'),
                        width=form.cleaned_data['width'],
                        height=form.cleaned_data['height'],
                        steps=form.cleaned_data['steps'],
                        cfg_scale=form.cleaned_data['cfg_scale'],
                        samples=form.cleaned_data['samples'],
                        style_preset=form.cleaned_data.get('style_preset'),
                        seed=form.cleaned_data.get('seed'),
                        status='processing'
                    )
                
                # Generate the image
                try:
                    result = generate_image(
                        prompt=form.cleaned_data['prompt'],
                        negative_prompt=form.cleaned_data.get('negative_prompt'),
                        width=form.cleaned_data['width'],
                        height=form.cleaned_data['height'],
                        steps=form.cleaned_data['steps'],
                        cfg_scale=form.cleaned_data['cfg_scale'],
                        samples=form.cleaned_data['samples'],
                        style_preset=form.cleaned_data.get('style_preset'),
                        seed=form.cleaned_data.get('seed')
                    )
                    
                    # Update request with results
                    with transaction.atomic():
                        image_request.status = 'completed'
                        image_request.generation_time = result['generation_time']
                        image_request.model_used = result['model']
                        image_request.cached = result['cached']
                        image_request.save()
                        
                        # Save generated images
                        for image_data in result['images']:
                            GeneratedImage.objects.create(
                                request=image_request,
                                image_data=image_data['base64'],
                                seed_used=image_data.get('seed'),
                                finish_reason=image_data.get('finish_reason'),
                                file_size=len(base64.b64decode(image_data['base64']))
                            )
                        
                        # Update user preferences/stats
                        preferences, created = UserImagePreferences.objects.get_or_create(
                            user=request.user
                        )
                        preferences.update_stats(result['generation_time'], len(result['images']))
                    
                    return redirect('image_result', request_id=image_request.id)
                    
                except Exception as e:
                    # Update request with error
                    image_request.status = 'failed'
                    image_request.error_message = str(e)
                    image_request.save()
                    
                    form.add_error(None, f"Image generation failed: {str(e)}")
                    
            except Exception as e:
                form.add_error(None, f"Request creation failed: {str(e)}")
        
        # Get recent requests for context
        recent_requests = ImageGenerationRequest.objects.filter(
            user=request.user
        ).select_related().prefetch_related('images')[:10]
        
        return render(request, self.template_name, {
            'form': form,
            'recent_requests': recent_requests
        })


class QuickImageView(LoginRequiredMixin, View):
    """Quick image generation with minimal options"""
    template_name = 'quick_image.html'
    login_url = reverse_lazy('login')
    
    def get(self, request):
        form = QuickImageForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = QuickImageForm(request.POST)
        
        if form.is_valid():
            try:
                # Create and process request
                with transaction.atomic():
                    image_request = ImageGenerationRequest.objects.create(
                        user=request.user,
                        prompt=form.cleaned_data['prompt'],
                        style_preset=form.cleaned_data.get('style'),
                        status='processing'
                    )
                
                # Generate image with default settings
                result = generate_image(
                    prompt=form.cleaned_data['prompt'],
                    style_preset=form.cleaned_data.get('style') or None
                )
                
                # Save results
                with transaction.atomic():
                    image_request.status = 'completed'
                    image_request.generation_time = result['generation_time']
                    image_request.model_used = result['model']
                    image_request.cached = result['cached']
                    image_request.save()
                    
                    for image_data in result['images']:
                        GeneratedImage.objects.create(
                            request=image_request,
                            image_data=image_data['base64'],
                            seed_used=image_data.get('seed'),
                            finish_reason=image_data.get('finish_reason'),
                            file_size=len(base64.b64decode(image_data['base64']))
                        )
                
                return redirect('image_result', request_id=image_request.id)
                
            except Exception as e:
                form.add_error(None, f"Image generation failed: {str(e)}")
        
        return render(request, self.template_name, {'form': form})


@method_decorator(csrf_exempt, name='dispatch')
class ImageGenerationAPIView(LoginRequiredMixin, View):
    """AJAX API for image generation"""
    login_url = reverse_lazy('login')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            prompt = data.get('prompt', '').strip()
            
            if not prompt:
                return JsonResponse({'error': 'Prompt is required'}, status=400)
            
            # Create request record
            with transaction.atomic():
                image_request = ImageGenerationRequest.objects.create(
                    user=request.user,
                    prompt=prompt,
                    negative_prompt=data.get('negative_prompt'),
                    width=data.get('width', 1024),
                    height=data.get('height', 1024),
                    steps=data.get('steps', 30),
                    cfg_scale=data.get('cfg_scale', 7.0),
                    samples=data.get('samples', 1),
                    style_preset=data.get('style_preset'),
                    seed=data.get('seed'),
                    status='processing'
                )
            
            # Generate image
            result = generate_image(
                prompt=prompt,
                negative_prompt=data.get('negative_prompt'),
                width=data.get('width', 1024),
                height=data.get('height', 1024),
                steps=data.get('steps', 30),
                cfg_scale=data.get('cfg_scale', 7.0),
                samples=data.get('samples', 1),
                style_preset=data.get('style_preset'),
                seed=data.get('seed')
            )
            
            # Save results
            with transaction.atomic():
                image_request.status = 'completed'
                image_request.generation_time = result['generation_time']
                image_request.model_used = result['model']
                image_request.cached = result['cached']
                image_request.save()
                
                images = []
                for image_data in result['images']:
                    img = GeneratedImage.objects.create(
                        request=image_request,
                        image_data=image_data['base64'],
                        seed_used=image_data.get('seed'),
                        finish_reason=image_data.get('finish_reason'),
                        file_size=len(base64.b64decode(image_data['base64']))
                    )
                    images.append({
                        'id': img.id,
                        'url': img.image_url,
                        'seed': img.seed_used
                    })
            
            return JsonResponse({
                'success': True,
                'request_id': image_request.id,
                'images': images,
                'generation_time': result['generation_time'],
                'model': result['model'],
                'cached': result['cached']
            })
            
        except Exception as e:
            # Update request if it was created
            if 'image_request' in locals():
                image_request.status = 'failed'
                image_request.error_message = str(e)
                image_request.save()
            
            return JsonResponse({'error': str(e)}, status=500)


class ImageResultView(LoginRequiredMixin, View):
    """View to display image generation results"""
    template_name = 'image_result.html'
    login_url = reverse_lazy('login')
    
    def get(self, request, request_id):
        image_request = get_object_or_404(
            ImageGenerationRequest.objects.prefetch_related('images'),
            id=request_id,
            user=request.user
        )
        
        return render(request, self.template_name, {
            'image_request': image_request,
            'images': image_request.images.all()
        })


class ImageGalleryView(LoginRequiredMixin, View):
    """View to display user's image gallery"""
    template_name = 'image_gallery.html'
    login_url = reverse_lazy('login')
    
    def get(self, request):
        # Get user's image requests with pagination
        requests_list = ImageGenerationRequest.objects.filter(
            user=request.user,
            status='completed'
        ).prefetch_related('images').order_by('-created_at')
        
        paginator = Paginator(requests_list, 12)  # 12 requests per page
        page_number = request.GET.get('page')
        requests = paginator.get_page(page_number)
        
        # Get user stats
        user_preferences, _ = UserImagePreferences.objects.get_or_create(
            user=request.user
        )
        
        context = {
            'requests': requests,
            'user_preferences': user_preferences,
            'total_requests': requests_list.count()
        }
        
        return render(request, self.template_name, context)


class ImageUpscaleView(LoginRequiredMixin, View):
    """View for upscaling images"""
    login_url = reverse_lazy('login')
    
    def post(self, request):
        form = ImageUpscaleForm(request.POST)
        
        if form.is_valid():
            try:
                image_id = form.cleaned_data['image_id']
                target_size = form.cleaned_data['target_size']
                
                # Get the original image
                original_image = get_object_or_404(
                    GeneratedImage.objects.select_related('request'),
                    id=image_id,
                    request__user=request.user
                )
                
                # Create upscale request
                upscale_request = ImageUpscaleRequest.objects.create(
                    user=request.user,
                    original_image=original_image,
                    status='processing'
                )
                
                try:
                    # Perform upscaling
                    result = upscale_image(original_image.image_data)
                    
                    # Save result
                    upscale_request.status = 'completed'
                    upscale_request.processing_time = result['generation_time']
                    upscale_request.upscaled_image_data = result['images'][0]['base64']
                    upscale_request.save()
                    
                    return JsonResponse({
                        'success': True,
                        'upscale_id': upscale_request.id,
                        'upscaled_url': upscale_request.upscaled_image_url,
                        'processing_time': result['generation_time']
                    })
                    
                except Exception as e:
                    upscale_request.status = 'failed'
                    upscale_request.error_message = str(e)
                    upscale_request.save()
                    raise e
                    
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)
        
        return JsonResponse({'error': 'Invalid form data'}, status=400)


class ImageMetricsView(LoginRequiredMixin, View):
    """View to get image generation metrics"""
    login_url = reverse_lazy('login')
    
    def get(self, request):
        # Get system metrics
        system_metrics = get_image_metrics()
        
        # Get user metrics
        user_requests = ImageGenerationRequest.objects.filter(user=request.user)
        user_metrics = {
            'total_requests': user_requests.count(),
            'completed_requests': user_requests.filter(status='completed').count(),
            'failed_requests': user_requests.filter(status='failed').count(),
            'total_images': GeneratedImage.objects.filter(request__user=request.user).count(),
            'avg_generation_time': user_requests.filter(
                generation_time__isnull=False
            ).aggregate(
                avg_time=Avg('generation_time')
            )['avg_time'] or 0
        }
        
        return JsonResponse({
            'system_metrics': system_metrics,
            'user_metrics': user_metrics
        })


@method_decorator(csrf_exempt, name='dispatch')
class VideoGenerationAPIView(LoginRequiredMixin, View):
    """AJAX API for video generation"""
    login_url = reverse_lazy('login')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            prompt = data.get('prompt', '').strip()
            
            if not prompt:
                return JsonResponse({'error': 'Prompt is required'}, status=400)
            
            if len(prompt) > 500:
                return JsonResponse({'error': 'Prompt too long (max 500 characters)'}, status=400)
            
            # Create request record
            with transaction.atomic():
                video_request = VideoGenerationRequest.objects.create(
                    user=request.user,
                    prompt=prompt,
                    model=data.get('model', 'ali-vilab/text-to-video-ms-1.7b'),
                    duration=data.get('duration'),
                    fps=data.get('fps'),
                    width=data.get('width'),
                    height=data.get('height'),
                    status='processing'
                )
            
            # Generate video with timeout
            result = generate_video(
                prompt=prompt,
                model=data.get('model', 'ali-vilab/text-to-video-ms-1.7b'),
                duration=data.get('duration'),
                fps=data.get('fps'),
                width=data.get('width'),
                height=data.get('height'),
                timeout=90  # 90 seconds timeout for API calls
            )
            
            if result['success']:
                # Save results
                with transaction.atomic():
                    video_request.status = 'completed'
                    video_request.generation_time = result['generation_time']
                    video_request.cached = result.get('cached', False)
                    video_request.save()
                    
                    # Create generated video record
                    video = GeneratedVideo.objects.create(
                        request=video_request,
                        video_data=result['video_data'],
                        file_size=result.get('file_size'),
                        mime_type=result.get('mime_type', 'video/mp4')
                    )
                    
                    # Update user preferences/stats
                    try:
                        preferences, created = UserVideoPreferences.objects.get_or_create(
                            user=request.user
                        )
                        preferences.update_stats(result['generation_time'])
                    except Exception:
                        pass  # Continue even if stats update fails
                
                return JsonResponse({
                    'success': True,
                    'request_id': video_request.id,
                    'video': {
                        'id': video.id,
                        'url': video.video_url,
                        'file_size': video.file_size
                    },
                    'generation_time': result['generation_time'],
                    'model': data.get('model', 'ali-vilab/text-to-video-ms-1.7b'),
                    'cached': result.get('cached', False)
                })
            else:
                # Handle generation error
                video_request.status = 'failed'
                video_request.error_message = result.get('error', 'Unknown error occurred')
                video_request.generation_time = result.get('generation_time', 0)
                video_request.save()
                
                return JsonResponse({
                    'success': False,
                    'error': result.get('error', 'Video generation failed'),
                    'request_id': video_request.id
                }, status=500)
                
        except Exception as e:
            # Update request if it was created
            if 'video_request' in locals():
                video_request.status = 'failed'
                video_request.error_message = str(e)
                video_request.save()
            
            return JsonResponse({'error': str(e)}, status=500)


class VideoGenerationView(LoginRequiredMixin, View):
    """Main view for video generation"""
    template_name = 'video_generation.html'
    login_url = reverse_lazy('login')
    
    def get(self, request):
        form = VideoGenerationForm()
        
        # Get user's recent video requests
        recent_requests = VideoGenerationRequest.objects.filter(
            user=request.user
        ).select_related().prefetch_related('videos')[:10]
        
        return render(request, self.template_name, {
            'form': form,
            'recent_requests': recent_requests
        })
    
    def post(self, request):
        form = VideoGenerationForm(request.POST)
        
        if form.is_valid():
            try:
                # Create video generation request
                with transaction.atomic():
                    video_request = VideoGenerationRequest.objects.create(
                        user=request.user,
                        prompt=form.cleaned_data['prompt'],
                        model=form.cleaned_data['model'],
                        duration=form.cleaned_data.get('duration'),
                        fps=form.cleaned_data.get('fps'),
                        width=form.cleaned_data.get('width'),
                        height=form.cleaned_data.get('height'),
                        status='processing'
                    )
                
                # Generate the video with shorter timeout for better UX
                try:
                    result = generate_video(
                        prompt=form.cleaned_data['prompt'],
                        model=form.cleaned_data['model'],
                        duration=form.cleaned_data.get('duration'),
                        fps=form.cleaned_data.get('fps'),
                        width=form.cleaned_data.get('width'),
                        height=form.cleaned_data.get('height'),
                        timeout=90  # 90 seconds timeout instead of default 120
                    )
                    
                    if result['success']:
                        # Save successful result
                        video_request.status = 'completed'
                        video_request.generation_time = result['generation_time']
                        video_request.cached = result.get('cached', False)
                        video_request.save()
                        
                        # Create generated video record
                        generated_video = GeneratedVideo.objects.create(
                            request=video_request,
                            video_data=result['video_data'],
                            file_size=result.get('file_size'),
                            mime_type=result.get('mime_type', 'video/mp4')
                        )
                        
                        # Update user preferences/stats
                        try:
                            preferences, created = UserVideoPreferences.objects.get_or_create(
                                user=request.user
                            )
                            preferences.update_stats(result['generation_time'])
                        except Exception:
                            pass  # Continue even if stats update fails
                        
                        # Redirect to result view
                        return redirect('video_result', request_id=video_request.id)
                    
                    else:
                        # Handle generation error
                        video_request.status = 'failed'
                        video_request.error_message = result.get('error', 'Unknown error occurred')
                        video_request.generation_time = result.get('generation_time', 0)
                        video_request.save()
                        
                        form.add_error(None, f"Video generation failed: {result.get('error', 'Unknown error')}")
                
                except Exception as e:
                    # Handle unexpected errors
                    video_request.status = 'failed'
                    video_request.error_message = str(e)
                    video_request.save()
                    form.add_error(None, f"An error occurred: {str(e)}")
                    
            except Exception as e:
                form.add_error(None, f"Failed to create video request: {str(e)}")
        
        # Get recent requests for re-rendering
        recent_requests = VideoGenerationRequest.objects.filter(
            user=request.user
        ).select_related().prefetch_related('videos')[:10]
        
        return render(request, self.template_name, {
            'form': form,
            'recent_requests': recent_requests
        })


class QuickVideoView(LoginRequiredMixin, View):
    """Quick video generation with minimal parameters"""
    template_name = 'quick_video.html'
    login_url = reverse_lazy('login')
    
    def get(self, request):
        form = QuickVideoForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = QuickVideoForm(request.POST)
        
        if form.is_valid():
            try:
                # Create video generation request with default parameters
                with transaction.atomic():
                    video_request = VideoGenerationRequest.objects.create(
                        user=request.user,
                        prompt=form.cleaned_data['prompt'],
                        model="ali-vilab/text-to-video-ms-1.7b",  # Default model
                        status='processing'
                    )
                
                # Generate the video with default settings and faster timeout
                result = generate_video(
                    prompt=form.cleaned_data['prompt'],
                    timeout=60  # 1 minute timeout for quick generation
                )
                
                if result['success']:
                    # Save successful result
                    video_request.status = 'completed'
                    video_request.generation_time = result['generation_time']
                    video_request.cached = result.get('cached', False)
                    video_request.save()
                    
                    # Create generated video record
                    generated_video = GeneratedVideo.objects.create(
                        request=video_request,
                        video_data=result['video_data'],
                        file_size=result.get('file_size'),
                        mime_type=result.get('mime_type', 'video/mp4')
                    )
                    
                    # Redirect to result
                    return redirect('video_result', request_id=video_request.id)
                else:
                    # Handle error
                    video_request.status = 'failed'
                    video_request.error_message = result.get('error', 'Unknown error')
                    video_request.save()
                    form.add_error(None, f"Video generation failed: {result.get('error')}")
                    
            except Exception as e:
                form.add_error(None, f"An error occurred: {str(e)}")
        
        return render(request, self.template_name, {'form': form})


class VideoResultView(LoginRequiredMixin, View):
    """View for displaying video generation results"""
    template_name = 'video_result.html'
    login_url = reverse_lazy('login')
    
    def get(self, request, request_id):
        video_request = get_object_or_404(
            VideoGenerationRequest.objects.select_related('user').prefetch_related('videos'),
            id=request_id,
            user=request.user
        )
        
        return render(request, self.template_name, {
            'video_request': video_request,
            'videos': video_request.videos.all()
        })


class VideoGalleryView(LoginRequiredMixin, View):
    """View for displaying user's video gallery"""
    template_name = 'video_gallery.html'
    login_url = reverse_lazy('login')
    
    def get(self, request):
        # Get user's video requests with pagination
        video_requests = VideoGenerationRequest.objects.filter(
            user=request.user,
            status='completed'
        ).select_related().prefetch_related('videos').order_by('-created_at')
        
        paginator = Paginator(video_requests, 12)  # Show 12 videos per page
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        return render(request, self.template_name, {
            'page_obj': page_obj,
            'video_requests': page_obj.object_list
        })


class VideoMetricsView(LoginRequiredMixin, View):
    """API view for video generation metrics"""
    
    def get(self, request):
        # Get system metrics
        system_metrics = get_video_metrics()
        
        # Get user-specific metrics
        user_requests = VideoGenerationRequest.objects.filter(user=request.user)
        user_metrics = {
            'total_requests': user_requests.count(),
            'completed_requests': user_requests.filter(status='completed').count(),
            'failed_requests': user_requests.filter(status='failed').count(),
            'total_videos': GeneratedVideo.objects.filter(request__user=request.user).count(),
            'avg_generation_time': user_requests.filter(
                generation_time__isnull=False
            ).aggregate(
                avg_time=Avg('generation_time')
            )['avg_time'] or 0
        }
        
        return JsonResponse({
            'system_metrics': system_metrics,
            'user_metrics': user_metrics
        })


class AudioGenerationView(LoginRequiredMixin, View):
    """Main view for audio generation"""
    template_name = 'audio_generation.html'
    login_url = reverse_lazy('login')
    
    def get(self, request):
        form = AudioGenerationForm()
        
        # Get user's recent audio requests
        recent_requests = AudioGenerationRequest.objects.filter(
            user=request.user
        ).select_related().prefetch_related('audio_files')[:10]
        
        return render(request, self.template_name, {
            'form': form,
            'recent_requests': recent_requests
        })
    
    def post(self, request):
        form = AudioGenerationForm(request.POST)
        
        if form.is_valid():
            try:
                # Create audio generation request
                with transaction.atomic():
                    audio_request = AudioGenerationRequest.objects.create(
                        user=request.user,
                        text=form.cleaned_data['text'],
                        voice_id=form.cleaned_data.get('voice_id'),
                        model=form.cleaned_data['model'],
                        stability=form.cleaned_data['stability'],
                        similarity_boost=form.cleaned_data['similarity_boost'],
                        style=form.cleaned_data['style'],
                        use_speaker_boost=form.cleaned_data['use_speaker_boost'],
                        character_count=len(form.cleaned_data['text']),
                        status='processing'
                    )
                
                # Generate the audio
                try:
                    result = generate_audio(
                        text=form.cleaned_data['text'],
                        voice_id=form.cleaned_data.get('voice_id'),
                        model=form.cleaned_data['model'],
                        stability=form.cleaned_data['stability'],
                        similarity_boost=form.cleaned_data['similarity_boost'],
                        style=form.cleaned_data['style'],
                        use_speaker_boost=form.cleaned_data['use_speaker_boost'],
                        timeout=60
                    )
                    
                    if result['success']:
                        # Save successful result
                        audio_request.status = 'completed'
                        audio_request.generation_time = result['generation_time']
                        audio_request.model_used = result.get('model', form.cleaned_data['model'])
                        audio_request.cached = result.get('cached', False)
                        audio_request.save()
                        
                        # Create generated audio record
                        generated_audio = GeneratedAudio.objects.create(
                            request=audio_request,
                            audio_data=result['audio_data'],
                            file_size=result.get('file_size'),
                            mime_type=result.get('mime_type', 'audio/mpeg'),
                            duration=result.get('duration')
                        )
                        
                        # Update user preferences/stats
                        try:
                            preferences, created = UserAudioPreferences.objects.get_or_create(
                                user=request.user
                            )
                            preferences.update_stats(
                                result['generation_time'],
                                len(form.cleaned_data['text'])
                            )
                        except Exception:
                            pass  # Continue even if stats update fails
                        
                        # Redirect to result view
                        return redirect('audio_result', request_id=audio_request.id)
                    
                    else:
                        # Handle generation error
                        audio_request.status = 'failed'
                        audio_request.error_message = result.get('error', 'Unknown error occurred')
                        audio_request.generation_time = result.get('generation_time', 0)
                        audio_request.save()
                        
                        form.add_error(None, f"Audio generation failed: {result.get('error', 'Unknown error')}")
                
                except Exception as e:
                    # Handle unexpected errors
                    audio_request.status = 'failed'
                    audio_request.error_message = str(e)
                    audio_request.save()
                    form.add_error(None, f"An error occurred: {str(e)}")
                    
            except Exception as e:
                form.add_error(None, f"Failed to create audio request: {str(e)}")
        
        # Get recent requests for re-rendering
        recent_requests = AudioGenerationRequest.objects.filter(
            user=request.user
        ).select_related().prefetch_related('audio_files')[:10]
        
        return render(request, self.template_name, {
            'form': form,
            'recent_requests': recent_requests
        })


class QuickAudioView(LoginRequiredMixin, View):
    """Quick audio generation with minimal parameters"""
    template_name = 'quick_audio.html'
    login_url = reverse_lazy('login')
    
    def get(self, request):
        form = QuickAudioForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = QuickAudioForm(request.POST)
        
        if form.is_valid():
            try:
                # Create audio generation request with default parameters
                with transaction.atomic():
                    audio_request = AudioGenerationRequest.objects.create(
                        user=request.user,
                        text=form.cleaned_data['text'],
                        voice_id=form.cleaned_data['voice'],
                        model="microsoft/speecht5_tts",  # Default model
                        character_count=len(form.cleaned_data['text']),
                        status='processing'
                    )
                
                # Generate the audio with default settings
                result = generate_audio(
                    text=form.cleaned_data['text'],
                    voice_id=form.cleaned_data['voice'],
                    timeout=30
                )
                
                if result['success']:
                    # Save successful result
                    audio_request.status = 'completed'
                    audio_request.generation_time = result['generation_time']
                    audio_request.model_used = result.get('model', 'microsoft/speecht5_tts')
                    audio_request.cached = result.get('cached', False)
                    audio_request.save()
                    
                    # Create generated audio record
                    generated_audio = GeneratedAudio.objects.create(
                        request=audio_request,
                        audio_data=result['audio_data'],
                        file_size=result.get('file_size'),
                        mime_type=result.get('mime_type', 'audio/mpeg'),
                        duration=result.get('duration')
                    )
                    
                    # Redirect to result
                    return redirect('audio_result', request_id=audio_request.id)
                else:
                    # Handle error
                    audio_request.status = 'failed'
                    audio_request.error_message = result.get('error', 'Unknown error')
                    audio_request.save()
                    form.add_error(None, f"Audio generation failed: {result.get('error')}")
                    
            except Exception as e:
                form.add_error(None, f"An error occurred: {str(e)}")
        
        return render(request, self.template_name, {'form': form})


@method_decorator(csrf_exempt, name='dispatch')
class AudioGenerationAPIView(LoginRequiredMixin, View):
    """AJAX API for audio generation"""
    login_url = reverse_lazy('login')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            text = data.get('text', '').strip()
            
            if not text:
                return JsonResponse({'error': 'Text is required'}, status=400)
            
            # Create request record
            with transaction.atomic():
                audio_request = AudioGenerationRequest.objects.create(
                    user=request.user,
                    text=text,
                    voice_id=data.get('voice_id'),
                    model=data.get('model', 'microsoft/speecht5_tts'),
                    stability=data.get('stability', 0.5),
                    similarity_boost=data.get('similarity_boost', 0.5),
                    style=data.get('style', 0.0),
                    use_speaker_boost=data.get('use_speaker_boost', True),
                    character_count=len(text),
                    status='processing'
                )
            
            # Generate audio
            result = generate_audio(
                text=text,
                voice_id=data.get('voice_id'),
                model=data.get('model', 'microsoft/speecht5_tts'),
                stability=data.get('stability', 0.5),
                similarity_boost=data.get('similarity_boost', 0.5),
                style=data.get('style', 0.0),
                use_speaker_boost=data.get('use_speaker_boost', True),
                timeout=60
            )
            
            if result['success']:
                # Save results
                with transaction.atomic():
                    audio_request.status = 'completed'
                    audio_request.generation_time = result['generation_time']
                    audio_request.model_used = result.get('model', data.get('model', 'microsoft/speecht5_tts'))
                    audio_request.cached = result.get('cached', False)
                    audio_request.save()
                    
                    audio = GeneratedAudio.objects.create(
                        request=audio_request,
                        audio_data=result['audio_data'],
                        file_size=result.get('file_size'),
                        mime_type=result.get('mime_type', 'audio/mpeg'),
                        duration=result.get('duration')
                    )
                    
                    # Update user preferences/stats
                    try:
                        preferences, created = UserAudioPreferences.objects.get_or_create(
                            user=request.user
                        )
                        preferences.update_stats(result['generation_time'], len(text))
                    except Exception:
                        pass
                
                return JsonResponse({
                    'success': True,
                    'request_id': audio_request.id,
                    'audio': {
                        'id': audio.id,
                        'url': audio.audio_url,
                        'duration': audio.duration,
                        'file_size': audio.file_size
                    },
                    'generation_time': result['generation_time'],
                    'model': audio_request.model_used,
                    'cached': result.get('cached', False)
                })
            else:
                # Handle generation error
                audio_request.status = 'failed'
                audio_request.error_message = result.get('error', 'Unknown error occurred')
                audio_request.generation_time = result.get('generation_time', 0)
                audio_request.save()
                
                return JsonResponse({
                    'success': False,
                    'error': result.get('error', 'Audio generation failed'),
                    'request_id': audio_request.id
                }, status=500)
                
        except Exception as e:
            # Update request if it was created
            if 'audio_request' in locals():
                audio_request.status = 'failed'
                audio_request.error_message = str(e)
                audio_request.save()
            
            return JsonResponse({'error': str(e)}, status=500)


class AudioResultView(LoginRequiredMixin, View):
    """View for displaying audio generation results"""
    template_name = 'audio_result.html'
    login_url = reverse_lazy('login')
    
    def get(self, request, request_id):
        audio_request = get_object_or_404(
            AudioGenerationRequest.objects.select_related('user').prefetch_related('audio_files'),
            id=request_id,
            user=request.user
        )
        
        return render(request, self.template_name, {
            'audio_request': audio_request,
            'audio_files': audio_request.audio_files.all()
        })


class AudioGalleryView(LoginRequiredMixin, View):
    """View for displaying user's audio gallery"""
    template_name = 'audio_gallery.html'
    login_url = reverse_lazy('login')
    
    def get(self, request):
        # Get user's audio requests with pagination
        audio_requests = AudioGenerationRequest.objects.filter(
            user=request.user,
            status='completed'
        ).select_related().prefetch_related('audio_files').order_by('-created_at')
        
        paginator = Paginator(audio_requests, 12)  # Show 12 audio files per page
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        return render(request, self.template_name, {
            'page_obj': page_obj,
            'audio_requests': page_obj.object_list
        })


class AudioMetricsView(LoginRequiredMixin, View):
    """API view for audio generation metrics"""
    
    def get(self, request):
        # Get system metrics
        system_metrics = get_audio_metrics()
        
        # Get user-specific metrics
        user_requests = AudioGenerationRequest.objects.filter(user=request.user)
        user_metrics = {
            'total_requests': user_requests.count(),
            'completed_requests': user_requests.filter(status='completed').count(),
            'failed_requests': user_requests.filter(status='failed').count(),
            'total_audio_files': GeneratedAudio.objects.filter(request__user=request.user).count(),
            'avg_generation_time': user_requests.filter(
                generation_time__isnull=False
            ).aggregate(
                avg_time=Avg('generation_time')
            )['avg_time'] or 0,
            'total_characters_processed': user_requests.aggregate(
                total_chars=Sum('character_count')
            )['total_chars'] or 0
        }
        
        return JsonResponse({
            'system_metrics': system_metrics,
            'user_metrics': user_metrics
        })


# ==================== PRESENTATION VIEWS ====================

class PresentationGenerationView(LoginRequiredMixin, View):
    """Main view for presentation generation"""
    template_name = 'presentation_generation.html'
    login_url = reverse_lazy('login')
    
    def get(self, request):
        form = PresentationGenerationForm()
        
        # Get user's recent presentation requests
        recent_requests = PresentationProject.objects.filter(
            user=request.user
        ).select_related().prefetch_related('slides')[:10]
        
        # Get available themes and templates
        themes = get_available_themes()
        templates = get_available_templates()
        
        return render(request, self.template_name, {
            'form': form,
            'recent_requests': recent_requests,
            'themes': themes,
            'templates': templates
        })
    
    def post(self, request):
        form = PresentationGenerationForm(request.POST)
        
        if form.is_valid():
            try:
                # Create presentation project
                with transaction.atomic():
                    presentation = PresentationProject.objects.create(
                        user=request.user,
                        title=form.cleaned_data['title'],
                        topic=form.cleaned_data['topic'],
                        description=form.cleaned_data.get('description', ''),
                        target_audience=form.cleaned_data.get('target_audience', ''),
                        presentation_type=form.cleaned_data['presentation_type'],
                        theme=form.cleaned_data['theme'],
                        color_scheme=form.cleaned_data['color_scheme'],
                        tone=form.cleaned_data['tone'],
                        slide_count=form.cleaned_data['slide_count'],
                        include_images=form.cleaned_data['include_images'],
                        include_charts=form.cleaned_data['include_charts'],
                        status='generating'
                    )
                
                # Generate presentation content
                result = generate_presentation(
                    topic=form.cleaned_data['topic'],
                    slide_count=form.cleaned_data['slide_count'],
                    target_audience=form.cleaned_data.get('target_audience'),
                    presentation_type=form.cleaned_data['presentation_type'],
                    tone=form.cleaned_data['tone'],
                    theme=form.cleaned_data['theme'],
                    include_images=form.cleaned_data['include_images'],
                    include_charts=form.cleaned_data['include_charts']
                )
                
                if result['success']:
                    # Save generated slides
                    with transaction.atomic():
                        presentation.status = 'completed'
                        presentation.generation_time = result['generation_time']
                        presentation.model_used = result['model_used']
                        presentation.save()
                        
                        for slide_data in result['slides']:
                            slide = PresentationSlide.objects.create(
                                presentation=presentation,
                                slide_number=slide_data['slide_number'],
                                title=slide_data.get('title', ''),
                                subtitle=slide_data.get('subtitle', ''),
                                content=slide_data.get('main_content', ''),
                                notes=slide_data.get('speaker_notes', ''),
                                slide_type=slide_data.get('slide_type', 'content'),
                                layout=slide_data.get('layout', 'default')
                            )
                            
                            # Create slide elements if bullet points exist
                            if slide_data.get('bullet_points'):
                                SlideElement.objects.create(
                                    slide=slide,
                                    element_type='bullet_list',
                                    content='\n'.join(slide_data['bullet_points']),
                                    position_x=0,
                                    position_y=20,
                                    width=100,
                                    height=60
                                )
                    
                    # Update user preferences
                    prefs, created = UserPresentationPreferences.objects.get_or_create(
                        user=request.user,
                        defaults={
                            'default_theme': form.cleaned_data['theme'],
                            'default_color_scheme': form.cleaned_data['color_scheme'],
                            'default_tone': form.cleaned_data['tone'],
                            'default_slide_count': form.cleaned_data['slide_count'],
                            'default_include_images': form.cleaned_data['include_images'],
                            'default_include_charts': form.cleaned_data['include_charts']
                        }
                    )
                    if not created:
                        prefs.update_stats(result['generation_time'], result['slide_count'])
                    
                    return redirect('presentation_result', presentation_id=presentation.id)
                
                else:
                    # Update presentation with error
                    presentation.status = 'failed'
                    presentation.error_message = result['error']
                    presentation.save()
                    
                    form.add_error(None, f"Generation failed: {result['error']}")
            
            except Exception as e:
                form.add_error(None, f"An error occurred: {str(e)}")
        
        # Get data for re-rendering form
        recent_requests = PresentationProject.objects.filter(user=request.user)[:10]
        themes = get_available_themes()
        templates = get_available_templates()
        
        return render(request, self.template_name, {
            'form': form,
            'recent_requests': recent_requests,
            'themes': themes,
            'templates': templates
        })


class QuickPresentationView(LoginRequiredMixin, View):
    """Quick presentation generation with minimal options"""
    template_name = 'quick_presentation.html'
    login_url = reverse_lazy('login')
    
    def get(self, request):
        form = QuickPresentationForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = QuickPresentationForm(request.POST)
        
        if form.is_valid():
            try:
                # Create and process request
                with transaction.atomic():
                    presentation = PresentationProject.objects.create(
                        user=request.user,
                        title=f"Quick Presentation: {form.cleaned_data['topic'][:50]}",
                        topic=form.cleaned_data['topic'],
                        presentation_type=form.cleaned_data['presentation_type'],
                        slide_count=form.cleaned_data['slide_count'],
                        status='generating'
                    )
                
                # Generate presentation with default settings
                result = generate_presentation(
                    topic=form.cleaned_data['topic'],
                    slide_count=form.cleaned_data['slide_count'],
                    presentation_type=form.cleaned_data['presentation_type']
                )
                
                if result['success']:
                    # Save results
                    with transaction.atomic():
                        presentation.status = 'completed'
                        presentation.generation_time = result['generation_time']
                        presentation.model_used = result['model_used']
                        presentation.save()
                        
                        for slide_data in result['slides']:
                            PresentationSlide.objects.create(
                                presentation=presentation,
                                slide_number=slide_data['slide_number'],
                                title=slide_data.get('title', ''),
                                content=slide_data.get('main_content', ''),
                                notes=slide_data.get('speaker_notes', ''),
                                slide_type=slide_data.get('slide_type', 'content'),
                                layout=slide_data.get('layout', 'default')
                            )
                    
                    return redirect('presentation_result', presentation_id=presentation.id)
                else:
                    presentation.status = 'failed'
                    presentation.error_message = result['error']
                    presentation.save()
                    form.add_error(None, f"Generation failed: {result['error']}")
                    
            except Exception as e:
                form.add_error(None, f"An error occurred: {str(e)}")
        
        return render(request, self.template_name, {'form': form})


@method_decorator(csrf_exempt, name='dispatch')
class PresentationGenerationAPIView(LoginRequiredMixin, View):
    """AJAX API for presentation generation"""
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            
            # Generate presentation
            result = generate_presentation(
                topic=data.get('topic', ''),
                slide_count=data.get('slide_count', 10),
                target_audience=data.get('target_audience'),
                presentation_type=data.get('presentation_type', 'business'),
                tone=data.get('tone', 'professional'),
                theme=data.get('theme', 'modern'),
                include_images=data.get('include_images', True),
                include_charts=data.get('include_charts', True)
            )
            
            if result['success']:
                # Create presentation in database
                with transaction.atomic():
                    presentation = PresentationProject.objects.create(
                        user=request.user,
                        title=data.get('title', f"Presentation: {data.get('topic', 'Untitled')[:50]}"),
                        topic=data.get('topic', ''),
                        presentation_type=data.get('presentation_type', 'business'),
                        theme=data.get('theme', 'modern'),
                        tone=data.get('tone', 'professional'),
                        slide_count=len(result['slides']),
                        status='completed',
                        generation_time=result['generation_time'],
                        model_used=result['model_used']
                    )
                    
                    for slide_data in result['slides']:
                        PresentationSlide.objects.create(
                            presentation=presentation,
                            slide_number=slide_data['slide_number'],
                            title=slide_data.get('title', ''),
                            content=slide_data.get('main_content', ''),
                            notes=slide_data.get('speaker_notes', ''),
                            slide_type=slide_data.get('slide_type', 'content'),
                            layout=slide_data.get('layout', 'default')
                        )
                
                return JsonResponse({
                    'success': True,
                    'presentation_id': presentation.id,
                    'generation_time': result['generation_time'],
                    'slide_count': len(result['slides']),
                    'model_used': result['model_used']
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': result['error']
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })


class PresentationResultView(LoginRequiredMixin, View):
    """View for displaying presentation generation results"""
    template_name = 'presentation_result.html'
    login_url = reverse_lazy('login')
    
    def get(self, request, presentation_id):
        presentation = get_object_or_404(
            PresentationProject.objects.prefetch_related('slides'),
            id=presentation_id,
            user=request.user
        )
        
        slides = presentation.slides.all().order_by('slide_number')
        
        return render(request, self.template_name, {
            'presentation': presentation,
            'slides': slides
        })


class PresentationPreviewView(LoginRequiredMixin, View):
    """View for presentation preview/slideshow"""
    template_name = 'presentation_preview.html'
    login_url = reverse_lazy('login')
    
    def get(self, request, presentation_id):
        presentation = get_object_or_404(
            PresentationProject.objects.prefetch_related('slides__elements'),
            id=presentation_id,
            user=request.user
        )
        
        slides = presentation.slides.all().order_by('slide_number')
        
        return render(request, self.template_name, {
            'presentation': presentation,
            'slides': slides
        })


class PresentationEditView(LoginRequiredMixin, View):
    """View for editing presentations"""
    template_name = 'presentation_edit.html'
    login_url = reverse_lazy('login')
    
    def get(self, request, presentation_id):
        presentation = get_object_or_404(
            PresentationProject,
            id=presentation_id,
            user=request.user
        )
        
        slides = presentation.slides.all().order_by('slide_number')
        
        return render(request, self.template_name, {
            'presentation': presentation,
            'slides': slides
        })
    
    def post(self, request, presentation_id):
        """Handle presentation save"""
        try:
            presentation = get_object_or_404(
                PresentationProject,
                id=presentation_id,
                user=request.user
            )
            
            data = json.loads(request.body)
            slides_data = data.get('slides', [])
            
            # Get existing slides
            existing_slides = {slide.id: slide for slide in presentation.slides.all()}
            updated_slide_ids = set()
            saved_slides = []
            
            # Update or create slides
            for slide_data in slides_data:
                slide_id = slide_data.get('id')
                
                if slide_id and slide_id in existing_slides:
                    # Update existing slide
                    slide = existing_slides[slide_id]
                    updated_slide_ids.add(slide_id)
                else:
                    # Create new slide
                    slide = PresentationSlide(presentation=presentation)
                
                # Update slide fields
                slide.slide_number = slide_data.get('slide_number', 1)
                slide.title = slide_data.get('title', '')
                slide.subtitle = slide_data.get('subtitle', '')
                slide.content = slide_data.get('content', '')
                slide.notes = slide_data.get('notes', '')
                slide.slide_type = slide_data.get('slide_type', 'content')
                slide.layout = slide_data.get('layout', 'default')
                slide.background_color = slide_data.get('background_color')
                slide.text_color = slide_data.get('text_color')
                slide.accent_color = slide_data.get('accent_color')
                
                slide.save()
                updated_slide_ids.add(slide.id)
                
                saved_slides.append({
                    'id': slide.id,
                    'slide_number': slide.slide_number
                })
            
            # Delete slides that were removed
            for slide_id, slide in existing_slides.items():
                if slide_id not in updated_slide_ids:
                    slide.delete()
            
            # Update presentation timestamp
            presentation.updated_at = timezone.now()
            presentation.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Presentation saved successfully',
                'slides': saved_slides
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)


class SlideEditView(LoginRequiredMixin, View):
    """View for editing individual slides"""
    template_name = 'slide_edit.html'
    login_url = reverse_lazy('login')
    
    def get(self, request, presentation_id, slide_id):
        presentation = get_object_or_404(
            PresentationProject,
            id=presentation_id,
            user=request.user
        )
        
        slide = get_object_or_404(
            PresentationSlide,
            id=slide_id,
            presentation=presentation
        )
        
        form = SlideEditForm(initial={
            'title': slide.title,
            'subtitle': slide.subtitle,
            'content': slide.content,
            'notes': slide.notes,
            'slide_type': slide.slide_type,
            'layout': slide.layout
        })
        
        return render(request, self.template_name, {
            'presentation': presentation,
            'slide': slide,
            'form': form
        })
    
    def post(self, request, presentation_id, slide_id):
        """Handle slide update via JSON or form data"""
        try:
            presentation = get_object_or_404(
                PresentationProject,
                id=presentation_id,
                user=request.user
            )
            
            slide = get_object_or_404(
                PresentationSlide,
                id=slide_id,
                presentation=presentation
            )
            
            # Check if request is JSON (from Alpine.js) or form data
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                
                # Update slide fields from JSON
                slide.title = data.get('title', slide.title)
                slide.subtitle = data.get('subtitle', '')
                slide.content = data.get('content', '')
                slide.notes = data.get('notes', '')
                slide.slide_type = data.get('slide_type', slide.slide_type)
                slide.layout = data.get('layout', slide.layout)
                slide.background_color = data.get('background_color')
                slide.text_color = data.get('text_color')
                slide.accent_color = data.get('accent_color')
                
                slide.save()
                
                # Update presentation timestamp
                presentation.updated_at = timezone.now()
                presentation.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Slide saved successfully',
                    'slide': {
                        'id': slide.id,
                        'title': slide.title,
                        'slide_number': slide.slide_number
                    }
                })
            else:
                # Handle traditional form submission
                form = SlideEditForm(request.POST)
                
                if form.is_valid():
                    slide.title = form.cleaned_data['title']
                    slide.subtitle = form.cleaned_data['subtitle']
                    slide.content = form.cleaned_data['content']
                    slide.notes = form.cleaned_data['notes']
                    slide.slide_type = form.cleaned_data['slide_type']
                    slide.layout = form.cleaned_data['layout']
                    slide.save()
                    
                    return redirect('presentation_edit', presentation_id=presentation.id)
                
                return render(request, self.template_name, {
                    'presentation': presentation,
                    'slide': slide,
                    'form': form
                })
                
        except Exception as e:
            if request.content_type == 'application/json':
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                }, status=400)
            else:
                # Handle form error
                return render(request, self.template_name, {
                    'presentation': presentation,
                    'slide': slide,
                    'form': form,
                    'error': str(e)
                })


class PresentationGalleryView(LoginRequiredMixin, View):
    """View to display user's presentation gallery"""
    template_name = 'presentation_gallery.html'
    login_url = reverse_lazy('login')
    
    def get(self, request):
        presentations = PresentationProject.objects.filter(
            user=request.user
        ).prefetch_related('slides').order_by('-updated_at')
        
        # Pagination
        paginator = Paginator(presentations, 12)  # 12 presentations per page
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        return render(request, self.template_name, {
            'page_obj': page_obj,
            'presentations': page_obj.object_list
        })


class PresentationShareView(LoginRequiredMixin, View):
    """View for sharing presentations"""
    template_name = 'presentation_share.html'
    login_url = reverse_lazy('login')
    
    def get(self, request, presentation_id):
        presentation = get_object_or_404(
            PresentationProject,
            id=presentation_id,
            user=request.user
        )
        
        form = PresentationShareForm(initial={
            'is_public': presentation.is_public,
            'generate_link': bool(presentation.share_token)
        })
        
        return render(request, self.template_name, {
            'presentation': presentation,
            'form': form
        })
    
    def post(self, request, presentation_id):
        presentation = get_object_or_404(
            PresentationProject,
            id=presentation_id,
            user=request.user
        )
        
        form = PresentationShareForm(request.POST)
        
        if form.is_valid():
            presentation.is_public = form.cleaned_data['is_public']
            
            if form.cleaned_data['generate_link'] and not presentation.share_token:
                presentation.generate_share_token()
            elif not form.cleaned_data['generate_link']:
                presentation.share_token = None
            
            presentation.save()
            
            return render(request, self.template_name, {
                'presentation': presentation,
                'form': form,
                'success': True
            })
        
        return render(request, self.template_name, {
            'presentation': presentation,
            'form': form
        })


class PresentationExportView(LoginRequiredMixin, View):
    """View for exporting presentations"""
    template_name = 'presentation_export.html'
    login_url = reverse_lazy('login')
    
    def get(self, request, presentation_id):
        presentation = get_object_or_404(
            PresentationProject,
            id=presentation_id,
            user=request.user
        )
        
        form = PresentationExportForm()
        
        # Get recent exports
        recent_exports = PresentationExport.objects.filter(
            presentation=presentation,
            user=request.user
        ).order_by('-created_at')[:5]
        
        return render(request, self.template_name, {
            'presentation': presentation,
            'form': form,
            'recent_exports': recent_exports
        })
    
    def post(self, request, presentation_id):
        presentation = get_object_or_404(
            PresentationProject,
            id=presentation_id,
            user=request.user
        )
        
        form = PresentationExportForm(request.POST)
        
        if form.is_valid():
            # Create export request
            export = PresentationExport.objects.create(
                presentation=presentation,
                user=request.user,
                export_format=form.cleaned_data['export_format'],
                status='processing'
            )
            
            try:
                # Basic export functionality (can be enhanced later)
                export_data = self._generate_export_data(
                    presentation,
                    form.cleaned_data['export_format'],
                    form.cleaned_data['include_notes'],
                    form.cleaned_data['high_quality']
                )
                
                export.file_data = export_data
                export.status = 'completed'
                export.save()
                
                return JsonResponse({
                    'success': True,
                    'export_id': export.id,
                    'download_url': reverse('presentation_download', kwargs={'export_id': export.id})
                })
                
            except Exception as e:
                export.status = 'failed'
                export.save()
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                })
        
        return JsonResponse({
            'success': False,
            'error': 'Invalid form data'
        })
    
    def _generate_export_data(self, presentation, format_type, include_notes, high_quality):
        """Generate export data for different formats"""
        slides = presentation.slides.all().order_by('slide_number')
        
        if format_type == 'json':
            # JSON export
            data = {
                'presentation': {
                    'title': presentation.title,
                    'description': presentation.description,
                    'theme': presentation.theme,
                    'color_scheme': presentation.color_scheme,
                    'slides': []
                }
            }
            
            for slide in slides:
                slide_data = {
                    'slide_number': slide.slide_number,
                    'title': slide.title,
                    'subtitle': slide.subtitle,
                    'content': slide.content,
                    'slide_type': slide.slide_type,
                    'layout': slide.layout
                }
                
                if include_notes:
                    slide_data['notes'] = slide.notes
                
                data['presentation']['slides'].append(slide_data)
            
            return base64.b64encode(json.dumps(data, indent=2).encode()).decode()
        
        elif format_type == 'html':
            # Simple HTML export
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>{presentation.title}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; }}
                    .slide {{ page-break-after: always; margin-bottom: 40px; }}
                    .slide-title {{ font-size: 24px; font-weight: bold; margin-bottom: 10px; }}
                    .slide-content {{ font-size: 16px; line-height: 1.6; }}
                    .slide-notes {{ margin-top: 20px; font-style: italic; color: #666; }}
                </style>
            </head>
            <body>
                <h1>{presentation.title}</h1>
                <p>{presentation.description}</p>
            """
            
            for slide in slides:
                html_content += f"""
                <div class="slide">
                    <div class="slide-title">{slide.title or f'Slide {slide.slide_number}'}</div>
                    <div class="slide-content">{slide.content or ''}</div>
                """
                
                if include_notes and slide.notes:
                    html_content += f'<div class="slide-notes">Notes: {slide.notes}</div>'
                
                html_content += '</div>'
            
            html_content += '</body></html>'
            
            return base64.b64encode(html_content.encode()).decode()
        
        else:
            # Fallback to JSON
            return self._generate_export_data(presentation, 'json', include_notes, high_quality)


class PresentationDownloadView(LoginRequiredMixin, View):
    """View for downloading exported presentations"""
    
    def get(self, request, export_id):
        export = get_object_or_404(
            PresentationExport,
            id=export_id,
            user=request.user,
            status='completed'
        )
        
        if export.is_expired:
            return HttpResponse("Export has expired", status=410)
        
        # Decode file data
        file_data = base64.b64decode(export.file_data)
        
        # Set content type based on format
        content_types = {
            'pdf': 'application/pdf',
            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'html': 'text/html',
            'json': 'application/json',
            'images': 'application/zip'
        }
        
        content_type = content_types.get(export.export_format, 'application/octet-stream')
        filename = f"{export.presentation.title}.{export.export_format}"
        
        response = HttpResponse(file_data, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class PresentationMetricsView(LoginRequiredMixin, View):
    """View to get presentation generation metrics"""
    
    def get(self, request):
        # System metrics
        system_metrics = get_presentation_metrics()
        
        # User metrics
        user_requests = PresentationProject.objects.filter(user=request.user)
        user_metrics = {
            'total_presentations': user_requests.count(),
            'completed_presentations': user_requests.filter(status='completed').count(),
            'failed_presentations': user_requests.filter(status='failed').count(),
            'total_slides': PresentationSlide.objects.filter(presentation__user=request.user).count(),
            'avg_generation_time': user_requests.filter(
                generation_time__isnull=False
            ).aggregate(
                avg_time=Avg('generation_time')
            )['avg_time'] or 0,
            'favorite_theme': user_requests.values('theme').annotate(
                count=Sum('id')
            ).order_by('-count').first()
        }
        
        return JsonResponse({
            'system_metrics': system_metrics,
            'user_metrics': user_metrics
        })
