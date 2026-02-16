from django import forms
from django.contrib.auth.models import User
from .models import ImageGenerationRequest, VideoGenerationRequest, AudioGenerationRequest
from .services.stable_diffusion import get_available_style_presets
from .services.video_generation import get_available_video_models
from .services.audio_generation import get_available_voices


class SignUpForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    class Meta:
        model = User
        fields = ("username", "email")

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get("password")
        pwc = cleaned.get("password_confirm")
        if pw and pwc and pw != pwc:
            raise forms.ValidationError("Passwords do not match")
        return cleaned


class ImageGenerationForm(forms.Form):
    """Form for image generation requests"""
    
    prompt = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "Describe the image you want to generate...",
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Image Prompt",
        help_text="Describe what you want to see in the image"
    )
    
    negative_prompt = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 2,
            "placeholder": "Things to avoid in the image (optional)...",
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Negative Prompt",
        required=False,
        help_text="Specify what you don't want in the image"
    )
    
    # Size options
    SIZE_CHOICES = [
        ('1024x1024', 'Square (1024×1024)'),
        ('1152x896', 'Landscape (1152×896)'),
        ('896x1152', 'Portrait (896×1152)'),
        ('1216x832', 'Wide Landscape (1216×832)'),
        ('832x1216', 'Tall Portrait (832×1216)'),
        ('1344x768', 'Ultra Wide (1344×768)'),
        ('768x1344', 'Ultra Tall (768×1344)'),
        ('1536x640', 'Panoramic (1536×640)'),
        ('640x1536', 'Tall Panoramic (640×1536)'),
    ]
    
    size = forms.ChoiceField(
        choices=SIZE_CHOICES,
        initial='1024x1024',
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Image Size"
    )
    
    # Style preset
    style_preset = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Style Preset",
        help_text="Choose a style to apply to your image"
    )
    
    # Advanced settings
    steps = forms.IntegerField(
        initial=30,
        min_value=10,
        max_value=50,
        widget=forms.NumberInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "min": 10,
            "max": 50
        }),
        label="Steps",
        help_text="Number of diffusion steps (10-50, higher = better quality but slower)"
    )
    
    cfg_scale = forms.FloatField(
        initial=7.0,
        min_value=1.0,
        max_value=35.0,
        widget=forms.NumberInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "min": 1.0,
            "max": 35.0,
            "step": 0.5
        }),
        label="CFG Scale",
        help_text="How closely to follow the prompt (1-35, 7 is recommended)"
    )
    
    samples = forms.IntegerField(
        initial=1,
        min_value=1,
        max_value=4,
        widget=forms.NumberInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "min": 1,
            "max": 4
        }),
        label="Number of Images",
        help_text="How many images to generate (1-4)"
    )
    
    seed = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "placeholder": "Random (leave empty for random)"
        }),
        label="Seed",
        help_text="Random seed for reproducible results (optional)"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate style preset choices
        style_choices = [('', 'No Style (Default)')] + [
            (preset, preset.replace('-', ' ').title()) 
            for preset in get_available_style_presets()
        ]
        self.fields['style_preset'].choices = style_choices
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Parse size
        size = cleaned_data.get('size')
        if size:
            try:
                width, height = map(int, size.split('x'))
                cleaned_data['width'] = width
                cleaned_data['height'] = height
            except ValueError:
                raise forms.ValidationError("Invalid size format")
        
        return cleaned_data


class QuickImageForm(forms.Form):
    """Simplified form for quick image generation"""
    
    prompt = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Describe your image...",
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Prompt",
        max_length=1000
    )
    
    style = forms.ChoiceField(
        choices=[
            ('', 'Default'),
            ('photographic', 'Photographic'),
            ('digital-art', 'Digital Art'),
            ('anime', 'Anime'),
            ('fantasy-art', 'Fantasy'),
            ('cinematic', 'Cinematic'),
        ],
        required=False,
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Style"
    )


class ImageUpscaleForm(forms.Form):
    """Form for upscaling images"""
    
    image_id = forms.IntegerField(widget=forms.HiddenInput())
    
    target_size = forms.ChoiceField(
        choices=[
            ('2x', '2x Upscale'),
            ('4x', '4x Upscale (Premium)'),
        ],
        initial='2x',
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Upscale Factor"
    )


class VideoGenerationForm(forms.Form):
    """Form for video generation requests"""
    
    prompt = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "Describe the video you want to generate...",
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Video Prompt",
        max_length=500,  # Add max length for better UX
        help_text="Describe what you want to see in the video (max 500 characters)"
    )
    
    # Model selection - Dynamic based on available models
    model = forms.ChoiceField(
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Video Model",
        help_text="Choose the AI model for video generation"
    )
    
    # Video dimensions
    SIZE_CHOICES = [
        ('', 'Default (Model-specific)'),
        ('512x512', 'Square (512×512)'),
        ('640x480', 'Standard (640×480)'),
        ('720x480', 'SD Wide (720×480)'),
        ('1280x720', 'HD (1280×720)'),
    ]
    
    size = forms.ChoiceField(
        choices=SIZE_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Video Size",
        help_text="Choose video dimensions (leave default for model-specific sizing)"
    )
    
    # Duration settings
    duration = forms.FloatField(
        required=False,
        min_value=1.0,
        max_value=10.0,  # Reduced max for better performance
        widget=forms.NumberInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "placeholder": "e.g., 3.0",
            "step": "0.5",
            "min": "1.0",
            "max": "10.0"
        }),
        label="Duration (seconds)",
        help_text="Video duration in seconds (1-10, leave empty for model default)"
    )
    
    # FPS settings
    fps = forms.IntegerField(
        required=False,
        min_value=8,
        max_value=30,  # Reduced max for better performance
        widget=forms.NumberInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "placeholder": "e.g., 24",
            "min": "8",
            "max": "30"
        }),
        label="FPS (Frames per second)",
        help_text="Video frame rate (8-30, leave empty for model default)"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically load available models
        try:
            models = get_available_video_models()
            if models:
                self.fields['model'].choices = [(model['id'], model['name']) for model in models]
                if models:
                    self.fields['model'].initial = models[0]['id']
            else:
                # Fallback choices if service is unavailable
                self.fields['model'].choices = [
                    ('ali-vilab/text-to-video-ms-1.7b', 'Alibaba Text-to-Video (Default)'),
                    ('damo-vilab/text-to-video-ms-1.7b', 'DAMO Text-to-Video'),
                ]
        except Exception:
            # Fallback if service call fails
            self.fields['model'].choices = [
                ('ali-vilab/text-to-video-ms-1.7b', 'Alibaba Text-to-Video (Default)'),
            ]
    
    def clean_prompt(self):
        prompt = self.cleaned_data.get('prompt', '').strip()
        if not prompt:
            raise forms.ValidationError("Prompt cannot be empty")
        if len(prompt) < 10:
            raise forms.ValidationError("Prompt must be at least 10 characters long")
        return prompt
    
    def clean(self):
        cleaned_data = super().clean()
        size = cleaned_data.get('size')
        
        # Parse width and height from size if provided
        if size and 'x' in size:
            try:
                width, height = map(int, size.split('x'))
                cleaned_data['width'] = width
                cleaned_data['height'] = height
            except (ValueError, IndexError):
                pass
        
        return cleaned_data


class QuickVideoForm(forms.Form):
    """Simplified form for quick video generation"""
    
    prompt = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Quick video description...",
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Video Prompt",
        help_text="Describe the video you want to generate"
    )


class AudioGenerationForm(forms.Form):
    """Form for audio generation requests"""
    
    text = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 6,
            "placeholder": "Enter the text you want to convert to speech...",
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "maxlength": "5000"
        }),
        label="Text to Speech",
        max_length=5000,
        help_text="Enter text to convert to audio (up to 5000 characters)"
    )
    
    # Voice selection - Dynamic
    voice_id = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Voice",
        help_text="Choose a voice for the speech generation"
    )
    
    # Model selection - Updated for new service
    model = forms.ChoiceField(
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="TTS Model",
        help_text="Choose the text-to-speech model"
    )
    
    # Voice settings
    stability = forms.FloatField(
        initial=0.5,
        min_value=0.0,
        max_value=1.0,
        widget=forms.NumberInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "step": "0.1",
            "min": "0.0",
            "max": "1.0"
        }),
        label="Stability",
        help_text="Voice stability (0.0-1.0, higher = more stable but less expressive)"
    )
    
    similarity_boost = forms.FloatField(
        initial=0.5,
        min_value=0.0,
        max_value=1.0,
        widget=forms.NumberInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "step": "0.1",
            "min": "0.0",
            "max": "1.0"
        }),
        label="Similarity Boost",
        help_text="Voice similarity boost (0.0-1.0, higher = more similar to original voice)"
    )
    
    style = forms.FloatField(
        initial=0.0,
        min_value=0.0,
        max_value=1.0,
        widget=forms.NumberInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "step": "0.1",
            "min": "0.0",
            "max": "1.0"
        }),
        label="Style",
        help_text="Style exaggeration (0.0-1.0, higher = more exaggerated)"
    )
    
    use_speaker_boost = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            "class": "rounded bg-gray-800 border-gray-700 text-intellihub-primary focus:ring-intellihub-primary"
        }),
        label="Enable Speaker Boost",
        help_text="Boost speaker clarity and volume"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically load available voices
        try:
            voices = get_available_voices()
            if voices:
                self.fields['voice_id'].choices = [('', 'Default')] + [(voice['id'], voice['name']) for voice in voices]
            else:
                # Fallback choices if service is unavailable
                self.fields['voice_id'].choices = [
                    ('', 'Default'),
                    ('default', 'Default Voice'),
                    ('v2/en_speaker_6', 'Bark Speaker 6'),
                ]
        except Exception:
            # Fallback if service call fails
            self.fields['voice_id'].choices = [
                ('', 'Default'),
                ('default', 'Default Voice'),
            ]
        
        # Set model choices
        self.fields['model'].choices = [
            ('microsoft/speecht5_tts', 'Microsoft SpeechT5 (Recommended)'),
            ('facebook/mms-tts-eng', 'Facebook MMS TTS'),
            ('espnet/kan-bayashi_ljspeech_vits', 'VITS TTS'),
            ('suno/bark', 'Bark TTS'),
            ('tts-1', 'TTS-1 (Fallback)'),
        ]
        self.fields['model'].initial = 'microsoft/speecht5_tts'
    
    def clean_text(self):
        text = self.cleaned_data.get('text', '').strip()
        if not text:
            raise forms.ValidationError("Text cannot be empty")
        if len(text) < 5:
            raise forms.ValidationError("Text must be at least 5 characters long")
        return text
    
    # Voice settings
    stability = forms.FloatField(
        initial=0.5,
        min_value=0.0,
        max_value=1.0,
        widget=forms.NumberInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "step": "0.1",
            "min": "0.0",
            "max": "1.0"
        }),
        label="Stability",
        help_text="Voice stability (0.0-1.0, higher = more stable but less expressive)"
    )
    
    similarity_boost = forms.FloatField(
        initial=0.5,
        min_value=0.0,
        max_value=1.0,
        widget=forms.NumberInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "step": "0.1",
            "min": "0.0",
            "max": "1.0"
        }),
        label="Similarity Boost",
        help_text="Voice similarity boost (0.0-1.0, higher = closer to original voice)"
    )
    
    style = forms.FloatField(
        initial=0.0,
        min_value=0.0,
        max_value=1.0,
        widget=forms.NumberInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "step": "0.1",
            "min": "0.0",
            "max": "1.0"
        }),
        label="Style",
        help_text="Style exaggeration (0.0-1.0, higher = more stylized)"
    )
    
    use_speaker_boost = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={
            "class": "rounded bg-gray-800 border-gray-700 text-intellihub-primary focus:ring-intellihub-primary focus:ring-offset-gray-900"
        }),
        label="Speaker Boost",
        help_text="Enable speaker boost for better clarity"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate voice choices dynamically
        try:
            voices = get_available_voices()
            voice_choices = [('', 'Default')] + [(voice['id'], voice['name']) for voice in voices]
            self.fields['voice_id'].choices = voice_choices
        except Exception:
            # Fallback choices if service is unavailable
            self.fields['voice_id'].choices = [
                ('', 'Default'),
                ('alloy', 'Alloy'),
                ('echo', 'Echo'),
                ('fable', 'Fable'),
                ('onyx', 'Onyx'),
                ('nova', 'Nova'),
                ('shimmer', 'Shimmer'),
            ]


class QuickAudioForm(forms.Form):
    """Simplified form for quick audio generation"""
    
    text = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "Enter text to convert to speech...",
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary",
            "maxlength": "1000"
        }),
        label="Text",
        max_length=1000,
        help_text="Enter text to convert to audio (up to 1000 characters)"
    )
    
    voice = forms.ChoiceField(
        choices=[
            ('alloy', 'Alloy (Neutral)'),
            ('echo', 'Echo (Professional)'),
            ('fable', 'Fable (Storytelling)'),
            ('onyx', 'Onyx (Deep)'),
        ],
        initial='alloy',
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Voice",
        help_text="Choose a voice for the speech"
    )


class PresentationGenerationForm(forms.Form):
    """Form for presentation generation requests"""
    
    title = forms.CharField(
        widget=forms.TextInput(attrs={
            "placeholder": "My Presentation Title",
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Presentation Title",
        max_length=200,
        help_text="Give your presentation a compelling title"
    )
    
    topic = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Describe your presentation topic, key objectives, and main points you want to cover...",
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Topic & Objectives",
        max_length=500,
        help_text="Describe what your presentation should cover"
    )
    
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 2,
            "placeholder": "Brief description or context (optional)...",
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Description",
        required=False,
        help_text="Additional context or background information"
    )
    
    target_audience = forms.CharField(
        widget=forms.TextInput(attrs={
            "placeholder": "e.g., executives, students, clients, team members...",
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Target Audience",
        max_length=200,
        required=False,
        help_text="Who will be viewing this presentation?"
    )
    
    presentation_type = forms.ChoiceField(
        choices=[
            ('business', 'Business Presentation'),
            ('educational', 'Educational/Academic'),
            ('marketing', 'Marketing Pitch'),
            ('report', 'Report/Analysis'),
            ('proposal', 'Project Proposal'),
            ('training', 'Training Material'),
            ('portfolio', 'Portfolio Showcase'),
            ('other', 'Other'),
        ],
        initial='business',
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Presentation Type",
        help_text="What type of presentation are you creating?"
    )
    
    slide_count = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            "min": 3,
            "max": 50,
            "value": 10,
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Number of Slides",
        min_value=3,
        max_value=50,
        initial=10,
        help_text="How many slides do you want? (3-50)"
    )
    
    theme = forms.ChoiceField(
        choices=[
            ('modern', 'Modern & Clean'),
            ('corporate', 'Corporate Professional'),
            ('creative', 'Creative & Colorful'),
            ('minimal', 'Minimal & Simple'),
            ('academic', 'Academic & Traditional'),
            ('tech', 'Technology Focused'),
            ('nature', 'Nature & Organic'),
            ('dark', 'Dark & Bold'),
        ],
        initial='modern',
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Theme",
        help_text="Choose a visual theme for your presentation"
    )
    
    color_scheme = forms.ChoiceField(
        choices=[
            ('blue', 'Professional Blue'),
            ('green', 'Fresh Green'),
            ('purple', 'Creative Purple'),
            ('orange', 'Energetic Orange'),
            ('red', 'Bold Red'),
            ('teal', 'Modern Teal'),
            ('gray', 'Elegant Gray'),
            ('custom', 'Custom Colors'),
        ],
        initial='blue',
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Color Scheme",
        help_text="Select the primary color scheme"
    )
    
    tone = forms.ChoiceField(
        choices=[
            ('professional', 'Professional'),
            ('casual', 'Casual & Friendly'),
            ('formal', 'Formal & Academic'),
            ('persuasive', 'Persuasive & Compelling'),
            ('educational', 'Educational & Clear'),
            ('inspiring', 'Inspiring & Motivational'),
        ],
        initial='professional',
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Tone",
        help_text="What tone should your presentation have?"
    )
    
    include_images = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            "class": "w-4 h-4 text-intellihub-primary bg-gray-800 border-gray-600 rounded focus:ring-intellihub-primary focus:ring-2"
        }),
        label="Include Images",
        required=False,
        initial=True,
        help_text="Generate relevant images for slides"
    )
    
    include_charts = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            "class": "w-4 h-4 text-intellihub-primary bg-gray-800 border-gray-600 rounded focus:ring-intellihub-primary focus:ring-2"
        }),
        label="Include Charts",
        required=False,
        initial=True,
        help_text="Include charts and graphs where appropriate"
    )


class QuickPresentationForm(forms.Form):
    """Simplified form for quick presentation generation"""
    
    topic = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "What do you want to create a presentation about?",
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Presentation Topic",
        max_length=500,
        help_text="Describe your presentation topic and key points"
    )
    
    slide_count = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            "min": 5,
            "max": 20,
            "value": 10,
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Slides",
        min_value=5,
        max_value=20,
        initial=10,
        help_text="Number of slides (5-20)"
    )
    
    presentation_type = forms.ChoiceField(
        choices=[
            ('business', 'Business'),
            ('educational', 'Educational'),
            ('marketing', 'Marketing'),
            ('other', 'Other'),
        ],
        initial='business',
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Type"
    )


class SlideEditForm(forms.Form):
    """Form for editing individual slides"""
    
    title = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Slide Title",
        max_length=300,
        required=False
    )
    
    subtitle = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Subtitle",
        max_length=500,
        required=False
    )
    
    content = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 6,
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Content",
        required=False,
        help_text="Main slide content"
    )
    
    notes = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 3,
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Speaker Notes",
        required=False,
        help_text="Notes for the presenter"
    )
    
    slide_type = forms.ChoiceField(
        choices=[
            ('title', 'Title Slide'),
            ('content', 'Content Slide'),
            ('bullet_points', 'Bullet Points'),
            ('two_column', 'Two Column Layout'),
            ('image_text', 'Image with Text'),
            ('chart', 'Chart/Graph'),
            ('quote', 'Quote/Testimonial'),
            ('call_to_action', 'Call to Action'),
            ('thank_you', 'Thank You/Contact'),
            ('section_break', 'Section Break'),
        ],
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Slide Type"
    )
    
    layout = forms.ChoiceField(
        choices=[
            ('default', 'Default Layout'),
            ('centered', 'Centered Content'),
            ('left_aligned', 'Left Aligned'),
            ('split_half', 'Split 50/50'),
            ('two_thirds_left', 'Two-thirds Left'),
            ('two_thirds_right', 'Two-thirds Right'),
            ('full_image', 'Full Background Image'),
            ('minimal', 'Minimal Text'),
        ],
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Layout"
    )


class PresentationShareForm(forms.Form):
    """Form for sharing presentations"""
    
    is_public = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            "class": "w-4 h-4 text-intellihub-primary bg-gray-800 border-gray-600 rounded focus:ring-intellihub-primary focus:ring-2"
        }),
        label="Make Public",
        required=False,
        help_text="Allow others to view this presentation"
    )
    
    generate_link = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            "class": "w-4 h-4 text-intellihub-primary bg-gray-800 border-gray-600 rounded focus:ring-intellihub-primary focus:ring-2"
        }),
        label="Generate Sharing Link",
        required=False,
        help_text="Create a unique link for sharing"
    )


class PresentationExportForm(forms.Form):
    """Form for exporting presentations"""
    
    export_format = forms.ChoiceField(
        choices=[
            ('pdf', 'PDF Document'),
            ('pptx', 'PowerPoint (.pptx)'),
            ('html', 'HTML Presentation'),
            ('images', 'Image Files (ZIP)'),
            ('json', 'JSON Data'),
        ],
        initial='pdf',
        widget=forms.Select(attrs={
            "class": "w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-gray-100 focus:outline-none focus:ring-2 focus:ring-intellihub-primary"
        }),
        label="Export Format",
        help_text="Choose the export format"
    )
    
    include_notes = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            "class": "w-4 h-4 text-intellihub-primary bg-gray-800 border-gray-600 rounded focus:ring-intellihub-primary focus:ring-2"
        }),
        label="Include Speaker Notes",
        required=False,
        initial=True,
        help_text="Include speaker notes in the export"
    )
    
    high_quality = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            "class": "w-4 h-4 text-intellihub-primary bg-gray-800 border-gray-600 rounded focus:ring-intellihub-primary focus:ring-2"
        }),
        label="High Quality",
        required=False,
        initial=True,
        help_text="Export in high quality (larger file size)"
    )
