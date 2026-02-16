from django.urls import path
from .views import (
    IndexView, ChatAPIView, SignUpView, LoginView, LogoutView,
    ImageGenerationView, QuickImageView, ImageGenerationAPIView,
    ImageResultView, ImageGalleryView, ImageUpscaleView, ImageMetricsView,
    VideoGenerationView, QuickVideoView, VideoGenerationAPIView, VideoResultView, VideoGalleryView, VideoMetricsView,
    AudioGenerationView, QuickAudioView, AudioGenerationAPIView, AudioResultView, AudioGalleryView, AudioMetricsView,
    PresentationGenerationView, QuickPresentationView, PresentationGenerationAPIView, PresentationResultView,
    PresentationPreviewView, PresentationEditView, SlideEditView, PresentationGalleryView, PresentationShareView,
    PresentationExportView, PresentationDownloadView, PresentationMetricsView
)

# Import IDE views
from .views_ide import (
    IDEDashboardView, ProjectCreateView, IDEEditorView, ProjectDeleteView,
    FileAPIView, CodeExecutionView, ExecutionHistoryView, IDEChatView,
    ProjectExportView, ProjectDeploymentView, IDEPreferencesView,
    WebsiteTemplateView, ComponentLibraryView
)

urlpatterns = [
    path('', IndexView.as_view(), name='index'),
    path('chat/<int:conversation_id>/', IndexView.as_view(), name='chat_conversation'),
    path('signup/', SignUpView.as_view(), name='signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    
    # Chat API URLs
    path('api/chat/', ChatAPIView.as_view(), name='chat_api'),
    path('api/conversations/', ChatAPIView.as_view(), name='conversations_api'),
    path('api/conversations/<int:conversation_id>/', ChatAPIView.as_view(), name='conversation_detail_api'),
    path('api/conversations/<int:conversation_id>/messages/', ChatAPIView.as_view(), name='conversation_messages_api'),
    
    # Image generation URLs
    path('images/', ImageGenerationView.as_view(), name='image_generation'),
    path('images/quick/', QuickImageView.as_view(), name='quick_image'),
    path('images/result/<int:request_id>/', ImageResultView.as_view(), name='image_result'),
    path('images/gallery/', ImageGalleryView.as_view(), name='image_gallery'),
    
    # Image API URLs
    path('api/images/generate/', ImageGenerationAPIView.as_view(), name='image_generation_api'),
    path('api/images/upscale/', ImageUpscaleView.as_view(), name='image_upscale_api'),
    path('api/images/metrics/', ImageMetricsView.as_view(), name='image_metrics_api'),
    
    # Video generation URLs
    path('videos/', VideoGenerationView.as_view(), name='video_generation'),
    path('videos/quick/', QuickVideoView.as_view(), name='quick_video'),
    path('videos/result/<int:request_id>/', VideoResultView.as_view(), name='video_result'),
    path('videos/gallery/', VideoGalleryView.as_view(), name='video_gallery'),
    
    # Video API URLs
    path('api/videos/generate/', VideoGenerationAPIView.as_view(), name='video_generation_api'),
    path('api/videos/metrics/', VideoMetricsView.as_view(), name='video_metrics_api'),
    
    # Audio generation URLs
    path('audio/', AudioGenerationView.as_view(), name='audio_generation'),
    path('audio/quick/', QuickAudioView.as_view(), name='quick_audio'),
    path('audio/result/<int:request_id>/', AudioResultView.as_view(), name='audio_result'),
    path('audio/gallery/', AudioGalleryView.as_view(), name='audio_gallery'),
    
    # Audio API URLs
    path('api/audio/generate/', AudioGenerationAPIView.as_view(), name='audio_generation_api'),
    path('api/audio/metrics/', AudioMetricsView.as_view(), name='audio_metrics_api'),
    
    # Presentation generation URLs
    path('presentations/', PresentationGenerationView.as_view(), name='presentation_generation'),
    path('presentations/quick/', QuickPresentationView.as_view(), name='quick_presentation'),
    path('presentations/result/<int:presentation_id>/', PresentationResultView.as_view(), name='presentation_result'),
    path('presentations/preview/<int:presentation_id>/', PresentationPreviewView.as_view(), name='presentation_preview'),
    path('presentations/edit/<int:presentation_id>/', PresentationEditView.as_view(), name='presentation_edit'),
    path('presentations/edit/<int:presentation_id>/slide/<int:slide_id>/', SlideEditView.as_view(), name='slide_edit'),
    path('presentations/gallery/', PresentationGalleryView.as_view(), name='presentation_gallery'),
    path('presentations/share/<int:presentation_id>/', PresentationShareView.as_view(), name='presentation_share'),
    path('presentations/export/<int:presentation_id>/', PresentationExportView.as_view(), name='presentation_export'),
    path('presentations/download/<int:export_id>/', PresentationDownloadView.as_view(), name='presentation_download'),
    
    # Presentation API URLs
    path('api/presentations/generate/', PresentationGenerationAPIView.as_view(), name='presentation_generation_api'),
    path('api/presentations/metrics/', PresentationMetricsView.as_view(), name='presentation_metrics_api'),
    
    # ========================================
    # IDE URLs
    # ========================================
    
    # IDE Dashboard and Projects
    path('ide/', IDEDashboardView.as_view(), name='ide_dashboard'),
    path('ide/projects/create/', ProjectCreateView.as_view(), name='ide_project_create'),
    path('ide/projects/<int:project_id>/', IDEEditorView.as_view(), name='ide_editor'),
    path('ide/projects/<int:project_id>/delete/', ProjectDeleteView.as_view(), name='ide_project_delete'),
    
    # File Management API
    path('ide/api/projects/<int:project_id>/files/', FileAPIView.as_view(), name='ide_files_list'),
    path('ide/api/projects/<int:project_id>/files/<int:file_id>/', FileAPIView.as_view(), name='ide_file_detail'),
    
    # Code Execution API
    path('ide/api/projects/<int:project_id>/execute/', CodeExecutionView.as_view(), name='ide_execute'),
    path('ide/api/projects/<int:project_id>/executions/', ExecutionHistoryView.as_view(), name='ide_execution_history'),
    
    # AI Chat API
    path('ide/api/projects/<int:project_id>/chat/', IDEChatView.as_view(), name='ide_chat'),
    
    # Export and Deployment
    path('ide/api/projects/<int:project_id>/export/', ProjectExportView.as_view(), name='ide_export'),
    path('ide/api/projects/<int:project_id>/export/<int:export_id>/', ProjectExportView.as_view(), name='ide_export_download'),
    path('ide/api/projects/<int:project_id>/deploy/', ProjectDeploymentView.as_view(), name='ide_deploy'),
    
    # IDE Preferences
    path('ide/api/preferences/', IDEPreferencesView.as_view(), name='ide_preferences'),
    
    # Website Templates and Components
    path('ide/api/templates/', WebsiteTemplateView.as_view(), name='ide_templates'),
    path('ide/api/components/', ComponentLibraryView.as_view(), name='ide_components'),
]
