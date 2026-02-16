from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json


class ChatConversation(models.Model):
    """Model to store chat conversations"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=200, help_text="Conversation title")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"Conversation: {self.title} by {self.user.username}"
    
    @property
    def last_message(self):
        """Get the last message in this conversation"""
        return self.messages.first()


class ChatMessage(models.Model):
    """Model to store individual chat messages"""
    
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    
    conversation = models.ForeignKey(ChatConversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(help_text="Message content")
    image_url = models.URLField(blank=True, null=True, help_text="Optional image URL")
    
    # Assistant response metadata
    model_used = models.CharField(max_length=100, blank=True, null=True, help_text="AI model used for response")
    task_type = models.CharField(max_length=50, blank=True, null=True, help_text="Type of task performed")
    response_time = models.FloatField(blank=True, null=True, help_text="Response time in seconds")
    
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['conversation', '-created_at']),
            models.Index(fields=['role']),
        ]
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."

class ImageGenerationRequest(models.Model):
    """Model to store image generation requests and results"""
    
    # Request metadata
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='image_requests')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Generation parameters
    prompt = models.TextField(help_text="Text description for image generation")
    negative_prompt = models.TextField(blank=True, null=True, help_text="What to avoid in the image")
    width = models.IntegerField(default=1024, help_text="Image width in pixels")
    height = models.IntegerField(default=1024, help_text="Image height in pixels")
    steps = models.IntegerField(default=30, help_text="Number of diffusion steps")
    cfg_scale = models.FloatField(default=7.0, help_text="CFG scale (how closely to follow prompt)")
    samples = models.IntegerField(default=1, help_text="Number of images to generate")
    style_preset = models.CharField(max_length=50, blank=True, null=True, help_text="Style preset applied")
    seed = models.BigIntegerField(blank=True, null=True, help_text="Random seed for reproducible results")
    
    # Status tracking
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Results
    generation_time = models.FloatField(blank=True, null=True, help_text="Time taken to generate (seconds)")
    error_message = models.TextField(blank=True, null=True, help_text="Error message if generation failed")
    model_used = models.CharField(max_length=100, blank=True, null=True, help_text="AI model used for generation")
    
    # Additional metadata
    cached = models.BooleanField(default=False, help_text="Whether result was served from cache")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Image request by {self.user.username}: {self.prompt[:50]}..."
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    @property
    def is_failed(self):
        return self.status == 'failed'
    
    @property
    def is_processing(self):
        return self.status == 'processing'

class GeneratedImage(models.Model):
    """Model to store individual generated images"""
    
    request = models.ForeignKey(ImageGenerationRequest, on_delete=models.CASCADE, related_name='images')
    created_at = models.DateTimeField(default=timezone.now)
    
    # Image data
    image_data = models.TextField(help_text="Base64 encoded image data")
    seed_used = models.BigIntegerField(blank=True, null=True, help_text="Seed used for this specific image")
    finish_reason = models.CharField(max_length=50, blank=True, null=True, help_text="Completion status from API")
    
    # Image metadata
    file_size = models.IntegerField(blank=True, null=True, help_text="Image file size in bytes")
    mime_type = models.CharField(max_length=50, default='image/png')
    
    # User actions
    favorited = models.BooleanField(default=False, help_text="Whether user marked as favorite")
    public = models.BooleanField(default=False, help_text="Whether image is publicly viewable")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['request', '-created_at']),
            models.Index(fields=['favorited']),
            models.Index(fields=['public']),
        ]
    
    def __str__(self):
        return f"Image for request {self.request.id} (seed: {self.seed_used})"
    
    @property
    def image_url(self):
        """Return data URL for the image"""
        return f"data:{self.mime_type};base64,{self.image_data}"

class ImageUpscaleRequest(models.Model):
    """Model to store image upscaling requests"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='upscale_requests')
    original_image = models.ForeignKey(GeneratedImage, on_delete=models.CASCADE, related_name='upscale_requests')
    created_at = models.DateTimeField(default=timezone.now)
    
    # Upscale parameters
    target_width = models.IntegerField(blank=True, null=True)
    target_height = models.IntegerField(blank=True, null=True)
    
    # Status and results
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    processing_time = models.FloatField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    
    # Result image data
    upscaled_image_data = models.TextField(blank=True, null=True, help_text="Base64 encoded upscaled image")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Upscale request by {self.user.username} for image {self.original_image.id}"
    
    @property
    def upscaled_image_url(self):
        """Return data URL for the upscaled image"""
        if self.upscaled_image_data:
            return f"data:image/png;base64,{self.upscaled_image_data}"
        return None

class UserImagePreferences(models.Model):
    """Model to store user preferences for image generation"""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='image_preferences')
    
    # Default generation parameters
    default_width = models.IntegerField(default=1024)
    default_height = models.IntegerField(default=1024)
    default_steps = models.IntegerField(default=30)
    default_cfg_scale = models.FloatField(default=7.0)
    default_style_preset = models.CharField(max_length=50, blank=True, null=True)
    
    # Usage statistics
    total_images_generated = models.IntegerField(default=0)
    total_generation_time = models.FloatField(default=0.0)
    favorite_style_preset = models.CharField(max_length=50, blank=True, null=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Image preferences for {self.user.username}"
    
    def update_stats(self, generation_time: float, images_count: int = 1):
        """Update user statistics after image generation"""
        self.total_images_generated += images_count
        self.total_generation_time += generation_time
        self.save()


class VideoGenerationRequest(models.Model):
    """Model to store video generation requests and results"""
    
    # Request metadata
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='video_requests')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Generation parameters
    prompt = models.TextField(help_text="Text description for video generation")
    model = models.CharField(max_length=100, default="meituan-longcat/LongCat-Video", help_text="AI model used for generation")
    duration = models.FloatField(blank=True, null=True, help_text="Video duration in seconds")
    fps = models.IntegerField(blank=True, null=True, help_text="Frames per second")
    width = models.IntegerField(blank=True, null=True, help_text="Video width in pixels")
    height = models.IntegerField(blank=True, null=True, help_text="Video height in pixels")
    
    # Status tracking
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Results
    generation_time = models.FloatField(blank=True, null=True, help_text="Time taken to generate (seconds)")
    error_message = models.TextField(blank=True, null=True, help_text="Error message if generation failed")
    
    # Additional metadata
    cached = models.BooleanField(default=False, help_text="Whether result was served from cache")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Video request by {self.user.username}: {self.prompt[:50]}..."
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    @property
    def is_failed(self):
        return self.status == 'failed'
    
    @property
    def is_processing(self):
        return self.status == 'processing'


class GeneratedVideo(models.Model):
    """Model to store individual generated videos"""
    
    request = models.ForeignKey(VideoGenerationRequest, on_delete=models.CASCADE, related_name='videos')
    created_at = models.DateTimeField(default=timezone.now)
    
    # Video data
    video_data = models.TextField(help_text="Base64 encoded video data")
    file_size = models.IntegerField(blank=True, null=True, help_text="Video file size in bytes")
    mime_type = models.CharField(max_length=50, default='video/mp4')
    
    # User actions
    favorited = models.BooleanField(default=False, help_text="Whether user marked as favorite")
    public = models.BooleanField(default=False, help_text="Whether video is publicly viewable")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['request', '-created_at']),
            models.Index(fields=['favorited']),
            models.Index(fields=['public']),
        ]
    
    def __str__(self):
        return f"Video for request {self.request.id}"
    
    @property
    def video_url(self):
        """Return data URL for the video"""
        return f"data:{self.mime_type};base64,{self.video_data}"


class UserVideoPreferences(models.Model):
    """Model to store user preferences for video generation"""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='video_preferences')
    
    # Default generation parameters
    default_model = models.CharField(max_length=100, default="meituan-longcat/LongCat-Video")
    default_duration = models.FloatField(blank=True, null=True)
    default_fps = models.IntegerField(blank=True, null=True)
    default_width = models.IntegerField(blank=True, null=True)
    default_height = models.IntegerField(blank=True, null=True)
    
    # Usage statistics
    total_videos_generated = models.IntegerField(default=0)
    total_generation_time = models.FloatField(default=0.0)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Video preferences for {self.user.username}"
    
    def update_stats(self, generation_time: float, videos_count: int = 1):
        """Update user statistics after video generation"""
        self.total_videos_generated += videos_count
        self.total_generation_time += generation_time
        self.save()


class AudioGenerationRequest(models.Model):
    """Model to store audio generation requests and results"""
    
    # Request metadata
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='audio_requests')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Generation parameters
    text = models.TextField(help_text="Text to convert to speech")
    voice_id = models.CharField(max_length=100, blank=True, null=True, help_text="Voice ID/style")
    model = models.CharField(max_length=100, default="eleven_multilingual_v2", help_text="TTS model")
    stability = models.FloatField(default=0.5, help_text="Voice stability (0.0-1.0)")
    similarity_boost = models.FloatField(default=0.5, help_text="Voice similarity boost (0.0-1.0)")
    style = models.FloatField(default=0.0, help_text="Style exaggeration (0.0-1.0)")
    use_speaker_boost = models.BooleanField(default=True, help_text="Enable speaker boost")
    
    # Status tracking
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Results
    generation_time = models.FloatField(blank=True, null=True, help_text="Time taken to generate (seconds)")
    error_message = models.TextField(blank=True, null=True, help_text="Error message if generation failed")
    model_used = models.CharField(max_length=100, blank=True, null=True, help_text="TTS model used")
    
    # Additional metadata
    cached = models.BooleanField(default=False, help_text="Whether result was served from cache")
    character_count = models.IntegerField(blank=True, null=True, help_text="Number of characters in text")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Audio request by {self.user.username}: {self.text[:50]}..."
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    @property
    def is_failed(self):
        return self.status == 'failed'
    
    @property
    def is_processing(self):
        return self.status == 'processing'


class GeneratedAudio(models.Model):
    """Model to store individual generated audio files"""
    
    request = models.ForeignKey(AudioGenerationRequest, on_delete=models.CASCADE, related_name='audio_files')
    created_at = models.DateTimeField(default=timezone.now)
    
    # Audio data
    audio_data = models.TextField(help_text="Base64 encoded audio data")
    file_size = models.IntegerField(blank=True, null=True, help_text="Audio file size in bytes")
    mime_type = models.CharField(max_length=50, default='audio/mpeg')
    duration = models.FloatField(blank=True, null=True, help_text="Audio duration in seconds")
    
    # User actions
    favorited = models.BooleanField(default=False, help_text="Whether user marked as favorite")
    public = models.BooleanField(default=False, help_text="Whether audio is publicly viewable")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['request', '-created_at']),
            models.Index(fields=['favorited']),
            models.Index(fields=['public']),
        ]
    
    def __str__(self):
        return f"Audio for request {self.request.id}"
    
    @property
    def audio_url(self):
        """Return data URL for the audio"""
        return f"data:{self.mime_type};base64,{self.audio_data}"


class UserAudioPreferences(models.Model):
    """Model to store user preferences for audio generation"""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='audio_preferences')
    
    # Default generation parameters
    default_voice_id = models.CharField(max_length=100, blank=True, null=True)
    default_model = models.CharField(max_length=100, default="eleven_multilingual_v2")
    default_stability = models.FloatField(default=0.5)
    default_similarity_boost = models.FloatField(default=0.5)
    default_style = models.FloatField(default=0.0)
    default_speaker_boost = models.BooleanField(default=True)
    
    # Usage statistics
    total_audio_generated = models.IntegerField(default=0)
    total_generation_time = models.FloatField(default=0.0)
    total_characters_processed = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Audio preferences for {self.user.username}"
    
    def update_stats(self, generation_time: float, character_count: int, audio_count: int = 1):
        """Update user statistics after audio generation"""
        self.total_audio_generated += audio_count
        self.total_generation_time += generation_time
        self.total_characters_processed += character_count
        self.save()


class PresentationProject(models.Model):
    """Model to store presentation projects"""
    
    # Basic information
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='presentations')
    title = models.CharField(max_length=200, help_text="Presentation title")
    description = models.TextField(blank=True, null=True, help_text="Brief description of the presentation")
    
    # Generation parameters
    topic = models.CharField(max_length=500, help_text="Main topic or theme")
    target_audience = models.CharField(max_length=200, blank=True, null=True, help_text="Target audience")
    presentation_type = models.CharField(max_length=100, choices=[
        ('business', 'Business Presentation'),
        ('educational', 'Educational/Academic'),
        ('marketing', 'Marketing Pitch'),
        ('report', 'Report/Analysis'),
        ('proposal', 'Project Proposal'),
        ('training', 'Training Material'),
        ('portfolio', 'Portfolio Showcase'),
        ('other', 'Other')
    ], default='business')
    
    # Styling and preferences
    theme = models.CharField(max_length=100, choices=[
        ('modern', 'Modern & Clean'),
        ('corporate', 'Corporate Professional'),
        ('creative', 'Creative & Colorful'),
        ('minimal', 'Minimal & Simple'),
        ('academic', 'Academic & Traditional'),
        ('tech', 'Technology Focused'),
        ('nature', 'Nature & Organic'),
        ('dark', 'Dark & Bold')
    ], default='modern')
    
    color_scheme = models.CharField(max_length=100, choices=[
        ('blue', 'Professional Blue'),
        ('green', 'Fresh Green'),
        ('purple', 'Creative Purple'),
        ('orange', 'Energetic Orange'),
        ('red', 'Bold Red'),
        ('teal', 'Modern Teal'),
        ('gray', 'Elegant Gray'),
        ('custom', 'Custom Colors')
    ], default='blue')
    
    # Status tracking
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('generating', 'Generating'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Generation settings
    slide_count = models.IntegerField(default=10, help_text="Target number of slides")
    include_images = models.BooleanField(default=True, help_text="Generate relevant images")
    include_charts = models.BooleanField(default=True, help_text="Include charts and graphs")
    tone = models.CharField(max_length=100, choices=[
        ('professional', 'Professional'),
        ('casual', 'Casual & Friendly'),
        ('formal', 'Formal & Academic'),
        ('persuasive', 'Persuasive & Compelling'),
        ('educational', 'Educational & Clear'),
        ('inspiring', 'Inspiring & Motivational')
    ], default='professional')
    
    # Timestamps and metadata
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    generation_time = models.FloatField(blank=True, null=True, help_text="Time taken to generate")
    model_used = models.CharField(max_length=100, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    
    # Sharing and visibility
    is_public = models.BooleanField(default=False, help_text="Public presentations visible to others")
    share_token = models.CharField(max_length=100, blank=True, null=True, help_text="Unique sharing token")
    
    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['status']),
            models.Index(fields=['is_public']),
            models.Index(fields=['share_token']),
        ]
    
    def __str__(self):
        return f"{self.title} by {self.user.username}"
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    @property
    def slide_count_actual(self):
        return self.slides.count()
    
    def generate_share_token(self):
        """Generate a unique sharing token"""
        import secrets
        self.share_token = secrets.token_urlsafe(32)
        self.save()
        return self.share_token


class PresentationSlide(models.Model):
    """Model to store individual slides in a presentation"""
    
    presentation = models.ForeignKey(PresentationProject, on_delete=models.CASCADE, related_name='slides')
    slide_number = models.PositiveIntegerField(help_text="Order of slide in presentation")
    
    # Content
    title = models.CharField(max_length=300, blank=True, null=True)
    subtitle = models.CharField(max_length=500, blank=True, null=True)
    content = models.TextField(blank=True, null=True, help_text="Main slide content")
    notes = models.TextField(blank=True, null=True, help_text="Speaker notes")
    
    # Slide type and layout
    slide_type = models.CharField(max_length=100, choices=[
        ('title', 'Title Slide'),
        ('content', 'Content Slide'),
        ('bullet_points', 'Bullet Points'),
        ('two_column', 'Two Column Layout'),
        ('image_text', 'Image with Text'),
        ('chart', 'Chart/Graph'),
        ('quote', 'Quote/Testimonial'),
        ('call_to_action', 'Call to Action'),
        ('thank_you', 'Thank You/Contact'),
        ('section_break', 'Section Break')
    ], default='content')
    
    layout = models.CharField(max_length=100, choices=[
        ('default', 'Default Layout'),
        ('centered', 'Centered Content'),
        ('left_aligned', 'Left Aligned'),
        ('split_half', 'Split 50/50'),
        ('two_thirds_left', 'Two-thirds Left'),
        ('two_thirds_right', 'Two-thirds Right'),
        ('full_image', 'Full Background Image'),
        ('minimal', 'Minimal Text')
    ], default='default')
    
    # Styling
    background_color = models.CharField(max_length=50, blank=True, null=True)
    text_color = models.CharField(max_length=50, blank=True, null=True)
    accent_color = models.CharField(max_length=50, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['slide_number']
        unique_together = ('presentation', 'slide_number')
        indexes = [
            models.Index(fields=['presentation', 'slide_number']),
            models.Index(fields=['slide_type']),
        ]
    
    def __str__(self):
        return f"Slide {self.slide_number}: {self.title or 'Untitled'}"


class SlideElement(models.Model):
    """Model to store individual elements within slides (text, images, charts)"""
    
    slide = models.ForeignKey(PresentationSlide, on_delete=models.CASCADE, related_name='elements')
    element_type = models.CharField(max_length=100, choices=[
        ('text', 'Text Block'),
        ('heading', 'Heading'),
        ('bullet_list', 'Bullet List'),
        ('numbered_list', 'Numbered List'),
        ('image', 'Image'),
        ('chart', 'Chart/Graph'),
        ('table', 'Table'),
        ('quote', 'Quote Block'),
        ('divider', 'Divider/Separator'),
        ('button', 'Button/CTA'),
        ('embed', 'Embedded Content')
    ])
    
    # Position and sizing
    position_x = models.FloatField(default=0, help_text="X position as percentage")
    position_y = models.FloatField(default=0, help_text="Y position as percentage") 
    width = models.FloatField(default=100, help_text="Width as percentage")
    height = models.FloatField(default=20, help_text="Height as percentage")
    z_index = models.IntegerField(default=1, help_text="Layer order")
    
    # Content
    content = models.TextField(blank=True, null=True, help_text="Element content")
    content_data = models.JSONField(blank=True, null=True, help_text="Structured data for complex elements")
    
    # Styling
    font_size = models.CharField(max_length=50, blank=True, null=True)
    font_weight = models.CharField(max_length=50, blank=True, null=True)
    text_align = models.CharField(max_length=50, choices=[
        ('left', 'Left'),
        ('center', 'Center'),
        ('right', 'Right'),
        ('justify', 'Justify')
    ], default='left')
    color = models.CharField(max_length=50, blank=True, null=True)
    background = models.CharField(max_length=100, blank=True, null=True)
    border = models.CharField(max_length=100, blank=True, null=True)
    
    # Animation and transitions
    animation = models.CharField(max_length=100, blank=True, null=True)
    animation_delay = models.FloatField(default=0, help_text="Animation delay in seconds")
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['z_index', 'created_at']
        indexes = [
            models.Index(fields=['slide', 'z_index']),
            models.Index(fields=['element_type']),
        ]
    
    def __str__(self):
        return f"{self.element_type} in {self.slide}"


class PresentationTemplate(models.Model):
    """Model to store reusable presentation templates"""
    
    name = models.CharField(max_length=200, help_text="Template name")
    description = models.TextField(help_text="Template description")
    category = models.CharField(max_length=100, choices=[
        ('business', 'Business'),
        ('education', 'Education'),
        ('marketing', 'Marketing'),
        ('creative', 'Creative'),
        ('minimal', 'Minimal'),
        ('corporate', 'Corporate')
    ])
    
    # Template structure
    template_data = models.JSONField(help_text="Template structure and default content")
    preview_image = models.TextField(blank=True, null=True, help_text="Base64 preview image")
    
    # Usage and ratings
    usage_count = models.IntegerField(default=0)
    rating = models.FloatField(default=0)
    is_premium = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # Creator information
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-usage_count', '-created_at']
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['usage_count']),
        ]
    
    def __str__(self):
        return f"Template: {self.name}"


class PresentationExport(models.Model):
    """Model to track presentation exports and downloads"""
    
    presentation = models.ForeignKey(PresentationProject, on_delete=models.CASCADE, related_name='exports')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Export details
    export_format = models.CharField(max_length=50, choices=[
        ('pdf', 'PDF'),
        ('pptx', 'PowerPoint'),
        ('html', 'HTML'),
        ('images', 'Image Files'),
        ('json', 'JSON Data')
    ])
    
    # File information
    file_size = models.IntegerField(blank=True, null=True)
    file_data = models.TextField(blank=True, null=True, help_text="Base64 encoded file data")
    download_url = models.URLField(blank=True, null=True, help_text="External download URL")
    
    # Status
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(blank=True, null=True, help_text="Export expiration time")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['presentation', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.export_format.upper()} export of {self.presentation.title}"
    
    @property
    def is_expired(self):
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False


class UserPresentationPreferences(models.Model):
    """Model to store user preferences for presentation generation"""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='presentation_preferences')
    
    # Default generation parameters
    default_theme = models.CharField(max_length=100, default='modern')
    default_color_scheme = models.CharField(max_length=100, default='blue')
    default_tone = models.CharField(max_length=100, default='professional')
    default_slide_count = models.IntegerField(default=10)
    default_include_images = models.BooleanField(default=True)
    default_include_charts = models.BooleanField(default=True)
    
    # AI and export preferences
    preferred_ai_model = models.CharField(max_length=100, blank=True, null=True)
    default_export_format = models.CharField(max_length=50, default='pdf')
    auto_generate_speaker_notes = models.BooleanField(default=True)
    
    # Usage statistics
    total_presentations_created = models.IntegerField(default=0)
    total_slides_generated = models.IntegerField(default=0)
    total_generation_time = models.FloatField(default=0.0)
    favorite_templates = models.ManyToManyField(PresentationTemplate, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Presentation preferences for {self.user.username}"
    
    def update_stats(self, generation_time: float, slide_count: int, presentation_count: int = 1):
        """Update user statistics after presentation generation"""
        self.total_presentations_created += presentation_count
        self.total_slides_generated += slide_count
        self.total_generation_time += generation_time
        self.save()


# ============================================================================
# WEB IDE MODELS
# ============================================================================

class IDEProject(models.Model):
    """Model to store IDE projects"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ide_projects')
    name = models.CharField(max_length=200, help_text="Project name")
    description = models.TextField(blank=True, null=True, help_text="Project description")
    
    # Project metadata
    PROJECT_TYPE_CHOICES = [
        ('python', 'Python'),
        ('javascript', 'JavaScript'),
        ('typescript', 'TypeScript'),
        ('html', 'HTML/CSS/JS'),
        ('react', 'React'),
        ('vue', 'Vue.js'),
        ('django', 'Django'),
        ('flask', 'Flask'),
        ('node', 'Node.js'),
        ('other', 'Other'),
    ]
    project_type = models.CharField(max_length=50, choices=PROJECT_TYPE_CHOICES, default='python')
    
    # Project settings
    is_public = models.BooleanField(default=False, help_text="Whether project is publicly accessible")
    is_template = models.BooleanField(default=False, help_text="Whether project is a template")
    
    # AI settings
    ai_enabled = models.BooleanField(default=True, help_text="Enable AI assistance")
    ai_model = models.CharField(max_length=100, blank=True, null=True, help_text="Preferred AI model")
    
    # Execution settings
    python_version = models.CharField(max_length=20, default='3.10', help_text="Python version for execution")
    node_version = models.CharField(max_length=20, blank=True, null=True, help_text="Node.js version")
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    last_accessed = models.DateTimeField(default=timezone.now)
    
    # Statistics
    total_executions = models.IntegerField(default=0)
    total_ai_queries = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['is_public']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.name} by {self.user.username}"
    
    def update_access_time(self):
        """Update last accessed time"""
        self.last_accessed = timezone.now()
        self.save(update_fields=['last_accessed'])


class CodeFile(models.Model):
    """Model to store code files in IDE projects"""
    
    project = models.ForeignKey(IDEProject, on_delete=models.CASCADE, related_name='files')
    name = models.CharField(max_length=255, help_text="File name")
    path = models.CharField(max_length=500, help_text="File path relative to project root")
    content = models.TextField(help_text="File content")
    
    # File metadata
    FILE_TYPE_CHOICES = [
        ('python', 'Python'),
        ('javascript', 'JavaScript'),
        ('typescript', 'TypeScript'),
        ('html', 'HTML'),
        ('css', 'CSS'),
        ('json', 'JSON'),
        ('markdown', 'Markdown'),
        ('yaml', 'YAML'),
        ('text', 'Plain Text'),
        ('other', 'Other'),
    ]
    file_type = models.CharField(max_length=50, choices=FILE_TYPE_CHOICES, default='python')
    language = models.CharField(max_length=50, blank=True, null=True, help_text="Programming language")
    
    # Version control
    version = models.IntegerField(default=1)
    previous_version = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='next_versions')
    
    # Metadata
    size_bytes = models.IntegerField(default=0)
    line_count = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # AI metadata
    ai_generated = models.BooleanField(default=False, help_text="Whether file was AI-generated")
    ai_model_used = models.CharField(max_length=100, blank=True, null=True)
    
    class Meta:
        ordering = ['path', 'name']
        unique_together = [['project', 'path']]
        indexes = [
            models.Index(fields=['project', 'path']),
            models.Index(fields=['file_type']),
            models.Index(fields=['-updated_at']),
        ]
    
    def __str__(self):
        return f"{self.path} ({self.project.name})"
    
    def save(self, *args, **kwargs):
        # Auto-calculate metadata
        self.size_bytes = len(self.content.encode('utf-8'))
        self.line_count = self.content.count('\n') + 1
        super().save(*args, **kwargs)
    
    def detect_language(self):
        """Auto-detect programming language from file extension"""
        ext_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.html': 'html',
            '.css': 'css',
            '.json': 'json',
            '.md': 'markdown',
            '.yml': 'yaml',
            '.yaml': 'yaml',
            '.txt': 'text',
        }
        import os
        _, ext = os.path.splitext(self.name)
        return ext_map.get(ext.lower(), 'other')


class IDEChatMessage(models.Model):
    """Model to store IDE chat messages with AI"""
    
    project = models.ForeignKey(IDEProject, on_delete=models.CASCADE, related_name='chat_messages')
    
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(help_text="Message content")
    
    # Context information
    context_files = models.ManyToManyField(CodeFile, blank=True, help_text="Files referenced in message")
    code_snippets = models.JSONField(default=list, blank=True, help_text="Code snippets in message")
    
    # AI metadata
    model_used = models.CharField(max_length=100, blank=True, null=True)
    response_time = models.FloatField(blank=True, null=True, help_text="Response time in seconds")
    tokens_used = models.IntegerField(blank=True, null=True)
    
    # Message actions
    MESSAGE_TYPE_CHOICES = [
        ('chat', 'Chat'),
        ('code_generation', 'Code Generation'),
        ('code_explanation', 'Code Explanation'),
        ('code_fix', 'Code Fix'),
        ('code_refactor', 'Code Refactor'),
        ('documentation', 'Documentation'),
        ('other', 'Other'),
    ]
    message_type = models.CharField(max_length=50, choices=MESSAGE_TYPE_CHOICES, default='chat')
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['project', 'created_at']),
            models.Index(fields=['role']),
            models.Index(fields=['message_type']),
        ]
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class CodeExecutionResult(models.Model):
    """Model to store code execution results"""
    
    project = models.ForeignKey(IDEProject, on_delete=models.CASCADE, related_name='executions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='code_executions')
    
    # Execution details
    file = models.ForeignKey(CodeFile, on_delete=models.SET_NULL, null=True, blank=True)
    code = models.TextField(help_text="Code that was executed")
    
    # Execution settings
    EXECUTION_TYPE_CHOICES = [
        ('full', 'Full Project'),
        ('file', 'Single File'),
        ('snippet', 'Code Snippet'),
        ('terminal', 'Terminal Command'),
    ]
    execution_type = models.CharField(max_length=50, choices=EXECUTION_TYPE_CHOICES, default='snippet')
    
    command = models.TextField(blank=True, null=True, help_text="Command executed")
    environment = models.JSONField(default=dict, blank=True, help_text="Environment variables")
    
    # Results
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('error', 'Error'),
        ('timeout', 'Timeout'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    stdout = models.TextField(blank=True, null=True, help_text="Standard output")
    stderr = models.TextField(blank=True, null=True, help_text="Standard error")
    exit_code = models.IntegerField(blank=True, null=True)
    
    # Performance metrics
    execution_time = models.FloatField(blank=True, null=True, help_text="Execution time in seconds")
    memory_used = models.IntegerField(blank=True, null=True, help_text="Memory used in MB")
    cpu_time = models.FloatField(blank=True, null=True, help_text="CPU time in seconds")
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Execution {self.id} - {self.status}"
    
    @property
    def is_success(self):
        return self.status == 'completed' and self.exit_code == 0
    
    @property
    def has_output(self):
        return bool(self.stdout or self.stderr)


class ProjectDeployment(models.Model):
    """Model to store project deployment information"""
    
    project = models.ForeignKey(IDEProject, on_delete=models.CASCADE, related_name='deployments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deployments')
    
    # Deployment details
    PLATFORM_CHOICES = [
        ('github', 'GitHub'),
        ('gitlab', 'GitLab'),
        ('heroku', 'Heroku'),
        ('vercel', 'Vercel'),
        ('netlify', 'Netlify'),
        ('aws', 'AWS'),
        ('gcp', 'Google Cloud'),
        ('azure', 'Azure'),
        ('custom', 'Custom'),
    ]
    platform = models.CharField(max_length=50, choices=PLATFORM_CHOICES)
    
    # Deployment configuration
    deployment_url = models.URLField(blank=True, null=True, help_text="Deployment URL")
    repository_url = models.URLField(blank=True, null=True, help_text="Repository URL")
    config = models.JSONField(default=dict, blank=True, help_text="Deployment configuration")
    
    # Status
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('deploying', 'Deploying'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Logs and results
    deployment_log = models.TextField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    deployed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['platform']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.project.name} deployed to {self.platform}"


class ProjectExport(models.Model):
    """Model to store project export/download information"""
    
    project = models.ForeignKey(IDEProject, on_delete=models.CASCADE, related_name='exports')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_exports')
    
    # Export details
    EXPORT_FORMAT_CHOICES = [
        ('zip', 'ZIP Archive'),
        ('tar', 'TAR Archive'),
        ('github', 'GitHub Repository'),
    ]
    export_format = models.CharField(max_length=50, choices=EXPORT_FORMAT_CHOICES, default='zip')
    
    # Export data
    file_data = models.TextField(blank=True, null=True, help_text="Base64 encoded export file")
    file_size = models.IntegerField(blank=True, null=True, help_text="Export file size in bytes")
    download_url = models.URLField(blank=True, null=True, help_text="External download URL")
    
    # Settings
    include_dependencies = models.BooleanField(default=True)
    include_venv = models.BooleanField(default=False)
    
    # Status
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(blank=True, null=True, help_text="Export expiration time")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.export_format.upper()} export of {self.project.name}"
    
    @property
    def is_expired(self):
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False


class UserIDEPreferences(models.Model):
    """Model to store user IDE preferences"""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='ide_preferences')
    
    # Editor settings
    theme = models.CharField(max_length=50, default='vs-dark', help_text="Editor theme")
    font_size = models.IntegerField(default=14, help_text="Font size in pixels")
    font_family = models.CharField(max_length=100, default='Monaco, monospace')
    tab_size = models.IntegerField(default=4)
    use_spaces = models.BooleanField(default=True, help_text="Use spaces instead of tabs")
    word_wrap = models.BooleanField(default=True)
    line_numbers = models.BooleanField(default=True)
    minimap_enabled = models.BooleanField(default=True)
    
    # AI settings
    ai_autocomplete = models.BooleanField(default=True)
    ai_suggestions = models.BooleanField(default=True)
    preferred_ai_model = models.CharField(max_length=100, blank=True, null=True)
    
    # Execution settings
    auto_save = models.BooleanField(default=True)
    auto_format = models.BooleanField(default=False)
    
    # Layout preferences
    sidebar_position = models.CharField(max_length=20, default='left', choices=[('left', 'Left'), ('right', 'Right')])
    terminal_position = models.CharField(max_length=20, default='bottom', choices=[('bottom', 'Bottom'), ('right', 'Right')])
    
    # Usage statistics
    total_projects = models.IntegerField(default=0)
    total_executions = models.IntegerField(default=0)
    total_ai_queries = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"IDE preferences for {self.user.username}"